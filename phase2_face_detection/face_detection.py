#!/usr/bin/env python3
import base64
import logging
import sys
import os
import glob
from PIL import Image
from kafka import KafkaConsumer, KafkaProducer
from json import dumps, loads
import numpy as np

try:
    import cv2
except ImportError:
    sys.stderr.write("This example requires opencv-python is installed")
    raise

log = logging.getLogger(__name__)
GREEN = (0, 255, 0)

def detect_faces(cascade, frame, frame_number, scale_factor=1.1, min_neighbors=5):
    #detect all the faces in a frame => return a list
    frame_copy = frame.copy()
    frame_gray = cv2.cvtColor(frame_copy, cv2.COLOR_BGR2GRAY)
    faces = cascade.detectMultiScale(frame_gray, scaleFactor=scale_factor, minNeighbors=min_neighbors)
    detected_faces = []
    for (x, y, w, h) in faces:
        coords = [x, y, w, h]
        coords = [int(i) for i in coords]
        detected_faces.append(coords)
    return detected_faces


def main(kafka_url = "kafka-svc:9092"):
    face_cascade = cv2.CascadeClassifier(os.path.join(cv2.data.haarcascades, 'haarcascade_frontalface_default.xml'))
    #faces_data = open("faces_data.txt", "w+")
    print("Connecting to Kafka as a consumer...")
    kafka_consumer = KafkaConsumer(  
        'phase1',
        api_version = (3,3,1),
        # TODO
        security_protocol= "PLAINTEXT",
        bootstrap_servers = kafka_url,
        auto_offset_reset = 'earliest',  
        enable_auto_commit = True,
        group_id = 'my-group',  
        value_deserializer = lambda x : loads(x.decode('utf-8'))  
    )
    print("Connected !")
    print("Connecting to Kafka as a producer...")
    kafka_producer = KafkaProducer(
        api_version = (3,3,1),
        security_protocol= "PLAINTEXT",
        bootstrap_servers = kafka_url,
        value_serializer = lambda x:dumps(x).encode('utf-8')
    )
    print("Connected !")
    for message in kafka_consumer:
        message = message.value
        new_message = message.copy()
        print(message["frame_number"])
        frame_number = message['frame_number']
        #decode the b64 format -> bytes
        img = base64.b64decode(message['frame'])
        #decode the cv2 encoding -> buffer
        img_buffer = cv2.imdecode(np.frombuffer(img, dtype=np.uint8) , flags=1)
        detected_faces = detect_faces(face_cascade, img_buffer, frame_number, scale_factor=1.2)
        if(len(detected_faces) > 0):
            for index, face in enumerate(detected_faces):
                x = face[0]
                y = face[1]
                w = face[2]
                h = face[3]
                area = (x, y, x + w, y + h)
                #crop the PIL Image to only have the detected face
                cropped_img = img_buffer[y:y+h, x:x+w]
                #encode image so that it can be send
                frame_64 = base64.b64encode(cv2.imencode('.jpg', cropped_img)[1]).decode()
                new_message['detected_face'] = face
                new_message['frame'] = frame_64
                new_message['face_number'] = index
                #print(f"All types : message : {type(new_message)}, number : {type(new_message['frame_number'])}, img : {type(new_message['frame'])}, faces : {type(new_message['detected_faces'][0])}")
                print(new_message['face_number'])
                kafka_producer.send("phase3", value=new_message)
    

    '''
    os.chdir("./stream")
    for img_name in sorted(glob.glob('*.jpg'), key=os.path.getmtime):
        frame_number = img_name[0] #get the frame number in the name
        img = cv2.imread(img_name)
        detected_faces = detect_faces(face_cascade, img, frame_number, scale_factor=1.2)
        faces_data.write(f"{img_name} : {detected_faces}\n")
    faces_data.close()
    '''

'''
def main(url, quality='best', fps=30.0):
    face_cascade = cv2.CascadeClassifier(os.path.join(cv2.data.haarcascades, 'haarcascade_frontalface_default.xml'))
    directory = ".\stream"
    img_list = []
    os.chdir(directory)
    log.info("Loading stream {0}".format(stream_url))
    cap = cv2.VideoCapture(stream_url)
    frame_time = int((1.0 / fps) * 1000.0)
    frame_number = 0
    while True:
        try:
            ret, frame = cap.read()
            if ret:
                frame_f = detect_faces(face_cascade, frame, frame_number, scale_factor=1.2)
                frame_number += 1
                cv2.imshow('frame', frame_f)
                if cv2.waitKey(frame_time) & 0xFF == ord('q'):
                    break
            else:
                break
        except KeyboardInterrupt:
            break
    cv2.destroyAllWindows()
    cap.release()
'''

if __name__ == "__main__":
    KAFKA_URL = os.getenv("KAFKA_URL")
    if(KAFKA_URL is None):
        KAFKA_URL = "kafka-svc:9092"
    main(KAFKA_URL)