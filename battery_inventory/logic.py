# -*- coding: utf-8 -*-
"""Règles de Battery Inventory : toutes les actions sur les données.

Chaque action reçoit les données (déjà copiées), les modifie, et renvoie un message.
En cas de problème elle lève ActionError avec une phrase en français.
Rien n'est écrit sur le disque ici : c'est le rôle de server.py.
"""
import calendar
import copy
import re
import uuid
from datetime import date, datetime, timedelta, timezone

DEFAULT_FORMATS = ["AAAA", "AAA", "AA", "C", "D", "9V", "CR2032", "CR2025", "LR44"]
DEFAULT_CATEGORIES = ["Jouet", "Télécommande", "Multimédia", "Maison", "Sécurité", "Éclairage", "Autre"]
PHOTO_RE = re.compile(r"^photos/[0-9a-f\-]{36}\.jpg$")


class ActionError(Exception):
    pass


def uid():
    return str(uuid.uuid4())


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def plural(n):
    return "s" if n > 1 else ""


def describe(q, fmt, rechargeable):
    kind = "rechargeable" if rechargeable else "standard"
    return f"{q} pile{plural(q)} {fmt} {kind}{plural(q)}"


def type_label(rechargeable):
    return "Rechargeable" if rechargeable else "Standard"


def line_of(stock, fmt, rechargeable):
    for x in stock:
        if x["format"] == fmt and x["rechargeable"] == rechargeable:
            return x
    return None


def lack(line, need, fmt, rechargeable):
    msg = f"Stock insuffisant : il faut {describe(need, fmt, rechargeable)}, il en reste {line['quantity'] if line else 0}."
    if line and line.get("charging", 0) > 0:
        msg += f" ({line['charging']} en recharge)"
    return msg


def entry(kind, item, **extra):
    e = {
        "id": uid(),
        "date": now_iso(),
        "type": kind,
        "equipmentId": item.get("id") if item else None,
        "equipment": item.get("name") if item and item.get("name") else "Réserve de piles",
        "format": item.get("format", "") if item else "",
        "rechargeable": bool(item.get("rechargeable")) if item else False,
        "quantity": item.get("quantity", 0) if item else 0,
    }
    e.update(extra)
    return e


# ---------- Dates et rappels ----------

SOON_DAYS = 14          # un rappel passe en « bientôt » 14 jours avant l'échéance
REMINDER_MAX_MONTHS = 120


def add_months(d, n):
    """Ajoute n mois à une date (le 31 janvier + 1 mois = fin février)."""
    total = d.year * 12 + (d.month - 1) + n
    y, m = divmod(total, 12)
    m += 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def parse_day(text):
    """'2026-10-27' ou '2026-10-27T21:11:04.123Z' -> date ; None si illisible."""
    try:
        return date.fromisoformat(str(text)[:10])
    except ValueError:
        return None


def today_utc():
    return datetime.now(timezone.utc).date()


def reminder_info(e, today=None):
    """État du rappel d'un équipement, ou None s'il n'en a pas.

    status : ok (loin), soon (dans 14 jours ou moins), due (échéance atteinte), unknown (date du dernier changement inconnue)
    """
    n = e.get("reminderMonths")
    if not n:
        return None
    start = parse_day(e.get("lastChange")) if e.get("lastChange") else None
    if not start:
        return {"status": "unknown", "due": None, "days": None}
    today = today or today_utc()
    due = add_months(start, n)
    days = (due - today).days
    status = "due" if days <= 0 else "soon" if days <= SOON_DAYS else "ok"
    return {"status": status, "due": due.isoformat(), "days": days}


# ---------- Données de départ ----------

def _days_ago(n):
    return (datetime.now(timezone.utc) - timedelta(days=n)).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def seed_data():
    return {
        "version": 2, "revision": 1, "demo": True,
        "stock": [
            {"id": uid(), "format": "AA", "rechargeable": False, "quantity": 12, "minimum": 6, "charging": 0},
            {"id": uid(), "format": "AAA", "rechargeable": False, "quantity": 6, "minimum": 4, "charging": 0},
            {"id": uid(), "format": "CR2032", "rechargeable": False, "quantity": 2, "minimum": 2, "charging": 0},
            {"id": uid(), "format": "AA", "rechargeable": True, "quantity": 4, "minimum": 2, "charging": 0},
        ],
        "equipment": [
            {"id": uid(), "name": "Train en bois", "category": "Jouet", "location": "Chambre", "format": "AA",
             "rechargeable": True, "quantity": 3, "photo": "", "deadSince": None,
             "lastChange": _days_ago(40), "reminderMonths": None},
            {"id": uid(), "name": "Télécommande TV", "category": "Télécommande", "location": "Salon", "format": "AAA",
             "rechargeable": False, "quantity": 2, "photo": "", "deadSince": None,
             "lastChange": _days_ago(40), "reminderMonths": None},
        ],
        "history": [],
        "formats": list(DEFAULT_FORMATS),
        "categories": list(DEFAULT_CATEGORIES),
    }


