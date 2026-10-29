# The base image is given explicitly: Home Assistant no longer provides one to add-ons (2026.4+).
FROM python:3.12-alpine

LABEL \
  io.hass.version="1.0.0" \
  io.hass.type="app" \
  io.hass.arch="aarch64|amd64"

RUN pip install --no-cache-dir paho-mqtt==2.1.0

WORKDIR /app
COPY server.py logic.py ha_entities.py ha_mqtt.py /app/
COPY web /app/web
COPY run.sh /run.sh
RUN sed -i 's/\r$//' /run.sh && chmod a+x /run.sh

CMD [ "/run.sh" ]
