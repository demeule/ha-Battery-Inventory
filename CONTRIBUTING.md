# Contributing

Thanks for helping! Bug reports, ideas, translations and pull requests are all welcome.

## Project layout

| Folder | What it is |
|---|---|
| `battery_inventory/` | The Home Assistant add-on: Python server (`server.py`, `logic.py`, MQTT bridge) and the built interface in `web/index.html` |
| `frontend/` | Source of the interface (React + Tailwind), compiled into a single HTML file |
| `tests/` | Python, Node and interface tests |
| `docs/` | Screenshots used by the README |

## Run the tests

```bash
pip install paho-mqtt==2.1.0 pyyaml pillow      # MQTT tests also need the `mosquitto` program
cd tests && npm install && cd ..
python tests/run_all.py
```

Tests that need Mosquitto or paho-mqtt are skipped when those are missing; CI runs everything.

## Change the interface

```bash
cd frontend
npm install
npm run build        # writes battery_inventory/web/index.html
```

The built file is committed on purpose: Home Assistant builds the add-on from the repository folder and has no Node.js step.
CI fails if `index.html` is not up to date with the sources.

## Run the server on your computer (without Home Assistant)

```bash
python battery_inventory/server.py --ouvrir        # opens http://localhost:8765
```

Data goes to `battery_inventory/data/`. Set `BATTERY_PORT` or `BATTERY_DATA` to change the port or the folder.
There is a one-click launcher for Windows in `tools/run_local.bat`.

## Releasing a new version

1. Update the version in `battery_inventory/config.yaml` **and** in the `Dockerfile` label.
2. Add a section to `battery_inventory/CHANGELOG.md`.
3. `cd frontend && npm run build`, then run the tests.

`tests/python/test_repo_consistency.py` checks that these agree.

## Style

Keep it simple and readable: short functions, comments that explain *why*. All user-facing text is currently French
(English is planned, see the roadmap in the README).
