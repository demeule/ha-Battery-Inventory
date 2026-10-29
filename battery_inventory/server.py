# -*- coding: utf-8 -*-
"""Serveur Battery Inventory (aucune installation nécessaire : Python seul).

Il garde toutes les données au même endroit (dossier « donnees »), les photos en fichiers,
fait une sauvegarde par jour, et sert l'appli (dossier « web »).

Réglages possibles (variables d'environnement, tu n'en as pas besoin pour tester) :
  BATTERY_PORT  port (8765 par défaut)
  BATTERY_HOST  adresse d'écoute (127.0.0.1 = cet ordinateur seulement)
  BATTERY_DATA  dossier des données
  BATTERY_MQTT  "1" pour activer la liaison Home Assistant (MQTT)
  BATTERY_ALLOWED_CLIENTS  (module Home Assistant) adresses autorisées à parler au serveur
"""
import base64
import binascii
import copy
import json
import os
import re
import shutil
import sys
import threading
import time
import traceback
import uuid
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import logic

HERE = Path(__file__).resolve().parent
WEB = HERE / "web"
MAX_BODY = 30 * 1024 * 1024
UNDO_MAX = 30            # nombre d'actions qu'on peut annuler en remontant
COALESCE_SECONDS = 15    # plusieurs « + » de suite sur la même ligne = une seule annulation
COALESCE = ("adjustStock", "setMinimum")
DATA_URL_RE = re.compile(r"^data:image/[a-zA-Z+.\-]+;base64,(.+)$", re.S)
PHOTO_NAME_RE = re.compile(r"^[0-9a-f\-]{36}\.jpg$")


