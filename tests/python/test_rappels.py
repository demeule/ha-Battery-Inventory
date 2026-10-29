import sys, json, random, shutil, subprocess, os
from datetime import date, timedelta
from helpers import ADDON, tmpdir
import logic, server
fails=0
def ok(c,m):
    global fails
    print(("OK   " if c else "ECHEC")+" "+m)
    if not c: fails+=1
# --- calendrier
am=logic.add_months
ok(am(date(2026,1,31),1)==date(2026,2,28),"31 janvier + 1 mois = 28 février")
ok(am(date(2024,1,31),1)==date(2024,2,29),"31 janvier 2024 + 1 mois = 29 février (bissextile)")
ok(am(date(2026,10,27),3)==date(2027,1,27),"27 oct + 3 mois = 27 janvier de l'année suivante")
ok(am(date(2026,12,15),12)==date(2027,12,15),"+ 12 mois = un an")
ok(am(date(2024,2,29),12)==date(2025,2,28),"29 février + 1 an = 28 février")
ok(am(date(2026,5,31),24)==date(2028,5,31),"+ 24 mois")
# --- statuts
e={"reminderMonths":6,"lastChange":"2026-04-27T12:00:00.000Z"}   # échéance le 27 octobre 2026
st=lambda t: logic.reminder_info(e,t)
ok(st(date(2026,10,27))["status"]=="due" and st(date(2026,10,27))["days"]==0,"le jour même : à changer")
ok(st(date(2026,10,30))["status"]=="due" and st(date(2026,10,30))["days"]==-3,"3 jours de retard : à changer")
ok(st(date(2026,10,26))["status"]=="soon","la veille : bientôt")
ok(st(date(2026,10,13))["status"]=="soon" and st(date(2026,10,13))["days"]==14,"14 jours avant : bientôt")
ok(st(date(2026,10,12))["status"]=="ok" and st(date(2026,10,12))["days"]==15,"15 jours avant : encore ok")
ok(logic.reminder_info({"reminderMonths":None,"lastChange":"2026-01-01"}) is None,"sans rappel : rien")
ok(logic.reminder_info({"reminderMonths":6,"lastChange":None})["status"]=="unknown","rappel sans date : à compléter")
# --- validation
stt=server.Store(tmpdir())
base={"name":"Détecteur de fumée","location":"Couloir","category":"Sécurité","format":"AA","rechargeable":False,"quantity":1,"photo":""}
def add(**x):
    return stt.act_ex("addEquipment",{"v":{**base,**x}})
def eq(n): return next(e for e in stt.data["equipment"] if e["name"]==n)
add(lastChange="2026-03-01",reminderMonths=12)
d=eq("Détecteur de fumée"); ok(d["lastChange"]=="2026-03-01T12:00:00.000Z" and d["reminderMonths"]==12,"équipement créé avec date et rappel")
for bad,label in ((dict(reminderMonths=0.5),"rappel 0,5"),(dict(reminderMonths="x"),"rappel texte"),(dict(reminderMonths=999),"rappel 999 mois"),(dict(lastChange="pas une date"),"date invalide"),(dict(lastChange="2999-01-01"),"date dans le futur"),(dict(reminderMonths=True),"rappel booléen")):
    try: stt.act_ex("addEquipment",{"v":{**base,"name":"X",**bad}}); ok(False,label+" refusé")
    except logic.ActionError as ex: ok(True,label+" refusé : "+str(ex)[:60])
add(name="Sans date")
ok(eq("Sans date")["lastChange"] is not None and eq("Sans date")["reminderMonths"] is None,"sans date fournie : date du jour, pas de rappel")
# --- remplacement remet le compteur à zéro
stt.act_ex("replacePiles",{"id":eq("Détecteur de fumée")["id"]})
ok(eq("Détecteur de fumée")["lastChange"][:10]==date.today().isoformat() or eq("Détecteur de fumée")["lastChange"][:10]==logic.today_utc().isoformat(),"remplacement : date de changement = aujourd'hui")
ok(logic.reminder_info(eq("Détecteur de fumée"))["status"]=="ok","remplacement : rappel repart à « ok »")
# --- modification : changer rappel, vider la date, ne rien envoyer
e1=eq("Détecteur de fumée")
stt.act_ex("editEquipment",{"v":{**e1,"reminderMonths":6}}); ok(eq("Détecteur de fumée")["reminderMonths"]==6,"modifier le rappel")
stt.act_ex("editEquipment",{"v":{**e1,"reminderMonths":None,"lastChange":""}}); x=eq("Détecteur de fumée"); ok(x["reminderMonths"] is None and x["lastChange"] is None,"vider rappel et date")
v2={k:v for k,v in e1.items() if k not in ("lastChange","reminderMonths")}
stt.act_ex("editEquipment",{"v":{**v2,"quantity":1,"name":"Détecteur de fumée"}}); ok(eq("Détecteur de fumée")["lastChange"] is None,"champs absents : ne touche pas à ce qui existe")
# --- annuler
before=eq("Détecteur de fumée")["lastChange"]
stt.act_ex("replacePiles",{"id":eq("Détecteur de fumée")["id"]}); ok(eq("Détecteur de fumée")["lastChange"]!=before,"remplacement change la date")
stt.act("undo",{}); ok(eq("Détecteur de fumée")["lastChange"]==before,"annuler : la date revient comme avant")
# --- reprise depuis l'ancien historique
old={"stock":[],"equipment":[{"id":"a1","name":"Vieux","category":"Autre","location":"x","format":"AA","rechargeable":False,"quantity":1}],
 "history":[{"id":"h1","date":"2026-02-01T10:00:00.000Z","type":"installation","equipmentId":"a1"},{"id":"h2","date":"2026-06-01T10:00:00.000Z","type":"remplacement","equipmentId":"a1"},{"id":"h3","date":"2026-08-01T10:00:00.000Z","type":"mortes","equipmentId":"a1"}]}
n=logic.normalize(old); ok(n["equipment"][0]["lastChange"]=="2026-06-01T10:00:00.000Z","anciennes données : date reprise du dernier remplacement")
print("TOUT PASSE" if not fails else f"{fails} ECHEC(S)")
sys.exit(1 if fails else 0)
