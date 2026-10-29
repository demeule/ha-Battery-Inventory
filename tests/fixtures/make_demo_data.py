"""Écrit un jeu de données réaliste (un an d'historique) : python make_demo_data.py <dossier>. Sert aux tests et aux captures d'écran."""
import json, sys, uuid
from pathlib import Path
from datetime import datetime, timedelta, timezone
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "battery_inventory"))
import logic
out=sys.argv[1]
now=datetime.now(timezone.utc)
iso=lambda n: (now-timedelta(days=n)).isoformat(timespec="milliseconds").replace("+00:00","Z")
d=logic.empty_data(); d["demo"]=False
def stock(f,r,q,m): d["stock"].append({"id":logic.uid(),"format":f,"rechargeable":r,"quantity":q,"minimum":m,"charging":0})
stock("AA",False,10,4); stock("AAA",False,3,4); stock("CR2032",False,6,2); stock("AA",True,4,2)
hist=[]
def equip(name,loc,cat,fmt,rech,q,ages,rem=None):
    e={"id":logic.uid(),"name":name,"location":loc,"category":cat,"format":fmt,"rechargeable":rech,"quantity":q,"photo":"","deadSince":None,
       "lastChange":iso(ages[-1]),"reminderMonths":rem}
    d["equipment"].append(e)
    for i,a in enumerate(ages):
        hist.append({"id":logic.uid(),"date":iso(a),"type":"installation" if i==0 else "remplacement","equipmentId":e["id"],"equipment":name,"format":fmt,"rechargeable":rech,"quantity":q})
    return e
equip("Train en bois","Chambre","Jouet","AA",True,3,[300,279,258,237,216,195,174,153,132,111,90,69,48,27,6])   # ~21 jours
equip("Télécommande TV","Salon","Télécommande","AAA",False,2,[400,280,160,40])      # ~120 jours
equip("Horloge murale","Cuisine","Maison","AA",False,1,[330,150,10])                # ~160 jours
equip("Détecteur de fumée","Couloir","Sécurité","AA",False,1,[200,20],12)           # 1 mesure + rappel annuel
equip("Sonnette","Entrée","Sécurité","CR2032",False,1,[45])                         # aucune mesure
hist.sort(key=lambda h:h["date"],reverse=True)
d["history"]=hist
json.dump(d,open(out+"/piles.json","w"),ensure_ascii=False)
print("jeu de données écrit")
