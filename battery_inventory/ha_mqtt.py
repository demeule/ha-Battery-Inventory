# -*- coding: utf-8 -*-
"""Liaison Battery Inventory <-> Home Assistant, via Mosquitto (MQTT).

- Publie les capteurs, interrupteurs et boutons (découverte automatique : rien à écrire dans Home Assistant).
- Reçoit les ordres venant de Home Assistant (boutons, interrupteurs) et les applique avec les mêmes règles que l'appli.
- Si Mosquitto n'est pas joignable, l'appli continue de fonctionner normalement.
"""
import json
import os
import re
import threading
import time
import traceback
import urllib.error
import urllib.request
from pathlib import Path

import ha_entities as E
import logic

try:
    import paho.mqtt.client as paho
except Exception:  # pragma: no cover
    paho = None

ID_RE = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")
# Ancien nom interne (avant « Battery Inventory ») : ses entités MQTT sont retirées automatiquement au démarrage.
LEGACY_PREFIX = "mes_piles"


class SettingsError(Exception):
    pass


class Bridge:
    def __init__(self, store):
        self.store = store
        self.topics_file = store.dir / "mqtt_topics.json"
        self.status = {"state": "démarrage", "detail": "", "entities": 0}
        self.wake = threading.Event()
        self.connected = False
        self.client = None
        self.last_return = None
        self._cfg_cache = {}
        self._state_cache = {}
        self._legacy = set()
        self._legacy_at = None

    # ----- appelé par le serveur quand les données changent -----
    def notify(self):
        self.wake.set()

    def start(self):
        threading.Thread(target=self._run, daemon=True, name="mqtt").start()

    # ----- réglages de connexion -----
    def _settings(self):
        host = os.environ.get("BATTERY_MQTT_HOST", "").strip()
        if host:
            return {"host": host, "port": int(os.environ.get("BATTERY_MQTT_PORT", "1883")),
                    "user": os.environ.get("BATTERY_MQTT_USER") or None, "password": os.environ.get("BATTERY_MQTT_PASSWORD") or None}
        try:
            opts = json.loads(Path(os.environ.get("BATTERY_OPTIONS", "/data/options.json")).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            opts = {}
        if (opts.get("mqtt_host") or "").strip():
            return {"host": opts["mqtt_host"].strip(), "port": int(opts.get("mqtt_port") or 1883),
                    "user": opts.get("mqtt_user") or None, "password": opts.get("mqtt_password") or None}
        token = os.environ.get("SUPERVISOR_TOKEN")
        if not token:
            return None
        url = os.environ.get("BATTERY_SUPERVISOR_URL", "http://supervisor") + "/services/mqtt"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.loads(r.read().decode("utf-8")).get("data") or {}
        except urllib.error.HTTPError:
            raise SettingsError("Mosquitto n'est pas installé ou pas démarré dans Home Assistant.")
        except (OSError, ValueError):
            raise SettingsError("Home Assistant ne répond pas pour l'instant.")
        if not data.get("host"):
            raise SettingsError("Home Assistant n'a pas donné l'adresse de Mosquitto.")
        return {"host": data["host"], "port": int(data.get("port") or 1883),
                "user": data.get("username") or None, "password": data.get("password") or None}

    # ----- boucle principale -----
    def _run(self):
        if paho is None:
            self.status = {"state": "erreur", "detail": "Le composant MQTT (paho-mqtt) n'est pas installé.", "entities": 0}
            return
        cfg = None
        while cfg is None:
            try:
                cfg = self._settings()
                if cfg is None:
                    self.status = {"state": "non configuré", "detail": "Aucun Mosquitto indiqué.", "entities": 0}
            except SettingsError as e:
                self.status = {"state": "en attente", "detail": str(e), "entities": 0}
            if cfg is None:
                time.sleep(30)
        c = paho.Client(paho.CallbackAPIVersion.VERSION2, client_id="battery_inventory")
        if cfg["user"]:
            c.username_pw_set(cfg["user"], cfg["password"])
        c.will_set(E.STATUS_TOPIC, "offline", qos=1, retain=True)
        c.on_connect = self._on_connect
        c.on_disconnect = self._on_disconnect
        c.on_message = self._on_message
        c.reconnect_delay_set(2, 60)
        self.client = c
        self.status = {"state": "connexion", "detail": f"{cfg['host']}:{cfg['port']}", "entities": 0}
        c.connect_async(cfg["host"], cfg["port"], keepalive=60)
        c.loop_start()
        while True:
            self.wake.wait(timeout=3 if self._legacy_at else 300)
            self.wake.clear()
            if self.connected:
                try:
                    if self._legacy_at and time.time() - self._legacy_at > 2:
                        self._cleanup_legacy()
                    self.sync()
                except Exception as e:  # ne jamais faire tomber l'appli à cause de MQTT
                    traceback.print_exc()
                    self.status = {"state": "erreur", "detail": f"Envoi vers Home Assistant impossible : {e}", "entities": 0}

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        if rc.is_failure:
            self.status = {"state": "erreur", "detail": f"Mosquitto a refusé la connexion ({rc}).", "entities": 0}
            return
        self.connected = True
        self._cfg_cache, self._state_cache = {}, {}
        client.publish(E.STATUS_TOPIC, "online", qos=1, retain=True)
        for t in (f"{E.PREFIX}/equipment/+/dead/set", f"{E.PREFIX}/equipment/+/replace/press", f"{E.PREFIX}/stock/+/charged/press"):
            client.subscribe(t, qos=1)
        client.subscribe(f"{E.DISCOVERY}/+/{LEGACY_PREFIX}/+/config", qos=1)   # anciennes entités à retirer
        client.subscribe(f"{LEGACY_PREFIX}/#", qos=1)
        self._legacy, self._legacy_at = set(), time.time()
        self.status = {"state": "connecté", "detail": "Mosquitto", "entities": self.status.get("entities", 0)}
        self.wake.set()

    def _on_disconnect(self, client, userdata, flags, rc, properties=None):
        self.connected = False
        self.status = {"state": "déconnecté", "detail": "Connexion à Mosquitto perdue, nouvelle tentative automatique.", "entities": 0}

    # ----- publication -----
    def _load_topics(self):
        try:
            j = json.loads(self.topics_file.read_text(encoding="utf-8"))
            return set(j.get("configs", [])), set(j.get("states", []))
        except (OSError, ValueError):
            return set(), set()

    def sync(self):
        d = self.store.snapshot()
        configs, states = E.build(d, self.last_return)
        c = self.client
        for topic, cfg in configs.items():
            payload = json.dumps(cfg, ensure_ascii=False)
            if self._cfg_cache.get(topic) != payload:
                c.publish(topic, payload, qos=1, retain=True)
                self._cfg_cache[topic] = payload
        for topic, val in states.items():
            if self._state_cache.get(topic) != val:
                c.publish(topic, val, qos=1, retain=True)
                self._state_cache[topic] = val
        old_cfg, old_states = self._load_topics()
        for t in old_cfg - set(configs):       # équipement ou ligne de stock disparus : on retire l'entité
            c.publish(t, "", qos=1, retain=True)
            self._cfg_cache.pop(t, None)
        for t in old_states - set(states):
            c.publish(t, "", qos=1, retain=True)
            self._state_cache.pop(t, None)
        try:
            self.topics_file.write_text(json.dumps({"configs": sorted(configs), "states": sorted(states)}), encoding="utf-8")
        except OSError:
            pass
        self.status = {"state": "connecté", "detail": "Mosquitto", "entities": len(configs)}

    # ----- ordres reçus de Home Assistant -----
    def _cleanup_legacy(self):
        found = sorted(self._legacy)
        for t in found:
            self.client.publish(t, "", qos=1, retain=True)
        self.client.unsubscribe(f"{E.DISCOVERY}/+/{LEGACY_PREFIX}/+/config")
        self.client.unsubscribe(f"{LEGACY_PREFIX}/#")
        self._legacy, self._legacy_at = set(), None
        if found:
            print(f"Removed {len(found)} legacy '{LEGACY_PREFIX}' MQTT entries.")

    def _on_message(self, client, userdata, msg):
        if msg.topic.startswith(LEGACY_PREFIX + "/") or f"/{LEGACY_PREFIX}/" in msg.topic:
            if msg.payload:
                self._legacy.add(msg.topic)
            return
        try:
            self._command(msg.topic, msg.payload.decode("utf-8", "ignore"))
        except Exception:
            traceback.print_exc()

    def _command(self, topic, payload):
        p = topic.split("/")
        if len(p) != 5 or p[0] != E.PREFIX or not ID_RE.match(p[2]):
            return
        kind, ident, what, verb = p[1], p[2], p[3], p[4]
        payload = payload.strip().upper()
        snap = self.store.snapshot()
        eq = next((e for e in snap["equipment"] if e["id"] == ident), None)
        ok, msg = True, ""
        try:
            if (kind, what, verb) == ("equipment", "dead", "set"):
                if not eq:
                    raise logic.ActionError("Équipement introuvable")
                if payload == "ON":
                    msg = f"{eq['name']} : déjà signalé avec des piles mortes" if eq.get("deadSince") else f"{eq['name']} : " + self.store.act("declareDead", {"id": ident})
                elif payload == "OFF":
                    msg = f"{eq['name']} : aucune déclaration en cours" if not eq.get("deadSince") else f"{eq['name']} : " + self.store.act("cancelDead", {"id": ident})
                else:
                    return
            elif (kind, what, verb) == ("equipment", "replace", "press") and payload == "PRESS":
                if not eq:
                    raise logic.ActionError("Équipement introuvable")
                msg = f"{eq['name']} : " + self.store.act("replacePiles", {"id": ident})
            elif (kind, what, verb) == ("stock", "charged", "press") and payload == "PRESS":
                msg = self.store.act("finishCharging", {"lineId": ident})
            else:
                return
        except logic.ActionError as e:
            ok, msg = False, (f"{eq['name']} : " if eq else "") + str(e)
        self.last_return = {"message": msg, "ok": ok, "date": logic.now_iso()}
        self.wake.set()
