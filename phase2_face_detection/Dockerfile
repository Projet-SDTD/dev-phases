FROM python:3.9-slim

WORKDIR /app
RUN mkdir /app/stream

COPY requirements.txt .
RUN pip install --no-cache -r requirements.txt

COPY face_detection.py .
COPY haarcascade_frontalface_default.xml .

CMD ["python", "-u", "face_detection.py"]
