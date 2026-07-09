FROM docker.io/library/ros:humble-ros-base

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-pip \
    ros-humble-sensor-msgs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY server /app/server
COPY drivers/ito-droid /app/drivers/ito-droid

RUN pip3 install --no-cache-dir \
    'msgpack>=1.1,<2' \
    'websockets>=15,<16' \
    'aiortc>=1.9,<2' \
    'av>=16,<17'

ENV PYTHONPATH=/app:/app/drivers/ito-droid

CMD ["python3", "/app/drivers/ito-droid/main.py"]
