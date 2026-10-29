const {JSDOM}=require("jsdom");const BASE=process.env.BASE_URL;
const wait=(ms=120)=>new Promise(r=>setTimeout(r,ms));
let fails=0;const ok=(c,m)=>{console.log((c?"OK   ":"ECHEC")+" "+m);if(!c)fails++};
(async()=>{
 const html=await (await fetch(BASE)).text();
 const dom=new JSDOM(html,{runScripts:"dangerously",pretendToBeVisual:true,url:BASE,beforeParse(w){w.fetch=(u,o)=>fetch(new URL(u,BASE),o)}});
 const w=dom.window,d=w.document;await wait(600);
 const api=async p=>(await fetch(BASE+p)).json();
 const txt=()=>d.body.textContent;
 const btn=t=>[...d.querySelectorAll("button,label")].find(b=>b.textContent.trim()===t);
 const click=async t=>{const b=btn(t);if(!b)throw new Error("bouton introuvable: "+t);b.click();await wait()};
 const setv=(el,v)=>{const p=Object.getPrototypeOf(el);Object.getOwnPropertyDescriptor(p,"value").set.call(el,v);el.dispatchEvent(new w.Event(el.tagName==="SELECT"?"change":"input",{bubbles:true}))};
 const fieldIn=label=>[...d.querySelectorAll("[role=dialog] .label")].find(sp=>sp.textContent===label).parentElement.querySelector("input,select");
 const submit=async()=>{d.querySelector("[role=dialog] form").dispatchEvent(new w.Event("submit",{bubbles:true,cancelable:true}));await wait(300)};
 // l'accueil du lot 1 est identique ? (on part d'une base avec exemples ou non : on lit)
 await click("Ajouter");
 ok(!!d.querySelector("[role=dialog]"),"fenêtre d'ajout ouverte");
 ok(!!d.querySelector('[role=radiogroup] button[aria-checked="true"]'),"choix Standard / Rechargeable présent");
 setv(fieldIn("Nom"),"Horloge murale");setv(fieldIn("Emplacement"),"Cuisine");setv(fieldIn("Format"),"CR2032");await wait();
 // stepper : + augmente
 const plus=d.querySelector('[role=dialog] button[aria-label="Plus : Nombre de piles"]');plus.click();await wait();plus.click();await wait();plus.click();await wait();
 const q=fieldIn("Nombre de piles").value;ok(q==="5","bouton + du compteur : 2 -> 5 ("+q+")");
 await submit();
 ok(txt().includes("Stock insuffisant")&&(await api("api/state")).equipment.every(e=>e.name!=="Horloge murale"),"stock insuffisant : message rouge, rien créé");
 for(let i=0;i<3;i++){d.querySelector('[role=dialog] button[aria-label="Moins : Nombre de piles"]').click();await wait();}
 ok(fieldIn("Nombre de piles").value==="2","bouton − du compteur : 5 -> 2");
 await submit();
 let s=await api("api/state");
 ok(s.equipment.some(e=>e.name==="Horloge murale")&&!d.querySelector("[role=dialog]"),"équipement créé, fenêtre fermée");
 ok(txt().includes("Horloge murale"),"carte visible");
 // choix rechargeable puis édition
 d.querySelector('button[aria-label="Modifier Horloge murale"]').click();await wait();
 ok(fieldIn("Nom").value==="Horloge murale","formulaire de modification pré-rempli");
 [...d.querySelectorAll('[role=radiogroup] button')].find(b=>b.textContent==="Rechargeable").click();await wait();
 await submit();s=await api("api/state");
 ok(/insuffisant/i.test(txt())||s.equipment.find(e=>e.name==="Horloge murale").rechargeable===true,"changement vers rechargeable pris en compte ou refusé proprement");
 // échap ferme
 if(!d.querySelector("[role=dialog]")){ }
 d.querySelector('button[aria-label="Supprimer Horloge murale"]').click();await wait();
 ok(txt().includes("Supprimer cet équipement ?"),"confirmation de suppression");
 await click("Supprimer et remettre les piles en stock");
 s=await api("api/state");ok(s.equipment.every(e=>e.name!=="Horloge murale"),"équipement supprimé");
 // paramètres : carte liaison
 const tab=[...d.querySelectorAll("nav button")].find(b=>b.textContent.trim()==="Paramètres");tab.click();await wait(500);
 ok(!!d.querySelector("article h3")&&txt().includes("Liaison avec Home Assistant"),"onglet Paramètres + carte liaison");
 console.log(fails?`\n${fails} ECHEC(S)`:"\nTOUT PASSE");process.exit(fails?1:0);
})().catch(e=>{console.error("ERREUR",e);process.exit(1)});