def empty_data(revision=1):
    return {"version": 2, "revision": revision, "demo": False, "stock": [], "equipment": [], "history": [],
            "formats": list(DEFAULT_FORMATS), "categories": list(DEFAULT_CATEGORIES)}


def _int(x, default=0):
    try:
        return int(x)
    except (TypeError, ValueError):
        return default


def _reminder_value(x):
    try:
        n = int(x)
    except (TypeError, ValueError):
        return None
    return n if 1 <= n <= REMINDER_MAX_MONTHS else None


def normalize(d):
    """Remet des données lues (fichier, sauvegarde importée) dans la forme attendue."""
    lst = lambda k: [x for x in (d.get(k) or []) if isinstance(x, dict)]
    out = {
        "version": 2,
        "revision": max(1, _int(d.get("revision"), 1)),
        "demo": bool(d.get("demo")),
        "stock": [], "equipment": [], "history": lst("history"),
        "formats": [str(x) for x in (d.get("formats") or [])] or list(DEFAULT_FORMATS),
        "categories": [str(x) for x in (d.get("categories") or [])] or list(DEFAULT_CATEGORIES),
    }
    for x in lst("stock"):
        out["stock"].append({
            "id": x["id"] if isinstance(x.get("id"), str) and re.match(r"^[A-Za-z0-9_\-]{1,64}$", x["id"]) else uid(), "format": str(x.get("format", "")), "rechargeable": bool(x.get("rechargeable")),
            "quantity": max(0, _int(x.get("quantity"))), "minimum": max(0, _int(x.get("minimum"))),
            "charging": max(0, _int(x.get("charging"))),
        })
    safe = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")
    renamed = {}
    last_event = {}
    for h in out["history"]:
        if h.get("type") in ("installation", "remplacement") and h.get("equipmentId") and h.get("date"):
            last_event[h["equipmentId"]] = max(last_event.get(h["equipmentId"], ""), str(h["date"]))
    for x in lst("equipment"):
        old_id = x.get("id")
        new_id = old_id if isinstance(old_id, str) and safe.match(old_id) else uid()
        if old_id and new_id != old_id:
            renamed[old_id] = new_id
        out["equipment"].append({
            "id": new_id, "name": str(x.get("name", "")).strip() or "Sans nom",
            "category": str(x.get("category", "Autre")), "location": str(x.get("location", "")),
            "format": str(x.get("format", "")), "rechargeable": bool(x.get("rechargeable")),
            "quantity": max(1, _int(x.get("quantity"), 1)), "photo": str(x.get("photo") or ""),
            "deadSince": x.get("deadSince") or None,
            "lastChange": x.get("lastChange") or last_event.get(old_id) or None,
            "reminderMonths": _reminder_value(x.get("reminderMonths")),
        })
    for h in out["history"]:
        h.setdefault("id", uid())
        if h.get("equipmentId") in renamed:
            h["equipmentId"] = renamed[h["equipmentId"]]
    return out


# ---------- Vérification des champs envoyés par l'appli ----------

