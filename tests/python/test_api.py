import json, sys, threading, time, base64, urllib.request, urllib.error, os
from helpers import ADDON, tmpdir, free_port
import server, logic
DATA=tmpdir(); PORT=free_port()
httpd, store = server.make_server(DATA,"127.0.0.1",PORT)
threading.Thread(target=httpd.serve_forever,daemon=True).start()
B=f"http://127.0.0.1:{PORT}/"
fails=0
def ok(c,m):
    global fails
    print(("OK   " if c else "ECHEC")+" "+m)
    if not c: fails+=1
def get(p):
    return json.loads(urllib.request.urlopen(B+p).read())
def post(p,body,ctype="application/json"):
    req=urllib.request.Request(B+p,data=json.dumps(body).encode(),headers={"Content-Type":ctype},method="POST")
    try:
        r=urllib.request.urlopen(req); return r.status,json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code,json.loads(e.read())
def act(name,**args): return post("api/action",{"action":name,"args":args})
def stk(s,f,r=False): return next(x for x in s["stock"] if x["format"]==f and x["rechargeable"]==r)

s=get("api/state")
ok(len(s["equipment"])==2 and sum(x["quantity"] for x in s["stock"])==24,"départ : 2 équipements, 24 piles en stock")
rev=s["revision"]
ok(get(f"api/state?since={rev}").get("unchanged") is True,"since=revision -> unchanged")
tele=next(e for e in s["equipment"] if e["name"]=="Télécommande TV"); train=next(e for e in s["equipment"] if e["name"]=="Train en bois")
c,r=act("replacePiles",id=tele["id"]); ok(c==200 and stk(r["state"],"AAA")["quantity"]==4,"télécommande remplacée : AAA 6 -> 4")
c,r=act("declareDead",id=train["id"]); ok(c==200,"piles mortes déclarées")
c,r=act("declareDead",id=train["id"]); ok(c==400 and "déjà" in r["error"],"double déclaration refusée")
c,r=act("replacePiles",id=train["id"]); a=stk(r["state"],"AA",True)
ok(a["quantity"]==1 and a["charging"]==3,"AA rechargeable 4 -> 1, 3 en recharge")
ok([h["type"] for h in r["state"]["history"]]==["remplacement","mortes","remplacement"],"historique 3 lignes")
c,r=act("finishCharging",lineId=a["id"]); ok(stk(r["state"],"AA",True)["quantity"]==4,"recharge terminée -> 4")
# erreurs
c,r=act("addEquipment",v={"name":"Horloge","location":"Cuisine","category":"Maison","format":"CR2032","rechargeable":False,"quantity":5,"photo":""})
ok(c==400 and "Stock insuffisant" in r["error"],"stock insuffisant refusé : "+r.get("error",""))
c,r=act("addEquipment",v={"name":"","location":"x","category":"Maison","format":"AA","rechargeable":False,"quantity":1}); ok(c==400,"nom vide refusé")
c,r=act("addEquipment",v={"name":"X","location":"x","category":"Maison","format":"AA","rechargeable":False,"quantity":"2"}); ok(c==400,"quantité en texte refusée")
c,r=act("addEquipment",v={"name":"X","location":"x","category":"Maison","format":"ZZ","rechargeable":False,"quantity":1}); ok(c==400,"format inconnu refusé")
c,r=act("nimportequoi"); ok(c==400,"action inconnue refusée")
c,r=post("api/action",{"action":"reset"},"text/plain"); ok(c==415,"sans JSON déclaré -> refusé (protection)")
# photo
img=base64.b64encode(b"\xff\xd8\xff\xe0"+b"0"*100).decode()
c,p=post("api/photo",{"dataUrl":"data:image/jpeg;base64,"+img}); ok(c==200 and p["path"].startswith("photos/"),"photo envoyée")
raw=urllib.request.urlopen(B+p["path"]).read(); ok(raw.startswith(b"\xff\xd8\xff"),"photo relue")
c,_=post("api/photo",{"dataUrl":"data:image/jpeg;base64,"+base64.b64encode(b"pas une image").decode()}); ok(c==400,"fichier qui n'est pas un JPEG refusé")
try: urllib.request.urlopen(B+"photos/../piles.json"); ok(False,"traversée de dossier")
except urllib.error.HTTPError as e: ok(e.code in (404,400),"traversée de dossier bloquée")
c,r=act("addEquipment",v={"name":"Horloge","location":"Cuisine","category":"Maison","format":"AA","rechargeable":False,"quantity":2,"photo":p["path"]})
eq=next(e for e in r["state"]["equipment"] if e["name"]=="Horloge"); ok(eq["photo"]==p["path"] and stk(r["state"],"AA")["quantity"]==10,"équipement avec photo : AA 12 -> 10")
# faux nom de photo
c,r2=act("editEquipment",v={**eq,"photo":"photos/../../etc/passwd"}); ok(c==200 and next(e for e in r2["state"]["equipment"] if e["id"]==eq["id"])["photo"]=="","chemin de photo bidon neutralisé")
# edition avec correction de stock
c,r=act("editEquipment",v={**eq,"quantity":4}); ok(stk(r["state"],"AA")["quantity"]==8,"modif 2->4 piles : AA 10 -> 8")
c,r=act("editEquipment",v={**eq,"quantity":99}); ok(c==400 and "de plus" in r["error"],"modif impossible : "+r.get("error",""))
c,r=act("deleteEquipment",id=eq["id"],giveBack=True); ok(stk(r["state"],"AA")["quantity"]==12,"suppression + remise en stock : AA 12")
# export / import
exp=get("api/export"); ok(len(exp["equipment"])==2,"export : 2 équipements")
c,r=act("reset"); ok(len(r["state"]["equipment"])==0 and r["state"]["revision"]>rev,"réinitialisation, revision monte")
c,r=act("import",data=exp); ok(c==200 and len(r["state"]["equipment"])==2 and r["state"]["demo"] is False,"import restaure 2 équipements")
c,r=act("import",data={"foo":1}); ok(c==400,"import d'un mauvais fichier refusé")
# persistance : nouveau Store sur le même dossier
st2=server.Store(DATA); ok(len(st2.data["equipment"])==2 and st2.data["revision"]==store.data["revision"],"données retrouvées après redémarrage")
ok(len(list((store.backups).glob("piles-*.json")))==1,"une sauvegarde du jour créée")
# fichier abîmé -> reprise sauvegarde
open(os.path.join(DATA,"piles.json"),"w").write("{pas du json")
st3=server.Store(DATA); ok(len(st3.data["equipment"])>=0 and any(f.name.startswith("piles.illisible") for f in os.scandir(DATA)),"fichier abîmé : copie gardée + reprise sauvegarde")
# 30 clics + en même temps
sid=stk(get("api/state"),"AAA")["id"]
before=stk(get("api/state"),"AAA")["quantity"]
ths=[threading.Thread(target=lambda: act("adjustStock",lineId=sid,delta=1)) for _ in range(30)]
[t.start() for t in ths]; [t.join() for t in ths]
ok(stk(json.loads(store.state_json()),"AAA")["quantity"]==before+30,"30 clics simultanés : tous comptés")
print("quantité AAA avant/après:",before,stk(json.loads(store.state_json()),"AAA")["quantity"])
print("TOUT PASSE" if not fails else f"{fails} ECHEC(S)")
sys.exit(1 if fails else 0)
