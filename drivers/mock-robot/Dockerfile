FROM python:3.12-slim

WORKDIR /app

COPY drivers/mock-robot/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY server/ito ./server/ito
COPY drivers/mock-robot/mock_robot ./mock_robot
COPY drivers/mock-robot/main.py ./main.py

ENV PYTHONUNBUFFERED=1

CMD ["python", "main.py"]