def clean_equipment(d, v):
    if not isinstance(v, dict):
        raise ActionError("Données d'équipement invalides")
    name = str(v.get("name", "")).strip()
    location = str(v.get("location", "")).strip()
    if not name:
        raise ActionError("Le nom est obligatoire")
    if not location:
        raise ActionError("L'emplacement est obligatoire")
    if len(name) > 80 or len(location) > 80:
        raise ActionError("Nom ou emplacement trop long (80 caractères maximum)")
    fmt = str(v.get("format", ""))
    if fmt not in d["formats"]:
        raise ActionError("Format inconnu : ajoute-le d'abord dans les paramètres")
    category = str(v.get("category", ""))
    if category not in d["categories"]:
        raise ActionError("Catégorie inconnue : ajoute-la d'abord dans les paramètres")
    q = v.get("quantity")
    if isinstance(q, bool) or not isinstance(q, int) or q < 1 or q > 99:
        raise ActionError("Le nombre de piles doit être un nombre entier entre 1 et 99")
    photo = str(v.get("photo") or "")
    if photo and not PHOTO_RE.match(photo):
        photo = ""
    out = {"name": name, "location": location, "format": fmt, "category": category,
           "rechargeable": bool(v.get("rechargeable")), "quantity": q, "photo": photo}
    if "lastChange" in v:          # absent = on ne touche pas ; vide = date inconnue
        raw = v.get("lastChange")
        if raw in (None, ""):
            out["lastChange"] = None
        else:
            day = parse_day(raw)
            if not day:
                raise ActionError("La date du dernier changement n'est pas valide")
            if day > today_utc() + timedelta(days=1):
                raise ActionError("La date du dernier changement ne peut pas être dans le futur")
            out["lastChange"] = f"{day.isoformat()}T12:00:00.000Z" if len(str(raw)) <= 10 else str(raw)
    if "reminderMonths" in v:
        raw = v.get("reminderMonths")
        if raw in (None, "", 0):
            out["reminderMonths"] = None
        else:
            if isinstance(raw, bool) or not isinstance(raw, int) or not 1 <= raw <= REMINDER_MAX_MONTHS:
                raise ActionError(f"Le rappel doit être un nombre de mois entre 1 et {REMINDER_MAX_MONTHS}")
            out["reminderMonths"] = raw
    return out


def _find(d, key, value, label="Équipement introuvable"):
    for x in d[key]:
        if x["id"] == value:
            return x
    raise ActionError(label)


# ---------- Équipements ----------

def add_equipment(d, a):
    v = clean_equipment(d, a.get("v"))
    line = line_of(d["stock"], v["format"], v["rechargeable"])
    if not line or line["quantity"] < v["quantity"]:
        raise ActionError(lack(line, v["quantity"], v["format"], v["rechargeable"]))
    item = {**v, "id": uid(), "deadSince": None}
    if "lastChange" not in v:
        item["lastChange"] = now_iso()
    item.setdefault("reminderMonths", None)
    line["quantity"] -= v["quantity"]
    d["equipment"].append(item)
    d["history"].insert(0, entry("installation", item))
    return "Équipement ajouté, stock déduit"


def edit_equipment(d, a):
    raw = a.get("v") or {}
    prev = _find(d, "equipment", raw.get("id"))
    v = clean_equipment(d, raw)
    p_fmt, p_rech, p_q = prev["format"], prev["rechargeable"], prev["quantity"]
    same_line = p_fmt == v["format"] and p_rech == v["rechargeable"]
    changed = (not same_line) or p_q != v["quantity"]
    if changed:
        old_line = line_of(d["stock"], p_fmt, p_rech)
        new_line = line_of(d["stock"], v["format"], v["rechargeable"])
        if same_line:
            diff = v["quantity"] - p_q
            if diff > 0 and (not new_line or new_line["quantity"] < diff):
                kind = "rechargeable" if v["rechargeable"] else "standard"
                raise ActionError(f"Stock insuffisant : il faut {diff} pile{plural(diff)} {v['format']} {kind}{plural(diff)} "
                                  f"de plus, il en reste {new_line['quantity'] if new_line else 0}.")
            if new_line:
                new_line["quantity"] -= diff
        else:
            if not new_line or new_line["quantity"] < v["quantity"]:
                raise ActionError(lack(new_line, v["quantity"], v["format"], v["rechargeable"]))
            new_line["quantity"] -= v["quantity"]
            if old_line:
                old_line["quantity"] += p_q
    prev.update(v)  # deadSince et id restent inchangés
    for h in d["history"]:
        if h.get("equipmentId") == prev["id"]:
            h["equipment"] = prev["name"]
    if changed:
        note = f"Avant : {p_q} × {p_fmt} {type_label(p_rech).lower()}"
        d["history"].insert(0, entry("modification", prev, note=note))
    return "Équipement modifié, stock corrigé" if changed else "Équipement modifié"


