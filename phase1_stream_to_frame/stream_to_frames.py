#!/usr/bin/env python3
import logging
import sys
import streamlink
import os
import m3u8
from m3u8.httpclient import DefaultHTTPClient
from kafka import KafkaProducer
import base64
import time
from json import dumps
import numpy as np

try:
    import cv2
except ImportError:
    sys.stderr.write("This example requires opencv-python is installed")
    raise

log = logging.getLogger(__name__)

date_set = set()

TS_DURATION = 0 #Number of seconds per ts
TS_DURATION_SET = False

FRAMES_PER_TS_DETERMINED = False
NUMBER_FRAMES_PER_TS = 0 

def stream_to_url(url, quality='best'):
    streams = streamlink.streams(url)
    if streams:
        return streams[quality].to_url()
    else:
        raise ValueError("No streams were available")

def parse_m3u8(url_m3u8, ts_list, date_list, http_client):
    global TS_DURATION_SET
    global TS_DURATION
    error_counter = 0
    loaded = False
    while(error_counter < 5 and not loaded):
        try:
            file = m3u8.load(url_m3u8, timeout=3, http_client=http_client)
            loaded = True
            for ts in file.segments:
                if ts:
                    if ts.program_date_time not in date_set:
                        #print(ts.uri)
                        #print(ts.program_date_time)
                        if not(TS_DURATION_SET):
                            print("(i) Determining TS_DURATION")
                            TS_DURATION = ts.duration
                            TS_DURATION_SET = True
                            print("(i) TS_DURATION", TS_DURATION)
                        ts_list.append(ts.uri)
                        date_list.append(ts.program_date_time)
                        date_set.add(ts.program_date_time)
        except:
            print("(e) Couldn't load m3u8, retry in 0.1 second...")
            time.sleep(0.1)
            error_counter += 1
    if not loaded:
        print('(e) Retried 5 times to load m3u8 exiting now')
        exit(1)
    return ts_list, date_list

def main(url, quality='best', fps=30.0, kafka_url="kafka-svc:9092"):
    kafka_producer = KafkaProducer(
        api_version = (3,3,1),
        security_protocol= "PLAINTEXT",
        bootstrap_servers = kafka_url,
        value_serializer = lambda x:dumps(x).encode('utf-8')
    )
    global FRAMES_PER_TS_DETERMINED
    global NUMBER_FRAMES_PER_TS
    global TS_DURATION

    directory = "./stream"
    os.chdir(directory)
    frame_number = 0
    ts_num = 0
    ts_list = []
    date_list = []
    #récupération du m3u8
    stream_url = stream_to_url(url, quality)
    log.info("Loading stream {0}".format(stream_url))
    #print(stream_url)

    number_skipped = 0

    httpClient = DefaultHTTPClient()

    while True:
        ts_list, date_list = parse_m3u8(stream_url, ts_list, date_list, httpClient)
        #parser le m3u8 en ts
        if number_skipped < 8:
            time_before = time.time()
            #on récupère la 1ère ts
            while len(ts_list) > 0:
                ts = ts_list.pop(0)
                number_skipped += 1
                date = date_list.pop(0)
                
                cap = cv2.VideoCapture(ts)
                r = (True, '')
                while r[0]:
                    r = cap.read()

        else:
            if not(FRAMES_PER_TS_DETERMINED) and len(ts_list) != 0:
                print("(i) Determining FPTS")
                ts = ts_list.pop(0)
                i = 0
                cap = cv2.VideoCapture(ts)
                r = (True, '')
                while r[0]:
                    r = cap.read()
                    i += 1
                i -= 1
                cap.release()
                NUMBER_FRAMES_PER_TS = i
                FRAMES_PER_TS_DETERMINED = True
                print("(i) FPTS :", NUMBER_FRAMES_PER_TS)

            #traitement des ts
            elif len(ts_list) != 0:
                while len(ts_list) > 0:
                    time_before = time.time()
                    #on récupère la 1ère ts
                    ts = ts_list.pop(0)
                    date = date_list.pop(0)
                    print('------ ' + str(date) + ' -------')
                    print('     len(ts_list) = ', len(ts_list))
                    
                    cap = cv2.VideoCapture(ts)
                    
                    # on update les compteurs pour la nouvelle ts
                    frames = 0
                    ts_num += 1

                    ret = True

                    while frames < NUMBER_FRAMES_PER_TS:
                        try:
                            ret, frame = cap.read()
                            for _ in range(int(NUMBER_FRAMES_PER_TS // (fps * TS_DURATION) - 1)):
                                cap.read()
                                frames += 1
                            if ret:
                                print(frame_number)
                                frame_64 = base64.b64encode(cv2.imencode('.jpg', frame)[1]).decode()
                                print("sending frame to kafka...")
                                kafka_producer.send("phase1", value={'frame_number' : frame_number, "frame" : frame_64, "timestampFrame" : str(date), "url" : url})
                                print("sent !")
                                #cv2.imwrite(f"{frame_number}.jpg", frame)
                                frame_number += 1
                                frames += 1
                            else:
                                break
                        except KeyboardInterrupt:
                            break
                    
                    cap.release()
                
                # Make sure to wait the duration of a ts between two requests
                time_now = time.time()
                if time_now - time_before < TS_DURATION/2:
                    time.sleep(TS_DURATION/2 - (time_now - time_before))
                
            else:
                # Make sure to wait the duration of a ts between two requests
                time.sleep(TS_DURATION)


if __name__ == "__main__":

    QUALITY = os.getenv("STREAM_QUALITY")
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

