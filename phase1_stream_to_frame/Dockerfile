FROM python:3.9-slim

WORKDIR /app
RUN mkdir /app/stream

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY stream_to_frames.py .

CMD ["python","-u", "./stream_to_frames.py"]
