# -*- coding: utf-8 -*-
"""Construit la liste des capteurs, interrupteurs et boutons que Battery Inventory montre à Home Assistant.

Aucune connexion ici : on transforme seulement les données de l'appli en messages « découverte MQTT »
(ce qui crée les entités dans Home Assistant) et en états (ce qu'elles affichent).
"""
import json
import re
import unicodedata

import logic

PREFIX = "battery_inventory"
DISCOVERY = "homeassistant"
STATUS_TOPIC = f"{PREFIX}/status"
MAKER = "Battery Inventory"


def slug(text):
    t = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "_", t).strip("_") or "sans_nom"


def tw(rechargeable):
    return "rechargeable" if rechargeable else "standard"


def _dumps(x):
    return json.dumps(x, ensure_ascii=False)


ROOT_DEVICE = {"identifiers": ["battery_inventory_root"], "name": "Battery Inventory", "manufacturer": MAKER, "model": "Inventaire des piles"}
STOCK_DEVICE = {"identifiers": ["battery_inventory_stock"], "name": "Battery stock", "manufacturer": MAKER, "model": "Réserve",
                "via_device": "battery_inventory_root"}


def _entity(configs, component, obj, eid, name, device, **extra):
    topic = f"{DISCOVERY}/{component}/{PREFIX}/{obj}/config"
    cfg = {
        "name": name,
        "unique_id": f"{PREFIX}_{obj}",
        "default_entity_id": f"{component}.{eid}",
        "availability_topic": STATUS_TOPIC,
        "payload_available": "online",
        "payload_not_available": "offline",
        "device": device,
    }
    cfg.update(extra)
    configs[topic] = cfg
    return cfg


