# Battery Inventory

Keep track of every battery in your home: which equipment uses which batteries, how many you have in stock,
what is dead, what should be replaced soon, and how long batteries really last.

Open the app from the **Batteries** entry in the Home Assistant sidebar (works in the Home Assistant mobile app too).

## What you get

- Equipment cards with photo, location, battery format and type (standard or rechargeable).
- A stock with an alert threshold per format. Replacing batteries takes them out of the stock automatically.
- Dead-battery flags, replacement reminders (every 3, 6, 12 or 24 months) and an **Undo** button (30 steps).
- Lifetime estimates and a yearly shopping estimate, based on your own history.
- Home Assistant entities created automatically through MQTT (sensors, switches, buttons).

## Requirements

The **Mosquitto broker** add-on (or any MQTT broker) for the Home Assistant entities. The app itself works without it.

## Data and backups

Everything is stored in the add-on's data folder, so it is included in Home Assistant backups.
The app also keeps a daily copy for 14 days. In the app: **Settings → Backup** to download or restore a file
(photos included).

## Options

None are needed. The MQTT options exist only for a broker that is not the Mosquitto add-on.

## Support

Issues and ideas: <https://github.com/demeule/ha-Battery-Inventory/issues>
