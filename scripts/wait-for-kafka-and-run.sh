#!/bin/sh

set -e

KAFKA_HOST="kafka"
KAFKA_PORT="29092"
CMD="$@"

echo "Waiting for Kafka at $KAFKA_HOST:$KAFKA_PORT..."

while ! nc -z $KAFKA_HOST $KAFKA_PORT; do
  >&2 echo "Kafka is unavailable - sleeping"
  sleep 1
done

>&2 echo "Kafka is up - executing command: $CMD"
exec $CMD 