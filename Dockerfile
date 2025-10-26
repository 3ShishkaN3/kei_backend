FROM python:3.11.11-slim

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

RUN apt-get update && apt-get install -y netcat-openbsd && rm -rf /var/lib/apt/lists/*

COPY . .

RUN chmod +x /app/scripts/wait-for-kafka-and-run.sh

CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "kei_backend.asgi:application"] 