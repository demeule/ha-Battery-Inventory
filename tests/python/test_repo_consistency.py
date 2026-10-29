# -*- coding: utf-8 -*-
"""Contrôles du dépôt avant publication : versions, fichiers obligatoires, restes de l'ancien nom, informations personnelles."""
import ast, re, sys
from pathlib import Path
from helpers import ROOT, ADDON
import yaml

fails = 0
def ok(c, m):
    global fails
    print(("OK   " if c else "ECHEC") + " " + m)
    if not c: fails += 1

cfg = yaml.safe_load((ADDON / "config.yaml").read_text(encoding="utf8"))
ok(cfg["slug"] == "battery_inventory" and cfg["name"] == "Battery Inventory", "config.yaml : nom et slug")
ok(cfg.get("ingress") is True and cfg.get("ingress_port") == 8099, "config.yaml : ingress sur le port 8099")
allowed = {"name", "version", "slug", "description", "url", "arch", "startup", "boot", "ingress", "ingress_port", "panel_icon",
           "panel_title", "panel_admin", "hassio_api", "services", "options", "schema", "init", "map", "image", "ports", "backup"}
ok(set(cfg) <= allowed, "config.yaml : seulement des clés connues de Home Assistant" + ("" if set(cfg) <= allowed else f" (inconnues : {set(cfg) - allowed})"))
ok(set(cfg["options"]) == set(cfg["schema"]), "options et schema décrivent les mêmes champs")
version = cfg["version"]
docker = (ADDON / "Dockerfile").read_text(encoding="utf8")
ok(f'io.hass.version="{version}"' in docker, "Dockerfile : même version que config.yaml (" + version + ")")
ok("FROM python:" in docker and "BUILD_FROM" not in docker, "Dockerfile : image de départ explicite")
ok(re.search(rf"^## {re.escape(version)}\b", (ADDON / "CHANGELOG.md").read_text(encoding="utf8"), re.M) is not None, "CHANGELOG.md : une section pour la version " + version)
repo = yaml.safe_load((ROOT / "repository.yaml").read_text(encoding="utf8"))
ok(repo["url"] == "https://github.com/demeule/ha-Battery-Inventory" and repo["name"], "repository.yaml : nom et adresse du dépôt")
for f in ("DOCS.md", "CHANGELOG.md", "icon.png", "logo.png", "translations/en.yaml", "translations/fr.yaml", "run.sh", "web/index.html", "server.py", "logic.py", "ha_entities.py", "ha_mqtt.py"):
    ok((ADDON / f).exists(), f"module : {f} présent")
for f in ("README.md", "README.fr.md", "LICENSE", "CONTRIBUTING.md", "SECURITY.md", ".gitignore", ".github/workflows/tests.yml", ".github/FUNDING.yml"):
    ok((ROOT / f).exists(), f"dépôt : {f} présent")
from PIL import Image
im = Image.open(ADDON / "icon.png"); ok(im.size == (128, 128), "icon.png : 128 x 128")
lg = Image.open(ADDON / "logo.png"); ok(lg.size[0] <= 250 and lg.size[1] <= 100, f"logo.png : {lg.size} (250 x 100 maximum)")
ok("MIT License" in (ROOT / "LICENSE").read_text(encoding="utf8") and "demeule" in (ROOT / "LICENSE").read_text(encoding="utf8"), "LICENSE : MIT au nom de demeule")
for py in ADDON.glob("*.py"):
    ast.parse(py.read_text(encoding="utf8"))
ok(True, "les fichiers Python se lisent sans erreur")
# --- restes de l'ancien nom (« Mes Piles », mes_piles) : seule la migration automatique a le droit d'en parler
skip = {"node_modules", ".git", "dist"}
texts = [p for p in ROOT.rglob("*") if p.is_file() and not (set(p.relative_to(ROOT).parts) & skip) and p.suffix in {".py", ".js", ".jsx", ".cjs", ".mjs", ".md", ".yaml", ".yml", ".json", ".css", ".sh", ".html"} and p.name != "package-lock.json"]
old = []
for p in texts:
    t = p.read_text(encoding="utf8", errors="ignore")
    for needle in ("Mes Piles", "mes_piles", "MesPiles"):
        if needle in t:
            old.append((p.relative_to(ROOT).as_posix(), needle))
allowed_old = {("battery_inventory/ha_mqtt.py", "mes_piles"), ("tests/python/test_legacy_cleanup.py", "mes_piles"), ("tests/python/test_repo_consistency.py", "Mes Piles"),
               ("tests/python/test_repo_consistency.py", "mes_piles"), ("tests/python/test_repo_consistency.py", "MesPiles"), ("README.md", "mes_piles"), ("README.fr.md", "mes_piles"),
               ("README.fr.md", "Mes Piles"), ("README.md", "Mes Piles"), ("CHANGELOG.md", "mes_piles")}
rest = [x for x in old if x not in allowed_old]
ok(not rest, "aucun reste de l'ancien nom hors migration" + ("" if not rest else f" : {rest[:5]}"))
# --- informations personnelles ou adresses privées
bad = []
priv = re.compile(r"\b(192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+)\b")
for p in texts:
    t = p.read_text(encoding="utf8", errors="ignore")
    for m in priv.finditer(t):
        if m.group(0) != "172.30.32.2" and not p.name.startswith("test_"):
            bad.append((p.relative_to(ROOT).as_posix(), m.group(0)))
    for needle in ("maison-demeule", "D:\\_temp", "token", "password="):
        if needle in t and p.suffix != ".md" and "test" not in p.name and "package-lock" not in p.name and p.name not in {"ha_mqtt.py", "server.py", "config.yaml"} and "SUPERVISOR_TOKEN" not in t:
            bad.append((p.relative_to(ROOT).as_posix(), needle))
ok(not bad, "aucune adresse privée ni information personnelle" + ("" if not bad else f" : {bad[:5]}"))
# --- les identifiants d'entités cités dans la documentation existent vraiment
import ha_entities, logic
cfgs, _ = ha_entities.build(logic.seed_data())
ids = {c["default_entity_id"] for c in cfgs.values()}
cited = set()
for f in ("README.md", "README.fr.md", "docs/dashboard-card.yaml"):
    for m in re.finditer(r"\b((?:sensor|binary_sensor|switch|button)\.battery_[a-z0-9_]+)(?![a-z0-9_<])", (ROOT / f).read_text(encoding="utf8")):
        if not m.group(1).endswith("_"):
            cited.add(m.group(1))
missing = sorted(x for x in cited if x not in ids)
ok(len(cited) >= 8 and not missing, f"entités citées dans la documentation : {len(cited)} trouvées, manquantes : {missing}")
print("TOUT PASSE" if not fails else f"{fails} ECHEC(S)")
sys.exit(1 if fails else 0)
