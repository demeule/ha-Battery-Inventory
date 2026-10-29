#!/bin/sh
# Starts Battery Inventory inside Home Assistant.
export BATTERY_HOST=0.0.0.0
export BATTERY_PORT=8099
export BATTERY_DATA=/data
# Only the Home Assistant ingress proxy (and the local health check) may talk to the server.
export BATTERY_ALLOWED_CLIENTS=172.30.32.2,127.0.0.1
export BATTERY_MQTT=1
export PYTHONUNBUFFERED=1
export PYTHONUTF8=1
cd /app
exec python3 /app/server.py
