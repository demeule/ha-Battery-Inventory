const {JSDOM}=require("jsdom");const BASE=process.env.BASE_URL;
const wait=(ms=150)=>new Promise(r=>setTimeout(r,ms));
let fails=0;const ok=(c,m)=>{console.log((c?"OK   ":"ECHEC")+" "+m);if(!c)fails++};
const post=async(action,args)=>(await fetch(BASE+"api/action",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({action,args})})).json();
const api=async p=>(await fetch(BASE+p)).json();
const dayAgo=n=>new Date(Date.now()-n*86400000).toISOString().slice(0,10);
(async()=>{
 const base={location:"Couloir",category:"Sécurité",format:"AAA",rechargeable:false,quantity:1,photo:""};
 await post("keepDemo",{});
 await post("addEquipment",{v:{...base,name:"Détecteur A",lastChange:dayAgo(100),reminderMonths:3}});   // en retard
 await post("addEquipment",{v:{...base,name:"Détecteur B",lastChange:dayAgo(80),reminderMonths:3}});    // dans ~10 jours
 await post("addEquipment",{v:{...base,name:"Détecteur C",lastChange:dayAgo(10),reminderMonths:12}});   // loin
 const html=await (await fetch(BASE)).text();
 const dom=new JSDOM(html,{runScripts:"dangerously",pretendToBeVisual:true,url:BASE,beforeParse(w){w.fetch=(u,o)=>fetch(new URL(u,BASE),o)}});
 const w=dom.window,d=w.document;await wait(800);
 const txt=()=>d.body.textContent;
 const card=n=>[...d.querySelectorAll("article")].find(a=>a.textContent.includes(n));
 ok(card("Détecteur A").textContent.includes("À changer depuis"),"A (100 jours / 3 mois) : « À changer depuis … »");
 ok(card("Détecteur B").textContent.includes("À changer bientôt, dans"),"B : « À changer bientôt, dans … »");
 ok(card("Détecteur C").textContent.includes("Rappel dans"),"C : « Rappel dans … » (pas d'alerte)");
 ok(card("Détecteur A").className.includes("is-due")&&card("Détecteur B").className.includes("is-due")&&!card("Détecteur C").className.includes("is-due"),"cadre ambre sur A et B seulement");
 ok(card("Détecteur A").textContent.includes("Piles changées il y a"),"« Piles changées il y a … » affiché");
 const cells=[...d.querySelectorAll(".cell")];
 ok(cells.filter(c=>c.className.includes("is-soon")).length===2,"2 cellules ambre en haut");
 ok(txt().includes("À changer bientôt :")&&txt().includes("Détecteur A")&&txt().includes("Détecteur B"),"bandeau « À changer bientôt : … »");
 const chip=d.querySelector('[data-stat="Rappels"]'); ok(chip&&chip.querySelector("b").textContent==="2","pastille « Rappels » = 2");
 chip.click();await wait(300);
 ok([...d.querySelectorAll("article")].length===2,"clic sur la pastille : seulement les 2 équipements concernés");
 // modification : formulaire pré-rempli
 d.querySelector('button[aria-label="Modifier Détecteur A"]').click();await wait(300);
 const dlg=d.querySelector("[role=dialog]");
 const dateIn=dlg.querySelector('input[type=date]'),sel=[...dlg.querySelectorAll("select")].find(s=>[...s.options].some(o=>o.textContent==="Aucun"));
 ok(dateIn.value===dayAgo(100)&&sel.value==="3","formulaire pré-rempli : date et rappel « 3 mois »");
 ok(dateIn.max&&dateIn.max.length===10,"la date ne peut pas être dans le futur (max défini)");
 // remplacement : le compteur repart
 const btns=()=>[...d.querySelectorAll("button")];
 btns().find(b=>b.getAttribute("aria-label")==="Fermer").click();await wait(200);
 const bA=[...card("Détecteur A").querySelectorAll("button")].find(b=>b.textContent==="Remplacer les piles");bA.click();await wait(250);
 ok(txt().includes("Le compteur du rappel repart de zéro"),"fenêtre de remplacement : « le compteur repart de zéro »");
 btns().find(b=>b.textContent==="Confirmer le remplacement").click();await wait(500);
 const A=(await api("api/state")).equipment.find(e=>e.name==="Détecteur A");
 ok(A.lastChange.slice(0,10)===new Date().toISOString().slice(0,10),"après remplacement : date de changement = aujourd'hui");
 ok(d.querySelectorAll("article").length===1&&txt().includes("Détecteur B"),"filtre « rappels » : A en sort, seul B reste à surveiller");
 console.log(fails?`\n${fails} ECHEC(S)`:"\nTOUT PASSE");process.exit(fails?1:0);
})().catch(e=>{console.error("ERREUR",e);process.exit(1)});