class Store:
    """Les données + les photos, avec un verrou : une seule modification à la fois."""

    def __init__(self, folder):
        self.dir = Path(folder)
        self.photos = self.dir / "photos"
        self.backups = self.dir / "sauvegardes"
        self.file = self.dir / "piles.json"
        self.undo_file = self.dir / "annulations.json"
        for p in (self.dir, self.photos, self.backups):
            p.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.on_change = None  # appelé après chaque modification (liaison Home Assistant)
        self.data = self._load()
        self.undo = self._load_undo()

    # ----- pile des actions annulables -----
    def _load_undo(self):
        try:
            j = json.loads(self.undo_file.read_text(encoding="utf-8"))
            return [e for e in j if isinstance(e, dict) and "id" in e and "before" in e][-UNDO_MAX:]
        except (OSError, ValueError):
            return []

    def _save_undo(self):
        try:
            tmp = self.undo_file.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.undo, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, self.undo_file)
        except OSError:
            traceback.print_exc()

    def _undo_info(self):
        if not self.undo:
            return None
        t = self.undo[-1]
        return {"id": t["id"], "label": t["label"], "date": t["date"]}

    # ----- lecture / écriture du fichier -----
    def _load(self):
        if self.file.exists():
            try:
                return logic.normalize(json.loads(self.file.read_text(encoding="utf-8")))
            except (OSError, ValueError) as e:
                stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                aside = self.dir / f"piles.illisible-{stamp}.json"
                try:
                    shutil.copy2(self.file, aside)
                except OSError:
                    pass
                print(f"ATTENTION : le fichier de données était illisible ({e}). Copie gardée : {aside.name}")
                for b in sorted(self.backups.glob("piles-*.json"), reverse=True):
                    try:
                        d = logic.normalize(json.loads(b.read_text(encoding="utf-8")))
                        print(f"Données reprises depuis la sauvegarde {b.name}")
                        return d
                    except (OSError, ValueError):
                        continue
        d = logic.seed_data()
        self._write(d)
        return d

    def _write(self, d):
        tmp = self.file.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, self.file)
        today = self.backups / f"piles-{datetime.now().strftime('%Y-%m-%d')}.json"
        if not today.exists():
            shutil.copy2(self.file, today)
            for old in sorted(self.backups.glob("piles-*.json"))[:-14]:
                old.unlink(missing_ok=True)

    # ----- photos -----
    def save_photo(self, data_url):
        m = DATA_URL_RE.match(data_url or "")
        if not m:
            raise logic.ActionError("Photo invalide")
        try:
            raw = base64.b64decode(m.group(1), validate=False)
        except (binascii.Error, ValueError):
            raise logic.ActionError("Photo invalide")
        if len(raw) > 4 * 1024 * 1024:
            raise logic.ActionError("Photo trop lourde (4 Mo maximum)")
        if not raw.startswith(b"\xff\xd8\xff"):
            raise logic.ActionError("Seules les photos JPEG sont acceptées")
        name = f"{uuid.uuid4()}.jpg"
        (self.photos / name).write_bytes(raw)
        return f"photos/{name}"

    def _drop_missing_photos(self, d):
        for e in d["equipment"]:
            if e["photo"] and not (self.photos / Path(e["photo"]).name).exists():
                e["photo"] = ""

    def _cleanup_photos(self, d):
        used = {Path(e["photo"]).name for e in d["equipment"] if e["photo"]}
        for u in self.undo:  # les photos d'une action annulable restent gardées
            used |= {Path(e["photo"]).name for e in u["before"].get("equipment", []) if e.get("photo")}
        limit = time.time() - 600  # on laisse 10 minutes aux photos pas encore rattachées
        for f in self.photos.glob("*.jpg"):
            try:
                if f.name not in used and f.stat().st_mtime < limit:
                    f.unlink()
            except OSError:
                pass

    # ----- API -----
    def snapshot(self):
        with self.lock:
            return copy.deepcopy(self.data)

    def state_json(self, since=None):
        with self.lock:
            if since is not None and since == self.data["revision"]:
                return json.dumps({"unchanged": True, "revision": since})
            out = dict(self.data)
            out["undo"] = self._undo_info()
            out["undoCount"] = len(self.undo)
            return json.dumps(out, ensure_ascii=False)

    def export_json(self):
        """Sauvegarde complète : les photos sont intégrées au fichier."""
        with self.lock:
            d = copy.deepcopy(self.data)
        for e in d["equipment"]:
            if e["photo"]:
                try:
                    raw = (self.photos / Path(e["photo"]).name).read_bytes()
                    e["photo"] = "data:image/jpeg;base64," + base64.b64encode(raw).decode("ascii")
                except OSError:
                    e["photo"] = ""
        return json.dumps(d, ensure_ascii=False, indent=1)

    def act(self, name, args):
        return self.act_ex(name, args)[0]

    def act_ex(self, name, args):
        """Applique une action. Renvoie (message, annulation) ; annulation = {id, label} ou None."""
        if not isinstance(args, dict):
            raise logic.ActionError("Demande invalide")
        with self.lock:
            if name == "undo":
                return self._undo(args.get("id")), None
            old = self.data
            if name == "import":
                d, msg = self._import(args.get("data")), "Sauvegarde restaurée"
            else:
                d, msg = logic.apply(old, name, args)
                self._drop_missing_photos(d)
            if d == old:   # rien n'a changé : on n'écrit rien et on ne crée pas d'annulation
                return msg, None
            label = logic.undo_label(name, args, old, d)
            d["revision"] = old["revision"] + 1
            self._write(d)   # si l'écriture échoue, self.data reste intact
            self.data = d
            info = self._push_undo(name, args, old, d, label)
            self._cleanup_photos(d)
            if self.on_change:
                try:
                    self.on_change()
                except Exception:
                    traceback.print_exc()
            return msg, info

    def _push_undo(self, name, args, old, new, label):
        now = time.time()
        key = args.get("lineId") if name in COALESCE else None
        top = self.undo[-1] if self.undo else None
        if top and key and top.get("name") == name and top.get("key") == key and now - top["ts"] < COALESCE_SECONDS:
            # même ligne de stock, quelques secondes plus tard : on fusionne avec l'annulation précédente
            fake_after = new
            top["label"] = logic.undo_label(name, args, top["before"], fake_after)
            top["ts"] = now
            same = {k: v for k, v in top["before"].items() if k != "revision"} == {k: v for k, v in new.items() if k not in ("revision", "history")}
            if same:   # retour au point de départ : plus rien à annuler
                self.undo.pop()
                self._save_undo()
                return None
            self._save_undo()
            return {"id": top["id"], "label": top["label"]}
        entry = {"id": logic.uid(), "ts": now, "date": logic.now_iso(), "name": name, "key": key, "label": label,
                 "before": {k: v for k, v in old.items() if k != "history"}}
        n = len(new["history"]) - len(old["history"])
        if n >= 0 and new["history"][n:] == old["history"]:
            entry["historyAdded"] = n          # l'action n'a fait qu'ajouter des lignes en tête de l'historique
        else:
            entry["history"] = old["history"]  # l'action a réécrit l'historique : on le garde en entier
        self.undo.append(entry)
        del self.undo[:-UNDO_MAX]
        self._save_undo()
        return {"id": entry["id"], "label": label}

    def _undo(self, ident):
        if not self.undo:
            raise logic.ActionError("Il n'y a rien à annuler.")
        top = self.undo[-1]
        if ident and top["id"] != ident:
            raise logic.ActionError("Cette action n'est plus la dernière : une autre modification a eu lieu depuis. "
                                    "Utilise « Annuler la dernière action » dans l'onglet Historique.")
        restored = copy.deepcopy(top["before"])
        restored["history"] = copy.deepcopy(self.data["history"][top["historyAdded"]:] if "historyAdded" in top else top["history"])
        restored["revision"] = self.data["revision"] + 1
        self._drop_missing_photos(restored)
        self._write(restored)
        self.data = restored
        self.undo.pop()
        self._save_undo()
        self._cleanup_photos(restored)
        if self.on_change:
            try:
                self.on_change()
            except Exception:
                traceback.print_exc()
        return f"Annulé : {top['label']}"

    def _import(self, raw):
        if not isinstance(raw, dict) or not isinstance(raw.get("stock"), list) or not isinstance(raw.get("equipment"), list):
            raise logic.ActionError("Ce fichier n'est pas une sauvegarde Battery Inventory")
        if len(raw["equipment"]) > 2000 or len(raw["stock"]) > 500:
            raise logic.ActionError("Sauvegarde trop volumineuse")
        d = logic.normalize({**raw, "demo": False})
        for e in d["equipment"]:
            p = e["photo"]
            if p.startswith("data:"):
                try:
                    e["photo"] = self.save_photo(p)
                except logic.ActionError:
                    e["photo"] = ""
            elif not logic.PHOTO_RE.match(p):
                e["photo"] = ""
        self._drop_missing_photos(d)
        return d