def delete_equipment(d, a):
    item = _find(d, "equipment", a.get("id"))
    give_back = bool(a.get("giveBack"))
    if give_back:
        line = line_of(d["stock"], item["format"], item["rechargeable"])
        if line:
            line["quantity"] += item["quantity"]
        else:
            d["stock"].append({"id": uid(), "format": item["format"], "rechargeable": item["rechargeable"],
                               "quantity": item["quantity"], "minimum": 2, "charging": 0})
    d["equipment"] = [x for x in d["equipment"] if x["id"] != item["id"]]
    note = "Piles remises en stock" if give_back else "Piles non remises en stock"
    d["history"].insert(0, entry("suppression", item, note=note))
    return "Équipement supprimé, piles remises en stock" if give_back else "Équipement supprimé"


def replace_piles(d, a):
    item = _find(d, "equipment", a.get("id"))
    line = line_of(d["stock"], item["format"], item["rechargeable"])
    if not line or line["quantity"] < item["quantity"]:
        raise ActionError(lack(line, item["quantity"], item["format"], item["rechargeable"]))
    was_dead = bool(item.get("deadSince"))
    line["quantity"] -= item["quantity"]
    if item["rechargeable"]:  # les anciennes piles rechargeables partent en recharge
        line["charging"] += item["quantity"]
    item["deadSince"] = None
    item["lastChange"] = now_iso()
    d["history"].insert(0, entry("remplacement", item))
    return "Piles mortes remplacées, stock déduit" if was_dead else "Remplacement enregistré, stock déduit"


def declare_dead(d, a):
    item = _find(d, "equipment", a.get("id"))
    if item.get("deadSince"):
        raise ActionError("Cet équipement est déjà signalé avec des piles mortes")
    item["deadSince"] = now_iso()
    d["history"].insert(0, entry("mortes", item))
    q = item["quantity"]
    return f"{describe(q, item['format'], item['rechargeable'])} déclarée{plural(q)} morte{plural(q)}"


def cancel_dead(d, a):
    item = _find(d, "equipment", a.get("id"))
    if not item.get("deadSince"):
        raise ActionError("Aucune déclaration à annuler")
    item["deadSince"] = None
    d["history"].insert(0, entry("annulation", item))
    return "Déclaration de piles mortes annulée"


# ---------- Stock ----------

def add_stock(d, a):
    v = a.get("v") or {}
    fmt = str(v.get("format", ""))
    if fmt not in d["formats"]:
        raise ActionError("Format inconnu : ajoute-le d'abord dans les paramètres")
    q = v.get("quantity")
    if isinstance(q, bool) or not isinstance(q, int) or q < 1 or q > 9999:
        raise ActionError("La quantité doit être un nombre entier positif")
    minimum = max(0, _int(v.get("minimum")))
    rech = bool(v.get("rechargeable"))
    line = line_of(d["stock"], fmt, rech)
    if line:
        line["quantity"] += q
        line["minimum"] = minimum
    else:
        d["stock"].append({"id": uid(), "format": fmt, "rechargeable": rech, "quantity": q, "minimum": minimum, "charging": 0})
    d["history"].insert(0, entry("stock", {"format": fmt, "rechargeable": rech, "quantity": q}))
    return "Stock mis à jour"


def adjust_stock(d, a):
    line = _find(d, "stock", a.get("lineId"), "Ligne de stock introuvable")
    line["quantity"] = max(0, line["quantity"] + _int(a.get("delta")))
    return None


def set_minimum(d, a):
    line = _find(d, "stock", a.get("lineId"), "Ligne de stock introuvable")
    line["minimum"] = max(0, _int(a.get("value")))
    return None


def finish_charging(d, a):
    line = _find(d, "stock", a.get("lineId"), "Ligne de stock introuvable")
    n = line["charging"]
    if n <= 0:
        raise ActionError("Aucune pile en recharge")
    line["quantity"] += n
    line["charging"] = 0
    d["history"].insert(0, entry("recharge", {"format": line["format"], "rechargeable": True, "quantity": n}))
    return f"{describe(n, line['format'], True)} rechargée{plural(n)}, remise{plural(n)} en stock"


# ---------- Paramètres ----------

def add_setting(d, a):
    kind = a.get("kind")
    clean = str(a.get("value", "")).strip()
    if not clean:
        raise ActionError("Écris un nom avant d'ajouter")
    if len(clean) > 40:
        raise ActionError("Nom trop long (40 caractères maximum)")
    key = "formats" if kind == "format" else "categories"
    if any(x.lower() == clean.lower() for x in d[key]):
        raise ActionError("Cet élément existe déjà")
    d[key].append(clean.upper() if kind == "format" else clean)
    return "Format ajouté" if kind == "format" else "Catégorie ajoutée"


