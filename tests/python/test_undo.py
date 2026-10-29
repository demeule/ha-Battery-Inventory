import sys, os, json, random, shutil, time, base64
from helpers import ADDON, tmpdir
import server, logic
fails=0
def ok(c,m):
    global fails
    print(("OK   " if c else "ECHEC")+" "+m)
    if not c: fails+=1
def strip(d): return {k:v for k,v in d.items() if k!="revision"}
DIR=tmpdir()
st=server.Store(DIR)
S=lambda: json.loads(st.state_json())
def line(f,r=False): return next(x for x in st.data["stock"] if x["format"]==f and x["rechargeable"]==r)
def eq(n): return next(e for e in st.data["equipment"] if e["name"]==n)

# 1) chaque action est annulable et rend EXACTEMENT l'état d'avant
snaps=[]
def step(name,**a):
    before=json.loads(json.dumps(st.data))
    msg,undo=st.act_ex(name,a)
    snaps.append(before)
    return msg,undo
tele=eq("Télécommande TV")["id"]; train=eq("Train en bois")["id"]
step("replacePiles",id=tele)
step("declareDead",id=train)
step("replacePiles",id=train)
step("finishCharging",lineId=line("AA",True)["id"])
step("addStock",v={"format":"CR2032","rechargeable":False,"quantity":5,"minimum":2})
step("addSetting",kind="category",value="Cuisine")
m,u=step("addEquipment",v={"name":"Horloge","location":"Cuisine","category":"Cuisine","format":"AA","rechargeable":False,"quantity":2,"photo":""})
hid=eq("Horloge")["id"]
step("editEquipment",v={**eq("Horloge"),"quantity":3,"name":"Horloge murale"})
step("declareDead",id=hid); step("cancelDead",id=hid)
step("deleteEquipment",id=hid,giveBack=True)
step("keepDemo")
ok(u and u["label"]=="Ajout de Horloge","étiquette d'annulation : "+u["label"])
n=len(snaps); print("   pile :",len(st.undo),"annulations")
good=True
for i in range(n-1,-1,-1):
    top=st.undo[-1]
    msg=st.act("undo",{"id":top["id"]})
    if strip(st.data)!=strip(snaps[i]): good=False; print("   écart à l'étape",i,top["label"])
ok(good,f"{n} actions annulées une à une : l'état revient exactement à chaque étape")
ok(len(st.undo)==0,"pile vide à la fin")
try: st.act("undo",{}); ok(False,"annuler sans rien")
except logic.ActionError as e: ok("rien à annuler" in str(e),"annuler avec pile vide : "+str(e))

# 2) seule la dernière action est annulable
st.act("replacePiles",{"id":tele}); first=st.undo[-1]["id"]
st.act("declareDead",{"id":train})
try: st.act("undo",{"id":first}); ok(False,"annulation d'une action plus ancienne")
except logic.ActionError as e: ok("plus la dernière" in str(e),"annuler une action qui n'est plus la dernière : refusé")
st.act("undo",{}); st.act("undo",{})
# 3) fusion des +1 rapprochés
q0=line("AA")["quantity"]
for _ in range(5): st.act("adjustStock",{"lineId":line("AA")["id"],"delta":1})
ok(len(st.undo)==1 and st.undo[-1]["label"]=="Stock AA standard : +5","5 clics « + » = 1 seule annulation ("+st.undo[-1]["label"]+")")
st.act("undo",{}); ok(line("AA")["quantity"]==q0,"annuler : retour à "+str(q0))
for d in (1,-1): st.act("adjustStock",{"lineId":line("AA")["id"],"delta":d})
ok(len(st.undo)==0,"+1 puis −1 : plus rien à annuler")
# 4) pas d'annulation inutile
msg,u=st.act_ex("keepDemo",{}); msg,u2=st.act_ex("keepDemo",{}); ok(u2 is None,"action sans effet : pas d'entrée d'annulation")
# 5) limite de 30
for i in range(40): st.act("addSetting",{"kind":"category","value":f"C{i}"})
ok(len(st.undo)==server.UNDO_MAX,f"pile limitée à {server.UNDO_MAX}")
# 6) persistance après redémarrage
lab=st.undo[-1]["label"]; st2=server.Store(DIR)
ok(len(st2.undo)==server.UNDO_MAX and st2.undo[-1]["label"]==lab,"la pile survit à un redémarrage")
st2.act("undo",{}); ok("C39" not in st2.data["categories"],"annulation après redémarrage")
# 7) effacement total puis annulation (avec historique entier)
st=st2
h0=len(st.data["history"]); e0=len(st.data["equipment"])
st.act("reset",{}); ok(len(st.data["equipment"])==0,"effacement total")
st.act("undo",{}); ok(len(st.data["equipment"])==e0 and len(st.data["history"])==h0,"annuler l'effacement : tout revient, historique compris")
# 8) import annulable
exp=json.loads(st.export_json()); st.act("reset",{}); st.act("import",{"data":exp}); ok(len(st.data["equipment"])==e0,"import")
st.act("undo",{}); ok(len(st.data["equipment"])==0,"annuler l'import : état d'avant (vide)")
st.act("undo",{}); ok(len(st.data["equipment"])==e0,"puis annuler l'effacement")
# 9) la photo d'un équipement supprimé survit (même après 10 min) tant qu'on peut annuler
img=base64.b64encode(b"\xff\xd8\xff\xe0"+b"0"*200).decode()
path=st.save_photo("data:image/jpeg;base64,"+img)
st.act("addEquipment",{"v":{"name":"Lampe","location":"Salon","category":"Maison","format":"AA","rechargeable":False,"quantity":1,"photo":path}})
lid=eq("Lampe")["id"]; st.act("deleteEquipment",{"id":lid,"giveBack":True})
f=st.photos/os.path.basename(path); old=time.time()-3600; os.utime(f,(old,old))
st.act("addSetting",{"kind":"category","value":"Test photo"})   # déclenche le ménage des photos
ok(f.exists(),"photo gardée pendant que la suppression est annulable")
st.act("undo",{}); st.act("undo",{})
ok(eq("Lampe")["photo"]==path and f.exists(),"suppression annulée : la photo est bien revenue")
# 10) l'API publie la dernière annulation
j=S(); ok(j["undo"] and j["undo"]["id"]==st.undo[-1]["id"] and j["undoCount"]==len(st.undo),"l'état envoyé à l'appli contient l'annulation disponible")
# 11) l'historique ajouté par l'action est bien retiré à l'annulation
n0=len(st.data["history"]); st.act("replacePiles",{"id":eq("Lampe")["id"]}); ok(len(st.data["history"])==n0+1,"remplacement ajoute 1 ligne d'historique")
st.act("undo",{}); ok(len(st.data["history"])==n0,"annulation : la ligne d'historique disparaît")
print("TOUT PASSE" if not fails else f"{fails} ECHEC(S)")
sys.exit(1 if fails else 0)
