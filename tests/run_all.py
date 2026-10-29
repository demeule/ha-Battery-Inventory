# -*- coding: utf-8 -*-
"""Lance tous les tests du projet : python tests/run_all.py

Prérequis : Python 3.10+, Node.js 18+ (et `npm install` dans tests/), paho-mqtt et Mosquitto (facultatifs : les tests MQTT sont
ignorés s'ils manquent).
"""
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "python"))
from helpers import ROOT, start_server, stop, tmpdir  # noqa: E402

PY = [
    "test_repo_consistency.py", "test_api.py", "test_undo.py", "test_rappels.py",
    "test_legacy_cleanup.py", "test_mqtt_bridge.py", "test_mqtt_undo_reminders.py",
]
NODE_UNIT = ["test_lifetime.mjs", "test_reminder_parity.mjs"]
UI = [("ui_flow.cjs", False), ("ui_forms.cjs", False), ("ui_undo.cjs", False), ("ui_reminders.cjs", False), ("ui_lifetime.cjs", True)]


def run(name, cmd, env=None):
    t = time.time()
    r = subprocess.run(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    out = r.stdout.strip().splitlines()
    skipped = any(l.startswith("SKIP") for l in out)
    status = "SKIP" if skipped else "OK  " if r.returncode == 0 else "FAIL"
    print(f"{status} {name} ({time.time() - t:.1f} s)" + (f" - {out[-1]}" if skipped else ""))
    if r.returncode != 0:
        print("\n".join("     " + l for l in out[-25:]))
    return r.returncode == 0


def main():
    ok = True
    for f in PY:
        ok &= run(f"python  {f}", [sys.executable, str(HERE / "python" / f)])
    for f in NODE_UNIT:
        ok &= run(f"node    {f}", ["node", str(HERE / "unit" / f)])
    if not (HERE / "node_modules" / "jsdom").exists():
        print("SKIP tests d'interface : lance d'abord `npm install` dans le dossier tests")
    else:
        for f, seeded in UI:
            data = tmpdir()
            seed = None
            if seeded:
                subprocess.run([sys.executable, str(HERE / "fixtures" / "make_demo_data.py"), data], check=True, stdout=subprocess.DEVNULL)
                seed = Path(data) / "piles.json"
            proc, base = start_server(data)
            try:
                ok &= run(f"ui      {f}", ["node", str(HERE / "ui" / f)], env=dict(os.environ, BASE_URL=base))
            finally:
                stop(proc)
    print("\nTOUT PASSE" if ok else "\nDES TESTS ONT ECHOUE")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