def remove_setting(d, a):
    kind, value = a.get("kind"), a.get("value")
    if kind == "format":
        used = any(x["format"] == value for x in d["equipment"]) or any(x["format"] == value for x in d["stock"])
        key = "formats"
    else:
        used = any(x["category"] == value for x in d["equipment"])
        key = "categories"
    if used:
        raise ActionError("Suppression impossible : cet élément est utilisé")
    d[key] = [x for x in d[key] if x != value]
    return "Élément supprimé"


def keep_demo(d, a):
    d["demo"] = False
    return None


def reset(d, a):
    fresh = empty_data()
    d.clear()
    d.update(fresh)
    return "Données effacées"


ACTIONS = {
    "addEquipment": add_equipment, "editEquipment": edit_equipment, "deleteEquipment": delete_equipment,
    "replacePiles": replace_piles, "declareDead": declare_dead, "cancelDead": cancel_dead,
    "addStock": add_stock, "adjustStock": adjust_stock, "setMinimum": set_minimum, "finishCharging": finish_charging,
    "addSetting": add_setting, "removeSetting": remove_setting, "keepDemo": keep_demo, "reset": reset,
}


def apply(data, name, args):
    """Applique une action sur une COPIE des données. Renvoie (nouvelles_données, message)."""
    fn = ACTIONS.get(name)
    if not fn:
        raise ActionError("Action inconnue")
    if not isinstance(args, dict):
        raise ActionError("Demande invalide")
    d = copy.deepcopy(data)
    msg = fn(d, args)
    return d, msg


# ---------- Phrases affichées pour « Annuler » ----------

def _eq(src, ident):
    for e in src["equipment"]:
        if e["id"] == ident:
            return e
    return None


def _ln(src, ident):
    for x in src["stock"]:
        if x["id"] == ident:
            return x
    return None


def line_name(x):
    return f"{x['format']} {tw(x['rechargeable'])}"


def tw(rechargeable):
    return "rechargeable" if rechargeable else "standard"


def undo_label(name, args, before, after):
    """Courte phrase décrivant ce que « Annuler » va défaire."""
    try:
        if name == "addEquipment":
            old = {e["id"] for e in before["equipment"]}
            new = [e for e in after["equipment"] if e["id"] not in old]
            return f"Ajout de {new[0]['name']}"
        if name == "editEquipment":
            return f"Modification de {_eq(after, (args.get('v') or {}).get('id'))['name']}"
        if name == "deleteEquipment":
            return f"Suppression de {_eq(before, args.get('id'))['name']}"
        if name == "replacePiles":
            return f"Remplacement des piles de {_eq(before, args.get('id'))['name']}"
        if name == "declareDead":
            return f"Piles mortes déclarées : {_eq(before, args.get('id'))['name']}"
        if name == "cancelDead":
            return f"Déclaration annulée : {_eq(before, args.get('id'))['name']}"
        if name == "addStock":
            v = args.get("v") or {}
            return f"Ajout de stock : {v.get('quantity')} × {v.get('format')} {tw(bool(v.get('rechargeable')))}"
        if name == "adjustStock":
            b, a = _ln(before, args.get("lineId")), _ln(after, args.get("lineId"))
            delta = a["quantity"] - b["quantity"]
            return f"Stock {line_name(b)} : {'+' if delta > 0 else ''}{delta}" if delta else f"Stock {line_name(b)} : inchangé"
        if name == "setMinimum":
            b, a = _ln(before, args.get("lineId")), _ln(after, args.get("lineId"))
            return f"Alerte {line_name(b)} : de {b['minimum']} à {a['minimum']}"
        if name == "finishCharging":
            return f"Recharge terminée : {line_name(_ln(before, args.get('lineId')))}"
        if name == "addSetting":
            return f"Ajout {'du format' if args.get('kind') == 'format' else 'de la catégorie'} {str(args.get('value', '')).strip()}"
        if name == "removeSetting":
            return f"Retrait {'du format' if args.get('kind') == 'format' else 'de la catégorie'} {args.get('value')}"
        if name == "keepDemo":
            return "Exemples conservés"
        if name == "reset":
            return "Effacement des données"
        if name == "import":
            return "Restauration d'une sauvegarde"
    except (TypeError, KeyError, IndexError):
        pass
    return "Dernière modification"
