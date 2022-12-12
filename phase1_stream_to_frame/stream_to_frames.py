#!/usr/bin/env python3
import logging
import sys
import streamlink
import os
import m3u8
from kafka import KafkaProducer
import base64
from json import dumps
import numpy as np

try:
    import cv2
except ImportError:
    sys.stderr.write("This example requires opencv-python is installed")
    raise

log = logging.getLogger(__name__)

date_set = set()

NUMBER_FRAMES_PER_TS = 60    #OK pour du 720p TODO pour autres qualités

def stream_to_url(url, quality='best'):
    streams = streamlink.streams(url)
    if streams:
        return streams[quality].to_url()
    else:
        raise ValueError("No streams were available")

def parse_m3u8(url_m3u8, ts_list, date_list):
    file = m3u8.load(url_m3u8)
    for ts in file.segments:
        if ts:
            if ts.program_date_time not in date_set:
                #print(ts.uri)
                #print(ts.program_date_time)
                ts_list.append(ts.uri)
                date_list.append(ts.program_date_time)
                date_set.add(ts.program_date_time)
    return ts_list, date_list

def adjust_fps(cap, fps):
    for _ in range(NUMBER_FRAMES_PER_TS // fps - 1):
        cap.read()

def main(url, quality='best', fps=30.0, kafka_url="kafka-svc:9092"):
    kafka_producer = KafkaProducer(
        api_version = (3,3,1),
        security_protocol= "PLAINTEXT",
        bootstrap_servers = kafka_url,
        value_serializer = lambda x:dumps(x).encode('utf-8')
    )
    directory = "./stream"
    os.chdir(directory)
    frame_number = 0
    ts_num = 0
    ts_list = []
    date_list = []
    #récupération du m3u8
    stream_url = stream_to_url(url, quality)
    #print(stream_url)
    log.info("Loading stream {0}".format(stream_url))
    #print(stream_url)
    while True:
        #parser le m3u8 en ts 
        ts_list, date_list = parse_m3u8(stream_url, ts_list, date_list)
        #traitement des ts
        if len(ts_list) != 0:
            #on récupère la 1ère ts
            ts = ts_list.pop(0)
            date = date_list.pop(0)
            print('------ ' + str(date) + ' -------')
            print('     len(ts_list) = ', len(ts_list))
            
            cap = cv2.VideoCapture(ts)
            frame_time = (1.0 / fps)
            
            # on update les compteurs pour la nouvelle ts
            frames = 0
            ts_num += 1

            while frames < NUMBER_FRAMES_PER_TS:
                try:
                    ret, frame = cap.read()
                    adjust_fps(cap, int(fps))
                    if ret:
                        print(frame_number)
                        frame_64 = base64.b64encode(cv2.imencode('.jpg', frame)[1]).decode()
                        print("sending frame to kafka...")
                        kafka_producer.send("phase1", value={'frame_number' : frame_number, "frame" : frame_64})
                        print("sent !")
                        #cv2.imwrite(f"{ts_num}_{frame_number}.jpg", frame)
                        frame_number += 1
                        frames += 1
                    else:
                        break
                except KeyboardInterrupt:
                    break
            cap.release()


if __name__ == "__main__":

    QUALITY = os.getenv("STREAM-QUALITY")
    FPS = os.getenv("FPS")
    URL = os.getenv("URL")
    KAFKA_URL = os.getenv("KAFKA_URL")

    print(URL)

    if(URL is None):
        sys.stderr.write("You must set the environment var URL\n")
    if(QUALITY is None):
        QUALITY = "720p60"
    if(FPS is None):
        FPS = 10.0
    if(KAFKA_URL is None):
        KAFKA_URL = "kafka-svc:9092"

    main(URL, QUALITY, float(FPS), KAFKA_URL)