class Handler(BaseHTTPRequestHandler):
    server_version = "BatteryInventory"
    store = None
    local_only = True
    bridge = None           # liaison Home Assistant (None sur le PC)
    allowed_clients = None  # ex. {"172.30.32.2"} : seul Home Assistant peut parler au serveur

    def log_message(self, fmt, *args):  # on garde la fenêtre silencieuse
        pass

    # ----- réponses -----
    def _send(self, status, body, ctype, extra=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status, obj):
        self._send(status, json.dumps(obj, ensure_ascii=False), "application/json; charset=utf-8")

    def _host_ok(self):
        if self.allowed_clients and self.client_address[0] not in self.allowed_clients:
            return False
        if not self.local_only:
            return True
        host = (self.headers.get("Host") or "").split(":")[0].lower()
        return host in ("localhost", "127.0.0.1", "[::1]", "")

    # ----- GET -----
    def do_GET(self):
        if not self._host_ok():
            return self._json(403, {"error": "Adresse non autorisée"})
        url = urlparse(self.path)
        path = url.path
        try:
            if path in ("/", "/index.html"):
                page = WEB / "index.html"
                if not page.exists():
                    return self._send(500, "Fichier web/index.html manquant", "text/plain; charset=utf-8")
                html = page.read_bytes()
                # Dans Home Assistant, la page vit sous une adresse du type /api/hassio_ingress/xxxx/ :
                # on dit au navigateur de partir de là pour retrouver les données et les photos.
                base = (self.headers.get("X-Ingress-Path") or "").strip()
                if re.fullmatch(r"/[A-Za-z0-9/_\-.]*", base):
                    tag = f'<head><base href="{base.rstrip("/")}/">'.encode("utf-8")
                    html = html.replace(b"<head>", tag, 1)
                return self._send(200, html, "text/html; charset=utf-8")
            if path == "/api/state":
                since = parse_qs(url.query).get("since", [None])[0]
                since = int(since) if since is not None and since.lstrip("-").isdigit() else None
                return self._send(200, self.store.state_json(since), "application/json; charset=utf-8")
            if path == "/api/mqtt":
                if self.bridge is None:
                    return self._json(200, {"state": "désactivé", "entities": 0,
                                            "detail": "Disponible quand l'appli tourne dans Home Assistant."})
                return self._json(200, self.bridge.status)
            if path == "/api/export":
                name = f"mes-piles-{datetime.now().strftime('%Y-%m-%d')}.json"
                return self._send(200, self.store.export_json(), "application/json; charset=utf-8",
                                  {"Content-Disposition": f'attachment; filename="{name}"'})
            if path.startswith("/photos/"):
                name = path[len("/photos/"):]
                f = self.store.photos / name
                if PHOTO_NAME_RE.match(name) and f.is_file():
                    return self._send(200, f.read_bytes(), "image/jpeg", {"Cache-Control": "public, max-age=31536000, immutable"})
            return self._json(404, {"error": "Introuvable"})
        except Exception:
            traceback.print_exc()
            return self._json(500, {"error": "Erreur interne du serveur"})

    # ----- POST -----
    def do_POST(self):
        if not self._host_ok():
            return self._json(403, {"error": "Adresse non autorisée"})
        # Exiger du JSON empêche une page web quelconque d'envoyer des ordres à ce serveur.
        if not (self.headers.get("Content-Type") or "").startswith("application/json"):
            return self._json(415, {"error": "Format de demande non accepté"})
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        if n <= 0 or n > MAX_BODY:
            return self._json(413, {"error": "Demande trop volumineuse"})
        try:
            body = json.loads(self.rfile.read(n).decode("utf-8"))
            if not isinstance(body, dict):
                raise ValueError
        except (ValueError, UnicodeDecodeError):
            return self._json(400, {"error": "Demande illisible"})
        path = urlparse(self.path).path
        try:
            if path == "/api/action":
                msg, undo = self.store.act_ex(str(body.get("action", "")), body.get("args") or {})
                return self._send(200, json.dumps({"ok": True, "message": msg, "undo": undo, "state": json.loads(self.store.state_json())},
                                                  ensure_ascii=False), "application/json; charset=utf-8")
            if path == "/api/photo":
                return self._json(200, {"path": self.store.save_photo(body.get("dataUrl"))})
            return self._json(404, {"error": "Introuvable"})
        except logic.ActionError as e:
            return self._json(400, {"error": str(e)})
        except Exception:
            traceback.print_exc()
            return self._json(500, {"error": "Erreur interne du serveur"})


