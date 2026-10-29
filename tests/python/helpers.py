# -*- coding: utf-8 -*-
"""Outils communs aux tests : chemins, port libre, serveur et Mosquitto de test."""
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ADDON = ROOT / "battery_inventory"
sys.path.insert(0, str(ADDON))


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def tmpdir(prefix="battery-test-"):
    return tempfile.mkdtemp(prefix=prefix)


def start_server(data_dir, port=None, extra_env=None, seed_file=None):
    """Lance server.py dans un processus séparé ; renvoie (processus, adresse)."""
    port = port or free_port()
    env = dict(os.environ, BATTERY_PORT=str(port), BATTERY_DATA=str(data_dir), PYTHONUNBUFFERED="1", **(extra_env or {}))
    if seed_file:
        os.makedirs(data_dir, exist_ok=True)
        shutil.copy(seed_file, Path(data_dir) / "piles.json")
    log = open(Path(tempfile.gettempdir()) / f"battery-server-{port}.log", "w")
    proc = subprocess.Popen([sys.executable, str(ADDON / "server.py")], env=env, stdout=log, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}/"
    for _ in range(100):
        try:
            urllib.request.urlopen(base + "api/state", timeout=1).read()
            return proc, base
        except Exception:
            time.sleep(0.1)
    proc.kill()
    raise RuntimeError("le serveur ne démarre pas")


def stop(proc):
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def start_mosquitto():
    """Lance un Mosquitto de test sur un port libre ; renvoie (processus, port) ou (None, None) s'il n'est pas installé."""
    exe = shutil.which("mosquitto")
    if not exe:
        return None, None
    port = free_port()
    conf = Path(tempfile.mkdtemp()) / "mosquitto.conf"
    conf.write_text(f"listener {port} 127.0.0.1\nallow_anonymous true\npersistence false\n")
    proc = subprocess.Popen([exe, "-c", str(conf)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            return proc, port
        except OSError:
            time.sleep(0.1)
    proc.kill()
    raise RuntimeError("mosquitto ne démarre pas")


def skip_without_mqtt():
    try:
        import paho.mqtt.client  # noqa: F401
    except ImportError:
        print("SKIP : paho-mqtt n'est pas installé")
        sys.exit(0)
    if not shutil.which("mosquitto"):
        print("SKIP : mosquitto n'est pas installé")
        sys.exit(0)
