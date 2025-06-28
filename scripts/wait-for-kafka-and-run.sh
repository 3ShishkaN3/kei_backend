#!/bin/sh
# wait-for-kafka-and-run.sh

set -e

KAFKA_HOST="kafka"
KAFKA_PORT="9092"
CMD="$@"

echo "Waiting for Kafka at $KAFKA_HOST:$KAFKA_PORT..."

# Loop until we can establish a connection with Kafka
while ! nc -z $KAFKA_HOST $KAFKA_PORT; do
  >&2 echo "Kafka is unavailable - sleeping"
  sleep 1
done

>&2 echo "Kafka is up - executing command: $CMD"
exec $CMD 