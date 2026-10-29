# -*- coding: utf-8 -*-
"""Migration : les anciennes entités « mes_piles » (avant Battery Inventory) sont retirées de Home Assistant au démarrage."""
import json, os, subprocess, sys, time, urllib.request
import paho.mqtt.client as paho
from helpers import ADDON, tmpdir, free_port, start_mosquitto, skip_without_mqtt
skip_without_mqtt()
fails = 0
def ok(c, m):
    global fails
    print(("OK   " if c else "ECHEC") + " " + m)
    if not c: fails += 1
MQ, MQPORT = start_mosquitto()
msgs = {}
def on(c, u, m): msgs[m.topic] = m.payload.decode()
ha = paho.Client(paho.CallbackAPIVersion.VERSION2, client_id="legacy_sim"); ha.on_message = on
ha.connect("127.0.0.1", MQPORT); ha.loop_start(); ha.subscribe("#")
# des restes de l'ancienne version, conservés (retain) par Mosquitto
old = ["homeassistant/sensor/mes_piles/global_total_stock/config", "homeassistant/switch/mes_piles/eq_abc_dead/config",
       "mes_piles/status", "mes_piles/global/total_stock", "mes_piles/equipment/abc/dead"]
for t in old: ha.publish(t, '{"x":1}' if t.endswith("/config") else "ON", retain=True, qos=1)
time.sleep(0.5)
PORT = free_port(); DATA = tmpdir()
env = dict(os.environ, BATTERY_PORT=str(PORT), BATTERY_DATA=DATA, BATTERY_MQTT="1", BATTERY_MQTT_HOST="127.0.0.1", BATTERY_MQTT_PORT=str(MQPORT), PYTHONUNBUFFERED="1")
srv = subprocess.Popen([sys.executable, str(ADDON / "server.py")], env=env, stdout=open(os.path.join(DATA, "server.log"), "a"), stderr=subprocess.STDOUT)
def wait(c, t=10):
    d = time.time() + t
    while time.time() < d:
        try:
            if c(): return True
        except Exception: pass
        time.sleep(0.1)
    return False
ok(wait(lambda: msgs.get("battery_inventory/status") == "online"), "le nouveau module est connecté")
ok(wait(lambda: all(msgs.get(t) == "" for t in old)), "les 5 anciennes entrées « mes_piles » sont vidées (plus d'entités fantômes)")
ok(len([t for t, v in msgs.items() if t.startswith("homeassistant/") and "/battery_inventory/" in t and v]) == 24, "les 24 nouvelles entités sont bien là")
srv.terminate(); MQ.terminate()
print("TOUT PASSE" if not fails else f"{fails} ECHEC(S)")
sys.exit(1 if fails else 0)
