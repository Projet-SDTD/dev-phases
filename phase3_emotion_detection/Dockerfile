FROM python:3.9-slim

WORKDIR /app
RUN mkdir /app/stream

COPY requirements.txt .
RUN pip install --no-cache -r requirements.txt

COPY emotion_detection.py .
COPY emotion-ferplus-8.onnx .

CMD ["python", "-u", "emotion_detection.py"]
