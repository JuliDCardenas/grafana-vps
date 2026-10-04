#!/bin/sh

echo "Starting Jules DB Exporter..."
while true; do
  python3 /app/exporter.py
  sleep 60
done