def make_server(folder, host="127.0.0.1", port=8765, allowed=None):
    store = Store(folder)

    class H(Handler):
        pass

    H.store = store
    H.local_only = host in ("127.0.0.1", "localhost", "::1")
    H.allowed_clients = set(allowed) if allowed else None
    class Server(ThreadingHTTPServer):
        request_queue_size = 64   # plusieurs appareils peuvent écrire en même temps
        daemon_threads = True

    return Server((host, port), H), store


def main():
    host = os.environ.get("BATTERY_HOST", "127.0.0.1")
    port = int(os.environ.get("BATTERY_PORT", "8765"))
    folder = os.environ.get("BATTERY_DATA", str(HERE / "data"))
    url = f"http://localhost:{port}/"
    allowed = [x.strip() for x in os.environ.get("BATTERY_ALLOWED_CLIENTS", "").split(",") if x.strip()]
    try:
        httpd, store = make_server(folder, host, port, allowed)
    except OSError:
        print(f"Le port {port} est déjà utilisé : Battery Inventory est sans doute déjà lancé.")
        print(f"Adresse : {url}")
        if "--ouvrir" in sys.argv:
            webbrowser.open(url)
        return 1
    if os.environ.get("BATTERY_MQTT") == "1":
        import ha_mqtt
        bridge = ha_mqtt.Bridge(store)
        store.on_change = bridge.notify
        httpd.RequestHandlerClass.bridge = bridge
        bridge.start()
    print("=" * 56)
    print(" Battery Inventory is running.")
    print(f" Address : {url}")
    print(f" Data    : {store.dir}")
    print(" Keep this window open while you use the app.")
    print(" To stop: close this window or press Ctrl+C.")
    print("=" * 56)
    if "--ouvrir" in sys.argv:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("Arrêt.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