def build(d, last_return=None, today=None):
    """Renvoie (configs, states) : {topic: dict} et {topic: texte}."""
    configs, states = {}, {}
    stock = d["stock"]
    equipment = d["equipment"]

    low = [x for x in stock if x["quantity"] <= x["minimum"]]
    dead = [e for e in equipment if e.get("deadSince")]
    low_list = [f"{x['format']} {tw(x['rechargeable'])} ({x['quantity']})" for x in low]
    dead_list = [e["name"] for e in dead]
    remind = []   # équipements dont le rappel de remplacement est proche ou dépassé
    for e in equipment:
        info = logic.reminder_info(e, today)
        if info and info["status"] in ("soon", "due"):
            remind.append((e, info))
    remind_list = [f"{e['name']} (dans {i['days']} jours)" if i["days"] > 0 else f"{e['name']} (échéance atteinte)" for e, i in remind]

    g = f"{PREFIX}/global"
    low_attrs, dead_attrs, remind_attrs = f"{g}/low_attrs", f"{g}/dead_attrs", f"{g}/remind_attrs"

    def gsensor(key, eid, name, value, icon, attrs=None):
        extra = {"state_topic": f"{g}/{key}", "icon": icon, "unit_of_measurement": "piles" if "stock" in key or "installed" in key else None}
        if extra["unit_of_measurement"] is None:
            del extra["unit_of_measurement"]
        else:
            extra["state_class"] = "measurement"
        if attrs:
            extra["json_attributes_topic"] = attrs
        _entity(configs, "sensor", f"global_{key}", eid, name, ROOT_DEVICE, **extra)
        states[f"{g}/{key}"] = str(value)

    gsensor("total_stock", "battery_total_stock", "Total en stock", sum(x["quantity"] for x in stock), "mdi:battery-multiple")
    gsensor("total_installed", "battery_total_installed", "Total installées", sum(e["quantity"] for e in equipment), "mdi:battery-check")
    gsensor("n_equipment", "battery_equipment_count", "Nombre d'équipements", len(equipment), "mdi:devices")
    gsensor("n_low", "battery_low_stock_count", "Stocks faibles", len(low), "mdi:battery-alert-variant-outline", low_attrs)
    gsensor("n_dead", "battery_dead_count", "Équipements à piles mortes", len(dead), "mdi:battery-off-outline", dead_attrs)

    _entity(configs, "binary_sensor", "global_alert_low", "battery_low_stock_alert", "Alerte stock faible", ROOT_DEVICE,
            state_topic=f"{g}/alert_low", device_class="problem", json_attributes_topic=low_attrs)
    states[f"{g}/alert_low"] = "ON" if low else "OFF"
    _entity(configs, "binary_sensor", "global_alert_dead", "battery_dead_alert", "Alerte piles mortes", ROOT_DEVICE,
            state_topic=f"{g}/alert_dead", device_class="problem", json_attributes_topic=dead_attrs)
    states[f"{g}/alert_dead"] = "ON" if dead else "OFF"
    gsensor("n_remind", "battery_reminder_count", "Rappels de remplacement", len(remind), "mdi:calendar-clock", remind_attrs)
    _entity(configs, "binary_sensor", "global_alert_remind", "battery_reminder_alert", "Alerte rappels de remplacement", ROOT_DEVICE,
            state_topic=f"{g}/alert_remind", device_class="problem", json_attributes_topic=remind_attrs)
    states[f"{g}/alert_remind"] = "ON" if remind else "OFF"
    states[remind_attrs] = _dumps({"items": remind_list, "text": ", ".join(remind_list)})
    states[low_attrs] = _dumps({"items": low_list, "text": ", ".join(low_list)})
    states[dead_attrs] = _dumps({"items": dead_list, "text": ", ".join(dead_list)})

    lr = last_return or {}
    _entity(configs, "sensor", "global_last_return", "battery_last_result", "Dernier retour", ROOT_DEVICE,
            state_topic=f"{g}/last_return", json_attributes_topic=f"{g}/last_return_attrs", icon="mdi:message-text-outline")
    states[f"{g}/last_return"] = (lr.get("message") or "Aucune commande reçue")[:250]
    states[f"{g}/last_return_attrs"] = _dumps({"ok": lr.get("ok"), "date": lr.get("date")})

    # ----- un appareil par équipement -----
    counts = {}
    for e in equipment:
        counts[slug(e["name"])] = counts.get(slug(e["name"]), 0) + 1
    for e in equipment:
        s = slug(e["name"])
        if counts[s] > 1:
            s = f"{s}_{slug(e['id'])[:4]}"
        base = f"{PREFIX}/equipment/{e['id']}"
        dev = {"identifiers": [f"battery_inventory_eq_{e['id']}"], "name": e["name"], "manufacturer": MAKER,
               "model": f"{e['format']} {tw(e['rechargeable'])}", "via_device": "battery_inventory_root"}
        _entity(configs, "switch", f"eq_{e['id']}_dead", f"battery_{s}_dead", "Piles mortes", dev,
                state_topic=f"{base}/dead", command_topic=f"{base}/dead/set", payload_on="ON", payload_off="OFF",
                state_on="ON", state_off="OFF", json_attributes_topic=f"{base}/attrs", icon="mdi:battery-alert")
        _entity(configs, "button", f"eq_{e['id']}_replace", f"battery_{s}_replace", "Remplacer les piles", dev,
                command_topic=f"{base}/replace/press", payload_press="PRESS", icon="mdi:battery-sync")
        info = logic.reminder_info(e, today)
        if info:   # un capteur « Rappel » seulement pour les équipements qui en ont un
            _entity(configs, "binary_sensor", f"eq_{e['id']}_remind", f"battery_{s}_reminder", "Rappel de remplacement", dev,
                    state_topic=f"{base}/remind", device_class="problem", json_attributes_topic=f"{base}/remind_attrs",
                    icon="mdi:calendar-clock")
            states[f"{base}/remind"] = "ON" if info["status"] in ("soon", "due") else "OFF"
            states[f"{base}/remind_attrs"] = _dumps({
                "status": info["status"],
                "due_date": info["due"], "days_left": info["days"], "every_months": e.get("reminderMonths"),
            })
        states[f"{base}/dead"] = "ON" if e.get("deadSince") else "OFF"
        states[f"{base}/attrs"] = _dumps({
            "format": e["format"], "type": tw(e["rechargeable"]), "quantity": e["quantity"],
            "location": e["location"], "category": e["category"], "dead_since": e.get("deadSince"),
            "last_change": (e.get("lastChange") or "")[:10] or None,
        })

    # ----- l'appareil « Stock de piles » : une ligne par format et type -----
    for x in stock:
        s = slug(f"{x['format']} {tw(x['rechargeable'])}")
        label = f"{x['format']} {tw(x['rechargeable'])}"
        base = f"{PREFIX}/stock/{x['id']}"
        need = sum(e["quantity"] for e in equipment if e["format"] == x["format"] and e["rechargeable"] == x["rechargeable"])
        _entity(configs, "sensor", f"stock_{x['id']}_qty", f"battery_stock_{s}", label, STOCK_DEVICE,
                state_topic=f"{base}/qty", unit_of_measurement="piles", state_class="measurement",
                json_attributes_topic=f"{base}/attrs", icon="mdi:battery")
        _entity(configs, "binary_sensor", f"stock_{x['id']}_low", f"battery_stock_{s}_low", f"{label} faible", STOCK_DEVICE,
                state_topic=f"{base}/low", device_class="problem")
        states[f"{base}/qty"] = str(x["quantity"])
        states[f"{base}/low"] = "ON" if x["quantity"] <= x["minimum"] else "OFF"
        states[f"{base}/attrs"] = _dumps({
            "format": x["format"], "type": tw(x["rechargeable"]), "threshold": x["minimum"],
            "charging": x["charging"], "low": x["quantity"] <= x["minimum"], "needed_for_full_replacement": need,
        })
        if x["rechargeable"]:
            _entity(configs, "sensor", f"stock_{x['id']}_charging", f"battery_stock_{s}_charging", f"{label} en recharge", STOCK_DEVICE,
                    state_topic=f"{base}/charging", unit_of_measurement="piles", state_class="measurement", icon="mdi:battery-charging")
            _entity(configs, "button", f"stock_{x['id']}_charged", f"battery_stock_{s}_charged", f"{label} recharge terminée", STOCK_DEVICE,
                    command_topic=f"{base}/charged/press", payload_press="PRESS", icon="mdi:battery-check")
            states[f"{base}/charging"] = str(x["charging"])
    return configs, states
