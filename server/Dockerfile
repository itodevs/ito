FROM python:3.14-slim

WORKDIR /app
COPY server/requirements.txt /app/server/requirements.txt
RUN pip install --no-cache-dir -r /app/server/requirements.txt
COPY server /app/server
ENV PYTHONPATH=/app
CMD ["python", "-m", "server.ito.app"]
