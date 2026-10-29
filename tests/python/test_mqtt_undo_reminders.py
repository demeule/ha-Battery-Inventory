import json, os, subprocess, sys, time, shutil, urllib.request
import paho.mqtt.client as paho
fails=0
def ok(c,m):
    global fails
    print(("OK   " if c else "ECHEC")+" "+m)
    if not c: fails+=1
from helpers import ADDON, tmpdir, free_port, start_mosquitto, skip_without_mqtt
skip_without_mqtt()
MQ, MQPORT = start_mosquitto()
PORT = free_port(); DATA = tmpdir()
env = dict(os.environ, BATTERY_PORT=str(PORT), BATTERY_DATA=DATA, BATTERY_MQTT="1", BATTERY_MQTT_HOST="127.0.0.1",
           BATTERY_MQTT_PORT=str(MQPORT), PYTHONUNBUFFERED="1")
def start():
    return subprocess.Popen([sys.executable, str(ADDON / "server.py")], env=env, stdout=open(os.path.join(DATA, "server.log"), "a"), stderr=subprocess.STDOUT)
B = f"http://127.0.0.1:{PORT}/"
srv=subprocess.Popen([sys.executable, str(ADDON / "server.py")], env=env, stdout=open(os.path.join(DATA, "server.log"), "a"), stderr=subprocess.STDOUT)
def get(p): return json.loads(urllib.request.urlopen(B+p).read())
def act(n,**a):
    r=urllib.request.Request(B+"api/action",data=json.dumps({"action":n,"args":a}).encode(),headers={"Content-Type":"application/json"},method="POST")
    return json.loads(urllib.request.urlopen(r).read())
msgs={}
def on(c,u,m): msgs[m.topic]=m.payload.decode()
ha=paho.Client(paho.CallbackAPIVersion.VERSION2,client_id="ha_sim2"); ha.on_message=on; ha.connect("127.0.0.1",MQPORT); ha.loop_start(); ha.subscribe("#")
def wait(c,t=8):
    d=time.time()+t
    while time.time()<d:
        try:
            if c(): return True
        except Exception: pass
        time.sleep(0.1)
    return False
n_cfg=lambda: len([t for t,v in msgs.items() if t.startswith("homeassistant/") and v])
ok(wait(lambda: n_cfg()==24),f"départ : 24 entités ({n_cfg()})")
train=[e for e in get("api/state")["equipment"] if e["name"]=="Train en bois"][0]
r=act("deleteEquipment",id=train["id"],giveBack=True)
ok(wait(lambda: n_cfg()==22),f"suppression : 22 entités ({n_cfg()})")
ok(msgs.get("battery_inventory/global/total_stock")=="27" or wait(lambda: msgs.get("battery_inventory/global/total_stock")=="27"),"stock total remonte à 27 (3 piles remises)")
r2=act("undo",id=r["undo"]["id"])
ok(r2["message"].startswith("Annulé : Suppression de Train en bois"),"annulation : "+r2["message"])
ok(wait(lambda: n_cfg()==24),f"annulation : les 24 entités reviennent ({n_cfg()})")
ok(wait(lambda: msgs.get("battery_inventory/global/total_stock")=="24"),"stock total revient à 24 dans Home Assistant")
# un ordre venu de Home Assistant est lui aussi annulable
tele=[e for e in get("api/state")["equipment"] if e["name"]=="Télécommande TV"][0]
ha.publish(f"battery_inventory/equipment/{tele['id']}/replace/press","PRESS")
ok(wait(lambda: msgs.get("battery_inventory/global/total_stock")=="22"),"bouton Home Assistant : remplacement fait")
u=get("api/state")["undo"]; ok(u and "Télécommande TV" in u["label"],"l'appli propose d'annuler : "+(u or {}).get("label",""))
act("undo",id=u["id"])
ok(wait(lambda: msgs.get("battery_inventory/global/total_stock")=="24"),"annulation : Home Assistant revient à 24")
# --- rappels de remplacement
import datetime
old=(datetime.date.today()-datetime.timedelta(days=100)).isoformat()
r=act("addEquipment",v={"name":"Detecteur fumee","location":"Couloir","category":"Sécurité","format":"AA","rechargeable":False,"quantity":1,"photo":"","lastChange":old,"reminderMonths":3})
det=[e for e in get("api/state")["equipment"] if e["name"]=="Detecteur fumee"][0]
tp=f"battery_inventory/equipment/{det['id']}"
ok(wait(lambda: msgs.get(tp+"/remind")=="ON"),"rappel dépassé (100 jours / 3 mois) : capteur « Rappel » ON")
ok(json.loads(msgs[tp+"/remind_attrs"])["status"]=="due","attribut status = due")
ok(wait(lambda: msgs.get("battery_inventory/global/n_remind")=="1" and "Detecteur fumee" in json.loads(msgs.get("battery_inventory/global/remind_attrs","{}") or "{}").get("text","")),"compteur global = 1 et nom dans le texte")
ok(wait(lambda: msgs.get("battery_inventory/global/alert_remind")=="ON"),"alerte globale ON")
ha.publish(tp+"/replace/press","PRESS")
ok(wait(lambda: msgs.get(tp+"/remind")=="OFF" and msgs.get("battery_inventory/global/n_remind")=="0"),"bouton Remplacer : le rappel repart à zéro (OFF, compteur 0)")
act("editEquipment",v={**det,"reminderMonths":None,"lastChange":old})
ok(wait(lambda: msgs.get("homeassistant/binary_sensor/battery_inventory/eq_"+det["id"]+"_remind/config")==""),"rappel supprimé dans l'appli : l'entité disparaît de Home Assistant")
print("TOUT PASSE" if not fails else f"{fails} ECHEC(S)")
try: srv.terminate()
except Exception: pass
MQ.terminate()
sys.exit(1 if fails else 0)

