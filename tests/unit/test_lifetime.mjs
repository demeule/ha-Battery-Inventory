import { lifeStats, approxMonth, nextText, yearlyNeeds, changeDates, frDuration } from "../../frontend/src/helpers.js";
let fails=0; const ok=(c,m)=>{console.log((c?"OK   ":"ECHEC")+" "+m); if(!c) fails++;};
const D=86400000, T0=Date.UTC(2026,0,1,12);
const iso=(n)=>new Date(T0+n*D).toISOString();
const ev=(id,type,n)=>({equipmentId:id,type,date:iso(n)});
const eq=(id,extra={})=>({id,name:id,quantity:2,format:"AA",rechargeable:false,lastChange:null,reminderMonths:null,...extra});
// 1) trois changements réguliers
let h=[ev("a","installation",0),ev("a","remplacement",90),ev("a","remplacement",180)];
let s=lifeStats(eq("a",{lastChange:iso(180)}),h);
ok(s.count===2&&Math.round(s.avgDays)===90,"2 mesures de 90 jours : durée moyenne 90 j");
ok(Math.round((s.nextAt-T0)/D)===270,"prochain remplacement estimé : jour 270");
ok(Math.round(s.perYear)===Math.round(2*365/90),"piles par an = 2 × 365 / 90 = "+s.perYear.toFixed(1));
// 2) une seule mesure : pas d'estimation
s=lifeStats(eq("b"),[ev("b","installation",0),ev("b","remplacement",60)]);
ok(s.count===1&&s.avgDays===null&&s.nextAt===null&&s.perYear===null,"1 seule mesure : rien d'estimé (pas inventé)");
// 3) aucune mesure
s=lifeStats(eq("c"),[ev("c","installation",0)]); ok(s.count===0&&s.avgDays===null,"aucune mesure");
// 4) double clic (intervalle de quelques heures) ignoré
h=[ev("d","installation",0),ev("d","remplacement",0.2),ev("d","remplacement",100),ev("d","remplacement",200)];
s=lifeStats(eq("d"),h); ok(s.count===2&&Math.round(s.avgDays)===100,"changements à quelques heures d'écart ignorés (durée 100 j)");
// 5) intervalle de 1 jour entre deux événements : ignoré
h=[ev("e","installation",0),ev("e","remplacement",1.5),ev("e","remplacement",100),ev("e","remplacement",200)];
s=lifeStats(eq("e"),h); ok(Math.round(s.avgDays)===Math.round((98.5+100)/2)||s.count>=2,"intervalles très courts écartés ("+s.count+" mesures)");
// 6) la date saisie à la main sert de départ
h=[ev("f","remplacement",100),ev("f","remplacement",200)];
s=lifeStats(eq("f",{lastChange:iso(200)}),h); ok(s.count===1,"sans départ : 1 mesure seulement");
s=lifeStats(eq("f",{lastChange:iso(200)}),[...h,ev("f","remplacement",300)]); ok(s.count===2&&Math.round(s.avgDays)===100,"3 remplacements : 2 mesures");
const g=eq("g",{lastChange:iso(0)}); h=[ev("g","remplacement",100),ev("g","remplacement",200)];
s=lifeStats(g,h); ok(s.count===2&&Math.round(s.avgDays)===100,"date de départ saisie à la main + 2 remplacements = 2 mesures");
// 7) seulement les 5 derniers intervalles
h=[ev("h","installation",0)]; let t=0; for(const g2 of [10,10,10,10,10,100,100,100,100,100]){ t+=g2; h.push(ev("h","remplacement",t)); }
s=lifeStats(eq("h",{lastChange:iso(t)}),h); ok(Math.round(s.avgDays)===100,"moyenne sur les 5 derniers intervalles seulement (100 j)");
// 8) le même jour dans l'historique et dans la date saisie ne compte qu'une fois
h=[ev("i","installation",0),ev("i","remplacement",50)]; s=lifeStats(eq("i",{lastChange:iso(50.01)}),h); ok(s.count===1,"date saisie = date de l'historique : pas de doublon");
// 9) textes
const now=Date.UTC(2026,5,15);
ok(approxMonth(Date.UTC(2026,0,5),now)==="début janvier"&&approxMonth(Date.UTC(2026,0,15),now)==="mi-janvier"&&approxMonth(Date.UTC(2026,0,28),now)==="fin janvier","début / mi- / fin du mois");
ok(approxMonth(Date.UTC(2027,1,12),now)==="mi-février 2027","année affichée si ce n'est pas l'année en cours");
ok(nextText({nextAt:now-5*D},now)==="à prévoir maintenant","estimation dépassée : « à prévoir maintenant »");
ok(nextText({nextAt:now+9*D},now)==="dans environ 9 jours","estimation proche : « dans environ 9 jours »");
ok(nextText({nextAt:now+90*D},now)==="mi-septembre"||nextText({nextAt:now+90*D},now)==="début septembre"||nextText({nextAt:now+90*D},now)==="fin septembre"||/septembre/.test(nextText({nextAt:now+90*D},now)),"estimation lointaine : mois approximatif ("+nextText({nextAt:now+90*D},now)+")");
ok(nextText({nextAt:null})==="","pas d'estimation : texte vide");
// 10) besoins annuels
const E=[eq("x",{format:"AA",quantity:2}),eq("y",{format:"AA",quantity:1,reminderMonths:12}),eq("z",{format:"AAA",quantity:3,rechargeable:true,reminderMonths:6}),eq("w",{format:"CR2032",quantity:1})];
const st={x:{perYear:24},y:{perYear:null},z:{perYear:12},w:{perYear:null}};
const n=yearlyNeeds(E,st);
ok(Math.round(n.byFormat.AA)===25&&n.measured===1&&n.fromReminder===1,"AA : 24 (mesuré) + 1 (rappel annuel) = 25");
ok(!("AAA" in n.byFormat),"rechargeables non comptées");
ok(!("CR2032" in n.byFormat),"équipement sans mesure ni rappel : non compté");
console.log(fails?`\n${fails} ECHEC(S)`:"\nTOUT PASSE");
process.exit(fails?1:0);
