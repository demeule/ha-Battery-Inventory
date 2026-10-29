import json, os, subprocess, sys, time, threading, urllib.request, shutil
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
def get(p): return json.loads(urllib.request.urlopen(B+p).read())
def post(p,b):
    r=urllib.request.Request(B+p,data=json.dumps(b).encode(),headers={"Content-Type":"application/json"},method="POST")
    return json.loads(urllib.request.urlopen(r).read())
def act(n,**a): return post("api/action",{"action":n,"args":a})
# "Home Assistant" simulé
msgs={}
def on_msg(c,u,m): msgs[m.topic]=m.payload.decode()
ha=paho.Client(paho.CallbackAPIVersion.VERSION2,client_id="ha_sim"); ha.on_message=on_msg
ha.connect("127.0.0.1",MQPORT); ha.loop_start(); ha.subscribe("#")
def wait(cond,t=6):
    d=time.time()+t
    while time.time()<d:
        try:
            if cond(): return True
        except Exception: pass
        time.sleep(0.1)
    return False
srv=start()
time.sleep(0.5)
ok(wait(lambda: get("api/mqtt")["state"]=="connecté" and get("api/mqtt")["entities"]>0),"liaison connectée : "+json.dumps(get("api/mqtt"),ensure_ascii=False))
ok(wait(lambda: msgs.get("battery_inventory/status")=="online"),"statut « online » publié")
cfgs={t:json.loads(v) for t,v in msgs.items() if t.startswith("homeassistant/") and v}
ok(len(cfgs)==24,f"24 entités découvertes ({len(cfgs)})")
ok(msgs.get("battery_inventory/global/total_stock")=="24","total en stock = 24")
s=get("api/state"); tele=[e for e in s["equipment"] if e["name"]=="Télécommande TV"][0]; train=[e for e in s["equipment"] if e["name"]=="Train en bois"][0]
# bouton « remplacer »
ha.publish(f"battery_inventory/equipment/{tele['id']}/replace/press","PRESS")
ok(wait(lambda: msgs.get("battery_inventory/global/total_stock")=="22"),"bouton Remplacer (HA) : stock 24 -> 22")
ok(wait(lambda: "Télécommande TV" in msgs.get("battery_inventory/global/last_return","")),"« Dernier retour » : "+msgs.get("battery_inventory/global/last_return",""))
ok(next(x for x in get("api/state")["stock"] if x["format"]=="AAA")["quantity"]==4,"l'appli voit le même stock (AAA = 4)")
# interrupteur piles mortes
ha.publish(f"battery_inventory/equipment/{train['id']}/dead/set","ON")
ok(wait(lambda: msgs.get(f"battery_inventory/equipment/{train['id']}/dead")=="ON"),"interrupteur ON : piles mortes déclarées")
ok(wait(lambda: msgs.get("battery_inventory/global/alert_dead")=="ON" and "Train en bois" in msgs.get("battery_inventory/global/dead_attrs","")),"alerte piles mortes ON + nom dans l'attribut texte")
ok(any(h["type"]=="mortes" for h in get("api/state")["history"]),"l'historique de l'appli a la ligne « piles mortes »")
msgs["battery_inventory/global/last_return"]=""
ha.publish(f"battery_inventory/equipment/{train['id']}/dead/set","ON")
ok(wait(lambda: "déjà" in msgs.get("battery_inventory/global/last_return","")),"2e ON : message « déjà signalé », pas d'erreur")
# remplacer -> sort de l'état mort, passe en recharge
ha.publish(f"battery_inventory/equipment/{train['id']}/replace/press","PRESS")
ok(wait(lambda: msgs.get(f"battery_inventory/equipment/{train['id']}/dead")=="OFF" and msgs.get("battery_inventory/global/alert_dead")=="OFF"),"remplacement : interrupteur repasse à OFF")
line=[x for x in get("api/state")["stock"] if x["rechargeable"]][0]
ok(wait(lambda: msgs.get(f"battery_inventory/stock/{line['id']}/charging")=="3"),"3 piles « en recharge » côté HA")
ha.publish(f"battery_inventory/stock/{line['id']}/charged/press","PRESS")
ok(wait(lambda: msgs.get(f"battery_inventory/stock/{line['id']}/charging")=="0" and msgs.get(f"battery_inventory/stock/{line['id']}/qty")=="4"),"bouton « recharge terminée » : retour à 4")
# échec : stock insuffisant -> retour d'erreur
act("adjustStock",lineId=[x for x in get("api/state")["stock"] if x["format"]=="AAA"][0]["id"],delta=-4)
msgs["battery_inventory/global/last_return"]=""
ha.publish(f"battery_inventory/equipment/{tele['id']}/replace/press","PRESS")
ok(wait(lambda: "Stock insuffisant" in msgs.get("battery_inventory/global/last_return","")),"stock insuffisant : retour d'erreur visible")
ok(json.loads(msgs["battery_inventory/global/last_return_attrs"])["ok"] is False,"attribut ok = false")
# ordre piégé
ha.publish("battery_inventory/equipment/../../x/replace/press","PRESS"); ha.publish("battery_inventory/equipment/inconnu/replace/press","PRESS")
time.sleep(0.5); ok(srv.poll() is None,"ordres invalides ignorés, serveur toujours là")
# ajout d'un équipement depuis l'appli -> nouvelles entités
r=act("addEquipment",v={"name":"Horloge","location":"Cuisine","category":"Maison","format":"AA","rechargeable":False,"quantity":2,"photo":""})
ok(wait(lambda: len([t for t,v in msgs.items() if t.startswith("homeassistant/") and v])==26),"équipement ajouté dans l'appli : 2 entités de plus (26)")
hid=[e for e in r["state"]["equipment"] if e["name"]=="Horloge"][0]["id"]
act("deleteEquipment",id=hid,giveBack=True)
ok(wait(lambda: len([t for t,v in msgs.items() if t.startswith("homeassistant/") and v])==24),"équipement supprimé : ses entités retirées de HA (24)")
# serveur redémarré : rien de dupliqué
srv.terminate(); srv.wait(); time.sleep(0.3)
msgs.pop("battery_inventory/status",None)
srv=start()
ok(wait(lambda: get("api/mqtt")["state"]=="connecté" if True else False,8),"redémarrage : reconnecté")
ok(wait(lambda: msgs.get("battery_inventory/status")=="online"),"« online » republié")
ok(len([t for t,v in msgs.items() if t.startswith("homeassistant/") and v])==24,"toujours 24 entités (pas de doublons)")
# arrêt brutal -> LWT offline
srv.kill(); srv.wait()
ok(wait(lambda: msgs.get("battery_inventory/status")=="offline",90),"arrêt brutal : HA voit « offline » (testament MQTT)")
ha.loop_stop()
print("TOUT PASSE" if not fails else f"{fails} ECHEC(S)")
try: srv.terminate()
except Exception: pass
MQ.terminate()
sys.exit(1 if fails else 0)

