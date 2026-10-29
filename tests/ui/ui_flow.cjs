const {JSDOM}=require("jsdom");
const BASE=process.env.BASE_URL;
const wait=(ms=80)=>new Promise(r=>setTimeout(r,ms));
async function open(){
  const html=await (await fetch(BASE)).text();
  const dom=new JSDOM(html,{runScripts:"dangerously",pretendToBeVisual:true,url:BASE,beforeParse(w){w.fetch=(u,o)=>fetch(new URL(u,BASE),o)}});
  await wait(400);return dom.window;
}
let fails=0;const ok=(c,m)=>{console.log((c?"OK   ":"ECHEC")+" "+m);if(!c)fails++};
const api=async(p,b)=>(await fetch(BASE+p,b?{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(b)}:{})).json();
(async()=>{
 const w=await open(),d=w.document;
 const txt=()=>d.body.textContent;
 const btn=t=>[...d.querySelectorAll("button,label")].find(b=>b.textContent.trim()===t);
 const click=async t=>{const b=btn(t);if(!b)throw new Error("bouton introuvable: "+t);b.click();await wait()};
 const stats=()=>{const r={};d.querySelectorAll("[data-stat]").forEach(x=>{r[x.getAttribute("data-stat")]=+x.querySelector("b").textContent});return r};
 ok(txt().includes("Battery Inventory")&&txt().includes("exemples pour découvrir"),"page affichée avec les exemples");
 let s=stats();ok(s["Équipements"]===2&&s["Piles installées"]===5&&s["Piles en stock"]===24&&s["Stocks faibles"]===1&&s["Piles mortes"]===0,"chiffres de départ identiques au lot 1");
 await click("Remplacer les piles");await click("Confirmer le remplacement");await wait(150);
 const train=[...d.querySelectorAll("article")].find(a=>a.textContent.includes("Train en bois"));
 [...train.querySelectorAll("button")].find(b=>b.textContent==="Piles mortes").click();await wait();
 await click("Confirmer");await wait(150);
 ok(stats()["Piles mortes"]===1&&txt().includes("Piles mortes à remplacer"),"piles mortes affichées");
 await click("Remplacer les piles mortes");await click("Confirmer le remplacement");await wait(200);
 s=stats();ok(s["Piles en stock"]===19&&s["Stocks faibles"]===3&&s["Piles mortes"]===0,"mêmes chiffres que lot 1 : 19 en stock, 3 faibles");
 // 2e appareil
 const w2=await open();
 ok(w2.document.body.textContent.includes("Train en bois")&&w2.document.querySelector('[data-stat="Piles en stock"] b').textContent==="19","2e fenêtre : voit déjà 19 piles en stock");
 // modification dans la 1re, vue dans la 2e sans recharger
 await click("Stock");
 const plus=[...d.querySelectorAll('button[aria-label^="Ajouter une pile"]')][0];plus.click();await wait(200);
 await wait(4500);
 const n2=w2.document.querySelector('[data-stat="Piles en stock"] b').textContent;
 ok(n2==="20","2e fenêtre : +1 pile fait dans la 1re apparaît seule en < 5 s (20)");
 // seuil
 const inp=d.querySelector('input[type=number][min="0"]');
 const setter=Object.getOwnPropertyDescriptor(w.HTMLInputElement.prototype,"value").set;
 setter.call(inp,"9");inp.dispatchEvent(new w.Event("input",{bubbles:true}));inp.dispatchEvent(new w.FocusEvent("focusout",{bubbles:true}));await wait(250);
 const st=await api("api/state");ok(st.stock.some(x=>x.minimum===9),"seuil modifié enregistré au serveur");
 // serveur arrêté -> bandeau
 console.log(fails?`\n${fails} ECHEC(S)`:"\nTOUT PASSE");process.exit(fails?1:0);
})().catch(e=>{console.error("ERREUR",e);process.exit(1)});
