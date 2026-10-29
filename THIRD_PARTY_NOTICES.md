# Third-party notices

Battery Inventory is released under the MIT license (see `LICENSE`). It includes or uses the following open-source components.

| Component | Where | License |
|---|---|---|
| React and React DOM 18 | bundled in `battery_inventory/web/index.html` | MIT |
| lucide-react (icons) | bundled in `battery_inventory/web/index.html` | ISC |
| Tailwind CSS 3 (build tool; its generated styles are in `index.html`) | `frontend/` | MIT |
| esbuild (build tool) | `frontend/` | MIT |
| paho-mqtt | installed in the add-on image | Eclipse Public License 2.0 / Eclipse Distribution License 1.0 |
| Python (base image `python:3.12-alpine`) | add-on image | Python Software Foundation License |
| jsdom (tests only) | `tests/` | MIT |

Each component remains under its own license and copyright.
