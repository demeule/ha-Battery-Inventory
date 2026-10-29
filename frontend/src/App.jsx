import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle, Battery, BatteryCharging, BatteryWarning, Camera, Check, Download, Grid2X2, History, ImagePlus,
  LayoutGrid, LayoutList, Minus, PackagePlus, Pencil, Plus, RefreshCw, Search, Settings, Tags, Trash2, Upload, X,
  ToyBrick, Tv2, Speaker, Home, ShieldCheck, Lightbulb, Package, WifiOff, CalendarClock, Hourglass, ShoppingBasket, TrendingUp,
} from "lucide-react";
import { REPO_URL, ISSUES_URL, KOFI_URL, VERSION } from "./project.js";
import { typeLabel, describe, lineOf, reminderInfo, reminderText, sinceText, frDuration, lifeStats, nextText, yearlyNeeds, REMINDER_CHOICES } from "./helpers.js";

const cn = (...x) => x.filter(Boolean).join(" ");
const fmtDate = (iso) => new Date(iso).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" });
const hello = () => {
  const h = new Date().getHours();
  return h < 5 ? "Bonsoir" : h < 12 ? "Bonjour" : h < 18 ? "Bon après-midi" : "Bonsoir";
};
const plural = (n, s = "s") => (n > 1 ? s : "");

// Une icône et une teinte par catégorie, pour que les équipements sans photo restent agréables à l'œil.
const CATS = { "Jouet": [ToyBrick, 0], "Télécommande": [Tv2, 1], "Multimédia": [Speaker, 2], "Maison": [Home, 3], "Sécurité": [ShieldCheck, 1], "Éclairage": [Lightbulb, 4], "Autre": [Package, 2] };
const catOf = (c) => CATS[c] || [Package, 2];

// Réduit une photo (iPhone = plusieurs Mo) à ~800 px avant de l'envoyer au serveur.
function compressImage(file, max = 800, quality = 0.72) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      const s = Math.min(1, max / Math.max(img.width, img.height));
      const c = document.createElement("canvas");
      c.width = Math.round(img.width * s);
      c.height = Math.round(img.height * s);
      c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
      URL.revokeObjectURL(url);
      resolve(c.toDataURL("image/jpeg", quality));
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("image illisible"));
    };
    img.src = url;
  });
}

const EMPTY = { stock: [], equipment: [], history: [], formats: [], categories: [], demo: false, revision: 0 };

// Parle au serveur. Les adresses sont « relatives » (sans / au début) pour fonctionner aussi dans Home Assistant.
async function api(path, body) {
  const res = await fetch(path, body === undefined ? { cache: "no-store" } : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  let j = null;
  try { j = await res.json(); } catch (e) { /* pas de JSON */ }
  if (!res.ok) {
    const err = new Error((j && j.error) || "Le serveur a refusé la demande");
    err.status = res.status;
    throw err;
  }
  return j;
}

export default function App() {
  const [state, setState] = useState(null);
  const [online, setOnline] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [busy, setBusy] = useState(false);
  const revRef = useRef(-1);
  const [tab, setTab] = useState("equipment");
  const [view, setView] = useState("cards");
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("Tous");
  const [onlyDead, setOnlyDead] = useState(false);
  const [onlyRemind, setOnlyRemind] = useState(false);
  const [modal, setModal] = useState(null);
  const [toast, setToast] = useState(null);
  const timer = useRef(null);
  const data = state || EMPTY;
  const { stock, equipment, history, formats, categories } = data;

  const apply = (s) => {
    if (s.revision < revRef.current) return; // réponse plus ancienne que ce qu'on affiche déjà
    revRef.current = s.revision;
    setState(s);
  };

  // Va chercher les données ; si rien n'a changé le serveur répond « unchanged ».
  const refresh = async () => {
    try {
      const s = await api("api/state?since=" + revRef.current);
      if (!s.unchanged) apply(s);
      setOnline(true);
      setLoadError("");
    } catch (e) {
      setOnline(false);
      if (revRef.current < 0) setLoadError("Impossible de joindre le serveur Battery Inventory.");
    }
  };

  // Vérifie le serveur toutes les 4 secondes : une modification faite sur l'iPhone apparaît sur le PC.
  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 4000);
    const onVis = () => document.visibilityState === "visible" && refresh();
    document.addEventListener("visibilitychange", onVis);
    return () => { clearInterval(t); document.removeEventListener("visibilitychange", onVis); };
  }, []);

  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && setModal(null);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const notify = (text, error = false, undo = null) => {
    setToast({ text, error, undo });
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setToast(null), undo ? 8000 : error ? 4500 : 2400);
  };

  // Envoie une action au serveur : s'il la refuse, on affiche pourquoi et rien n'a changé.
  const call = async (action, args = {}, { keepModal = false, silent = false } = {}) => {
    setBusy(true);
    try {
      const r = await api("api/action", { action, args });
      apply(r.state);
      setOnline(true);
      if (!keepModal) setModal(null);
      if (r.message && !silent) notify(r.message, false, r.undo || null);
      return true;
    } catch (e) {
      if (e.status) notify(e.message, true);
      else { setOnline(false); notify("Le serveur ne répond pas. Réessaie dans un instant.", true); }
      return false;
    } finally {
      setBusy(false);
    }
  };

  // Quand on change d'onglet, la page remonte au contenu (sur téléphone l'en-tête occupe tout l'écran).
  const contentRef = useRef(null);
  const firstTab = useRef(true);
  useEffect(() => {
    if (firstTab.current) { firstTab.current = false; return; }
    if (contentRef.current && contentRef.current.scrollIntoView) contentRef.current.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [tab]);

  const low = stock.filter((x) => x.quantity <= x.minimum);
  const dead = equipment.filter((x) => x.deadSince);
  const total = stock.reduce((a, x) => a + x.quantity, 0);
  const installed = equipment.reduce((a, x) => a + x.quantity, 0);
  const remind = equipment
    .map((e) => ({ e, info: reminderInfo(e) }))
    .filter((x) => x.info && (x.info.status === "soon" || x.info.status === "due"));
  const remindIds = new Set(remind.map((x) => x.e.id));
  const anyReminder = equipment.some((e) => e.reminderMonths);
  const todo = dead.length + low.length + remind.length;

  const filtered = useMemo(
    () =>
      equipment
        .filter((x) => `${x.name} ${x.location} ${x.category} ${x.format}`.toLowerCase().includes(query.toLowerCase()))
        .filter((x) => filter === "Tous" || x.format === filter)
        .filter((x) => !onlyDead || x.deadSince)
        .filter((x) => !onlyRemind || remindIds.has(x.id))
        .sort((a, b) => Number(!!b.deadSince) - Number(!!a.deadSince) || a.name.localeCompare(b.name, "fr")),
    [equipment, query, filter, onlyDead, onlyRemind]
  );

  const lifeById = useMemo(() => Object.fromEntries(equipment.map((e) => [e.id, lifeStats(e, history)])), [equipment, history]);

  const sortedStock = useMemo(
    () => [...stock].sort((a, b) => a.format.localeCompare(b.format, "fr") || Number(a.rechargeable) - Number(b.rechargeable)),
    [stock]
  );

  const need = (line) =>
    equipment.filter((e) => e.format === line.format && e.rechargeable === line.rechargeable).reduce((a, e) => a + e.quantity, 0);

  function exportData() {
    const a = document.createElement("a");
    a.href = "api/export";
    a.download = "mes-piles.json";
    a.click();
    notify("Sauvegarde téléchargée");
  }

  function pickImport(e) {
    const f = e.target.files && e.target.files[0];
    e.target.value = "";
    if (!f) return;
    const r = new FileReader();
    r.onload = () => {
      try {
        const d = JSON.parse(r.result);
        if (!d || !Array.isArray(d.stock) || !Array.isArray(d.equipment)) throw new Error();
        setModal({ type: "import", incoming: d });
      } catch (err) {
        notify("Ce fichier n'est pas une sauvegarde Battery Inventory", true);
      }
    };
    r.readAsText(f);
  }

  const showDead = () => { setTab("equipment"); setOnlyDead(true); setOnlyRemind(false); setQuery(""); setFilter("Tous"); };
  const showRemind = () => { setTab("equipment"); setOnlyRemind(true); setOnlyDead(false); setQuery(""); setFilter("Tous"); };
  const item = modal && modal.id ? equipment.find((x) => x.id === modal.id) : null;

  if (!state) {
    return (
      <div className="grid min-h-screen place-items-center p-6 text-center">
        <div className="glass w-full max-w-sm space-y-4 p-8">
          <div className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-gradient-to-br from-teal-600 to-cyan-700 text-white"><BatteryCharging /></div>
          <h1 className="text-xl font-extrabold">Battery Inventory</h1>
          {loadError ? (
            <>
              <p className="font-bold" style={{ color: "var(--t-red-fg)" }}>{loadError}</p>
              <p className="muted text-sm">Vérifie que la fenêtre noire du serveur est bien ouverte, puis réessaie.</p>
              <button type="button" className="btn btn-primary w-full" onClick={refresh}>Réessayer</button>
            </>
          ) : (
            <p className="muted font-semibold">Connexion au serveur…</p>
          )}
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="page">
        <header className="flex items-center gap-3 px-1 pb-4">
          <div className="grid h-11 w-11 place-items-center rounded-2xl bg-gradient-to-br from-teal-600 to-cyan-700 text-white shadow-lg"><BatteryCharging size={22} /></div>
          <h1 className="text-xl font-extrabold tracking-tight">Battery Inventory</h1>
        </header>

        {toast && (
          <div role="status" className={cn("toast glass", toast.error ? "err" : "ok")}>
            {toast.error ? <AlertTriangle size={20} /> : <Check size={20} style={{ color: "#16a34a" }} />}
            <span>{toast.text}</span>
            {toast.undo && (
              <button type="button" className="btn btn-sm" onClick={() => { const id = toast.undo.id; setToast(null); call("undo", { id }); }}>Annuler</button>
            )}
          </div>
        )}

        <div className="space-y-4">
          {!online && (
            <div className="notice tone-red flex items-center gap-3"><WifiOff size={20} />
              <span>Connexion au serveur perdue : les données affichées ne sont peut-être pas à jour. Nouvelle tentative automatique…</span>
            </div>
          )}

          {data.demo && (
            <div className="glass-card tone-blue flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
              <span><b>Voici des exemples pour découvrir l'appli.</b> Efface-les quand tu veux commencer ton vrai inventaire.</span>
              <div className="flex gap-2">
                <button type="button" className="btn btn-sm" onClick={() => setModal({ type: "reset", demo: true })}>Effacer les exemples</button>
                <button type="button" className="btn btn-sm" onClick={() => call("keepDemo")}>Garder</button>
              </div>
            </div>
          )}

          <section className="glass space-y-5 p-5 sm:p-7">
            <div>
              <h2 className="text-2xl font-extrabold tracking-tight sm:text-3xl">
                {hello()}, {equipment.length === 0 ? "bienvenue." : todo === 0 ? "tout est en ordre." : `${todo} chose${plural(todo)} à regarder.`}
              </h2>
              <p className="muted mt-1">
                {equipment.length === 0
                  ? "Ajoute ton premier équipement pour suivre ses piles."
                  : todo === 0
                    ? "Aucune pile à remplacer, aucun stock à racheter."
                    : "Touche une pastille pour voir de quoi il s'agit."}
              </p>
            </div>

            {equipment.length > 0 && (
              <div className="cells" aria-label="Tous tes équipements">
                {[...equipment].sort((a, b) => Number(!!b.deadSince) - Number(!!a.deadSince)).map((e, i) => {
                  const Icon = catOf(e.category)[0];
                  return (
                    <button key={e.id} type="button" className={cn("cell", e.deadSince ? "is-dead" : remindIds.has(e.id) && "is-soon")} style={{ animationDelay: `${Math.min(i, 20) * 45}ms` }}
                      title={e.deadSince ? `${e.name} : piles mortes` : remindIds.has(e.id) ? `${e.name} : à changer bientôt` : `${e.name} : piles en état`}
                      aria-label={e.deadSince ? `${e.name}, piles mortes` : remindIds.has(e.id) ? `${e.name}, rappel de remplacement` : `${e.name}, piles en état`}
                      onClick={() => { setTab("equipment"); setQuery(e.name); setOnlyDead(false); setFilter("Tous"); }}>
                      <Icon size={22} />
                    </button>
                  );
                })}
              </div>
            )}

            <div className="chips-row">
              <StatChip label="Équipements" value={equipment.length} icon={<LayoutGrid size={18} />} />
              <StatChip label="Piles installées" value={installed} icon={<Battery size={18} />} />
              <StatChip label="Piles en stock" value={total} icon={<BatteryCharging size={18} />} />
              <StatChip label="Stocks faibles" value={low.length} icon={<AlertTriangle size={18} />} tone={low.length ? "amber" : null} onClick={() => setTab("stock")} />
              <StatChip label="Piles mortes" value={dead.length} icon={<BatteryWarning size={18} />} tone={dead.length ? "red" : null} onClick={showDead} />
              {anyReminder && <StatChip label="Rappels" value={remind.length} icon={<CalendarClock size={18} />} tone={remind.length ? "amber" : null} onClick={showRemind} />}
            </div>

            {(dead.length > 0 || low.length > 0 || remind.length > 0) && (
              <div className="space-y-2">
                {dead.length > 0 && (
                  <button type="button" onClick={showDead} className="notice tone-red block w-full text-left">
                    <b>Piles mortes à remplacer :</b> {dead.map((x) => x.name).join(", ")}
                  </button>
                )}
                {remind.length > 0 && (
                  <button type="button" onClick={showRemind} className="notice tone-amber block w-full text-left">
                    <b>À changer bientôt :</b>{" "}
                    {remind.map(({ e, info }) => `${e.name} (${info.days > 0 ? `dans ${frDuration(info.days)}` : info.days === 0 ? "aujourd'hui" : `depuis ${frDuration(-info.days)}`})`).join(", ")}
                  </button>
                )}
                {low.length > 0 && (
                  <button type="button" onClick={() => setTab("stock")} className="notice tone-amber block w-full text-left">
                    <b>À réapprovisionner :</b> {low.map((x) => `${x.format} ${typeLabel(x.rechargeable).toLowerCase()} (${x.quantity})`).join(", ")}
                  </button>
                )}
              </div>
            )}
          </section>

          <nav className="tabs glass" aria-label="Sections">
            <TabButton active={tab === "equipment"} onClick={() => setTab("equipment")} icon={<LayoutGrid size={20} />} label="Équipements" />
            <TabButton active={tab === "stock"} onClick={() => setTab("stock")} icon={<Battery size={20} />} label="Stock" />
            <TabButton active={tab === "history"} onClick={() => setTab("history")} icon={<History size={20} />} label="Historique" />
            <TabButton active={tab === "settings"} onClick={() => setTab("settings")} icon={<Settings size={20} />} label="Paramètres" />
          </nav>

          <div ref={contentRef} className="-mb-4 h-0 scroll-mt-24" aria-hidden="true" />

          {tab === "equipment" && (
            <section className="space-y-4">
              <div className="glass-card flex flex-col gap-3 p-3 lg:flex-row lg:items-center">
                <div className="relative flex-1">
                  <Search className="muted pointer-events-none absolute left-4 top-3.5" size={20} />
                  <input aria-label="Rechercher" className="field" style={{ paddingLeft: "2.8rem" }} value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Chercher un équipement, une pièce, un format" />
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <div className="w-32"><Select aria-label="Filtrer par format" value={filter} onChange={(e) => setFilter(e.target.value)} options={["Tous", ...formats]} /></div>
                  <button type="button" aria-pressed={onlyDead} onClick={() => setOnlyDead(!onlyDead)} className={cn("btn btn-sm", onlyDead && "btn-soft-danger")}>Piles mortes seulement</button>
                  {anyReminder && <button type="button" aria-pressed={onlyRemind} onClick={() => setOnlyRemind(!onlyRemind)} className={cn("btn btn-sm", onlyRemind && "tone-amber")} style={onlyRemind ? { background: "var(--t-bg)", color: "var(--t-fg)" } : undefined}>Rappels seulement</button>}
                  <div className="seg" style={{ width: 104 }}>
                    <button type="button" aria-label="Vue cartes" aria-checked={view === "cards"} role="radio" onClick={() => setView("cards")}><Grid2X2 size={18} className="mx-auto" /></button>
                    <button type="button" aria-label="Vue liste" aria-checked={view === "list"} role="radio" onClick={() => setView("list")}><LayoutList size={18} className="mx-auto" /></button>
                  </div>
                  <button type="button" className="btn btn-primary" onClick={() => setModal({ type: "equipment" })}><Plus size={18} /> Ajouter</button>
                </div>
              </div>

              {filtered.length === 0 ? (
                <Empty icon={<Package size={30} />} title={equipment.length === 0 ? "Aucun équipement pour l'instant" : "Rien ne correspond à ta recherche"}
                  text={equipment.length === 0 ? "Ajoute le premier : jouet, télécommande, détecteur…" : "Essaie un autre mot, ou retire le filtre."}
                  action={equipment.length === 0 ? <button type="button" className="btn btn-primary" onClick={() => setModal({ type: "equipment" })}><Plus size={18} /> Ajouter un équipement</button> : null} />
              ) : view === "cards" ? (
                <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                  {filtered.map((x) => (
                    <EquipmentCard key={x.id} item={x} life={lifeById[x.id]}
                      edit={() => setModal({ type: "equipment", id: x.id })}
                      remove={() => setModal({ type: "delete", id: x.id })}
                      replace={() => setModal({ type: "replace", id: x.id })}
                      dead={() => setModal({ type: "dead", id: x.id })}
                      undo={() => call("cancelDead", { id: x.id })} />
                  ))}
                </div>
              ) : (
                <div className="glass-card overflow-x-auto">
                  <table className="list min-w-[860px]">
                    <thead><tr><th>Équipement</th><th>Emplacement</th><th>Piles</th><th>Actions</th></tr></thead>
                    <tbody>
                      {filtered.map((x) => {
                        const isDead = !!x.deadSince;
                        return (
                          <tr key={x.id} style={isDead ? { background: "var(--t-red-bg)" } : undefined}>
                            <td>
                              <div className="flex items-center gap-3">
                                <Photo src={x.photo} name={x.name} category={x.category} small />
                                <div>
                                  <div className="flex flex-wrap items-center gap-2"><b>{x.name}</b>{isDead && <DeadBadge />}</div>
                                  <div className="muted text-sm">{x.category}</div>
                                </div>
                              </div>
                            </td>
                            <td>{x.location}</td>
                            <td>
                              <div className="flex flex-wrap items-center gap-2"><b>{x.quantity} × {x.format}</b><Pill tone={x.rechargeable ? "teal" : "blue"}>{typeLabel(x.rechargeable)}</Pill></div>
                              {x.lastChange && <div className="muted text-sm">Changées {sinceText(x.lastChange)}</div>}
                              {reminderInfo(x) && <div className="text-sm font-semibold" style={remindIds.has(x.id) ? { color: "var(--t-amber-fg)" } : undefined}>{reminderText(reminderInfo(x))}</div>}
                            </td>
                            <td>
                              <div className="flex flex-wrap items-center gap-2">
                                <button type="button" className="btn btn-sm" onClick={() => setModal({ type: "replace", id: x.id })}>{isDead ? "Remplacer les piles mortes" : "Remplacer"}</button>
                                {isDead ? <button type="button" className="btn btn-sm" onClick={() => call("cancelDead", { id: x.id })}>Pas mortes</button> : <button type="button" className="btn btn-sm btn-soft-danger" onClick={() => setModal({ type: "dead", id: x.id })}>Piles mortes</button>}
                                <IconButton label={`Modifier ${x.name}`} onClick={() => setModal({ type: "equipment", id: x.id })} icon={<Pencil size={18} />} />
                                <IconButton label={`Supprimer ${x.name}`} danger onClick={() => setModal({ type: "delete", id: x.id })} icon={<Trash2 size={18} />} />
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          )}

          {tab === "stock" && (
            <section className="space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-3 px-1">
                <div>
                  <h2 className="text-xl font-extrabold">Ta réserve de piles</h2>
                  <p className="muted text-sm">Règle les quantités et l'alerte de chaque format.</p>
                </div>
                <button type="button" className="btn btn-primary" onClick={() => setModal({ type: "stock" })}><PackagePlus size={18} /> Ajouter du stock</button>
              </div>
              {sortedStock.length === 0 ? (
                <Empty icon={<Battery size={30} />} title="Aucune pile en réserve" text="Déclare tes piles pour qu'elles soient déduites à chaque remplacement."
                  action={<button type="button" className="btn btn-primary" onClick={() => setModal({ type: "stock" })}><PackagePlus size={18} /> Ajouter du stock</button>} />
              ) : (
                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                  {sortedStock.map((line) => (
                    <StockCard key={line.id} item={line} need={need(line)}
                      change={(delta) => call("adjustStock", { lineId: line.id, delta }, { silent: true, keepModal: true })}
                      setMin={(value) => call("setMinimum", { lineId: line.id, value }, { silent: true, keepModal: true })}
                      charged={() => call("finishCharging", { lineId: line.id })} />
                  ))}
                </div>
              )}
            </section>
          )}

          {tab === "history" && (
            <section className="space-y-4">
              <BilanCard equipment={equipment} stock={stock} lifeById={lifeById} />
              <div className="glass-card overflow-hidden">
              <div className="p-5"><h2 className="text-xl font-extrabold">Historique</h2><p className="muted text-sm">Tout ce qui s'est passé avec tes piles, du plus récent au plus ancien.</p></div>
              {data.undo && (
                <div className="row-item" style={{ borderTop: 0, paddingTop: 0 }}>
                  <div className="flex min-w-0 items-center gap-3">
                    <div className="bubble tone-amber"><RefreshCw size={20} /></div>
                    <div className="min-w-0">
                      <b className="block">Annuler la dernière action</b>
                      <span className="muted block text-sm">{data.undo.label}</span>
                      <span className="muted block text-sm">{fmtDate(data.undo.date)}{data.undoCount > 1 ? `, et ${data.undoCount - 1} avant elle` : ""}</span>
                    </div>
                  </div>
                  <button type="button" className="btn btn-sm" disabled={busy} onClick={() => call("undo", { id: data.undo.id })}>Annuler</button>
                </div>
              )}
              {history.length === 0 ? (
                <Empty icon={<History size={30} />} title="Rien pour l'instant" text="Chaque remplacement, ajout ou déclaration apparaîtra ici." />
              ) : (
                history.slice(0, 200).map((x) => {
                  const [Icon, tone, label] = HISTORY[x.type] || [History, "slate", x.type];
                  return (
                    <div key={x.id} className="row-item">
                      <div className="flex min-w-0 items-center gap-3">
                        <div className={cn("bubble", `tone-${tone}`)}><Icon size={20} /></div>
                        <div className="min-w-0">
                          <b className="block">{x.equipment}</b>
                          <span className="muted block text-sm">{fmtDate(x.date)}</span>
                          {x.note && <span className="muted block text-sm">{x.note}</span>}
                        </div>
                      </div>
                      <div className="flex flex-wrap items-center justify-end gap-2">
                        <span className={cn("chip", `tone-${tone}`)}>{label}</span>
                        {x.format && x.quantity > 0 && <Pill tone={x.rechargeable ? "teal" : "blue"}>{x.quantity} × {x.format}</Pill>}
                      </div>
                    </div>
                  );
                })
              )}
              </div>
            </section>
          )}

          {tab === "settings" && (
            <section className="space-y-4">
              <div className="grid gap-4 lg:grid-cols-2">
                <SettingsCard title="Catégories" icon={<Tags size={20} />} items={categories} placeholder="Nouvelle catégorie" onAdd={(value) => call("addSetting", { kind: "category", value }, { keepModal: true })} onRemove={(value) => call("removeSetting", { kind: "category", value }, { keepModal: true })} />
                <SettingsCard title="Formats de piles" icon={<Battery size={20} />} items={formats} placeholder="Nouveau format" onAdd={(value) => call("addSetting", { kind: "format", value }, { keepModal: true })} onRemove={(value) => call("removeSetting", { kind: "format", value }, { keepModal: true })} />
              </div>
              <article className="glass-card p-5">
                <h3 className="text-lg font-extrabold">Sauvegarde</h3>
                <p className="muted mt-1 text-sm">Télécharge une sauvegarde de temps en temps : elle contient tout, photos comprises.</p>
                <div className="mt-4 flex flex-wrap gap-2">
                  <button type="button" className="btn btn-sm" onClick={exportData}><Download size={17} /> Télécharger une sauvegarde</button>
                  <label className="btn btn-sm cursor-pointer">
                    <Upload size={17} /> Restaurer une sauvegarde
                    <input type="file" accept="application/json,.json" onChange={pickImport} className="sr-only" />
                  </label>
                  <button type="button" onClick={() => setModal({ type: "reset" })} className="btn btn-sm btn-soft-danger">Tout effacer</button>
                </div>
              </article>
              <MqttCard />
              <AboutCard />
            </section>
          )}
        </div>
      </div>

      {modal && modal.type === "equipment" && (
        <Modal title={item ? "Modifier l'équipement" : "Ajouter un équipement"} close={() => setModal(null)}>
          <EquipmentForm initial={item} formats={formats} categories={categories} notify={notify} busy={busy}
            save={(v) => call(v.id ? "editEquipment" : "addEquipment", { v })} />
        </Modal>
      )}

      {modal && modal.type === "stock" && (
        <Modal title="Ajouter du stock" close={() => setModal(null)}>
          <StockForm stock={stock} formats={formats} busy={busy} save={(v) => call("addStock", { v })} />
        </Modal>
      )}

      {modal && modal.type === "replace" && item && (
        <Modal title={item.deadSince ? "Remplacer les piles mortes" : "Confirmer le remplacement"} close={() => setModal(null)}>
          <div className="space-y-4">
            <div className={cn("flex gap-4 rounded-2xl p-3", item.deadSince ? "tone-red" : "tone-slate")} style={{ background: "var(--t-bg)" }}>
              <Photo src={item.photo} name={item.name} category={item.category} small />
              <div>
                <b className="text-lg">{item.name}</b>
                {item.deadSince && <div className="mt-1"><DeadBadge /></div>}
                <p className="mt-1 text-sm">
                  Utiliser {describe(item.quantity, item.format, item.rechargeable)} du stock.
                  {item.rechargeable ? " Les anciennes piles partiront en recharge." : " Les anciennes piles sont jetées."}
                  {item.reminderMonths ? " Le compteur du rappel repart de zéro." : ""}
                </p>
              </div>
            </div>
            <button type="button" className="btn btn-primary w-full" disabled={busy} onClick={() => call("replacePiles", { id: item.id })}>Confirmer le remplacement</button>
          </div>
        </Modal>
      )}

      {modal && modal.type === "dead" && item && (
        <Modal title="Déclarer les piles mortes" close={() => setModal(null)}>
          <div className="space-y-4">
            <div className="tone-red rounded-2xl p-3" style={{ background: "var(--t-bg)", color: "var(--t-fg)" }}>
              <b className="text-lg">{item.name}</b>
              <p className="text-sm">Enregistrer {describe(item.quantity, item.format, item.rechargeable)} comme mortes.</p>
            </div>
            <button type="button" disabled={busy} onClick={() => call("declareDead", { id: item.id })} className="btn btn-danger w-full">Confirmer</button>
          </div>
        </Modal>
      )}

      {modal && modal.type === "delete" && item && (
        <Modal title="Supprimer cet équipement ?" close={() => setModal(null)}>
          <div className="space-y-3">
            <div className="tone-slate rounded-2xl p-3" style={{ background: "var(--t-bg)", color: "var(--t-fg)" }}>
              <b className="text-lg">{item.name}</b>
              <p className="text-sm">Que faire des {describe(item.quantity, item.format, item.rechargeable)} installées ?</p>
            </div>
            <button type="button" className="btn btn-primary w-full" disabled={busy} onClick={() => call("deleteEquipment", { id: item.id, giveBack: true })}>Supprimer et remettre les piles en stock</button>
            <button type="button" disabled={busy} onClick={() => call("deleteEquipment", { id: item.id, giveBack: false })} className="btn btn-danger w-full">Supprimer sans remettre en stock</button>
            <button type="button" onClick={() => setModal(null)} className="btn w-full">Annuler</button>
          </div>
        </Modal>
      )}

      {modal && modal.type === "import" && (
        <Modal title="Restaurer cette sauvegarde ?" close={() => setModal(null)}>
          <div className="space-y-3">
            <div className="tone-slate rounded-2xl p-3 text-sm" style={{ background: "var(--t-bg)", color: "var(--t-fg)" }}>
              <p>Cette sauvegarde contient :</p>
              <p className="mt-1 font-bold">{modal.incoming.equipment.length} équipement(s), {modal.incoming.stock.length} ligne(s) de stock, {(modal.incoming.history || []).length} mouvement(s)</p>
              <p className="mt-2 font-semibold" style={{ color: "var(--t-red-fg)" }}>Elle remplacera tout ce qui est actuellement dans l'appli.</p>
            </div>
            <button type="button" className="btn btn-primary w-full" disabled={busy} onClick={() => call("import", { data: modal.incoming })}>Remplacer mes données</button>
            <button type="button" onClick={() => setModal(null)} className="btn w-full">Annuler</button>
          </div>
        </Modal>
      )}

      {modal && modal.type === "reset" && (
        <Modal title={modal.demo ? "Effacer les exemples ?" : "Tout effacer ?"} close={() => setModal(null)}>
          <div className="space-y-3">
            <p className="muted text-sm">{modal.demo ? "Les équipements et stocks d'exemple seront supprimés." : "Tous les équipements, le stock et l'historique seront supprimés. Pense à télécharger une sauvegarde avant."}</p>
            <button type="button" disabled={busy} onClick={() => call("reset")} className="btn btn-danger w-full">Effacer</button>
            <button type="button" onClick={() => setModal(null)} className="btn w-full">Annuler</button>
          </div>
        </Modal>
      )}
    </div>
  );
}

// ================= Petits composants =================

const HISTORY = {
  mortes: [BatteryWarning, "red", "Piles mortes"],
  installation: [PackagePlus, "violet", "Installation"],
  remplacement: [RefreshCw, "blue", "Remplacement"],
  annulation: [X, "slate", "Annulation"],
  modification: [Pencil, "amber", "Modification"],
  suppression: [Trash2, "slate", "Suppression"],
  stock: [PackagePlus, "green", "Ajout au stock"],
  recharge: [BatteryCharging, "teal", "Recharge terminée"],
};

function BilanCard({ equipment, stock, lifeById }) {
  const measured = equipment.filter((e) => lifeById[e.id] && lifeById[e.id].avgDays);
  const waiting = equipment.filter((e) => !(lifeById[e.id] && lifeById[e.id].avgDays));
  const ranking = measured
    .map((e) => ({ e, perYear: lifeById[e.id].perYear, avg: lifeById[e.id].avgDays }))
    .sort((a, b) => b.perYear - a.perYear)
    .slice(0, 5);
  const top = ranking.length ? ranking[0].perYear : 1;
  const needs = yearlyNeeds(equipment, lifeById);
  const formats = Object.keys(needs.byFormat).sort((a, b) => a.localeCompare(b, "fr"));
  const have = (f) => stock.filter((x) => x.format === f && !x.rechargeable).reduce((a, x) => a + x.quantity, 0);
  return (
    <article className="glass-card space-y-5 p-5">
      <div>
        <h2 className="text-xl font-extrabold">Bilan de tes piles</h2>
        <p className="muted text-sm">Calculé à partir de ton historique : plus tu remplaces tes piles dans l'appli, plus il est juste.</p>
      </div>

      {ranking.length === 0 ? (
        <div className="flex items-start gap-3 rounded-2xl p-4" style={{ background: "var(--field)" }}>
          <div className="bubble tone-teal"><Hourglass size={20} /></div>
          <div>
            <p className="font-bold">Le bilan se remplit au fil des remplacements</p>
            <p className="muted text-sm">Il faut au moins deux remplacements d'un même équipement pour estimer la durée de vie de ses piles. Rien n'est inventé avant.</p>
          </div>
        </div>
      ) : (
        <div className="space-y-3">
          <h3 className="flex items-center gap-2 font-extrabold"><TrendingUp size={18} /> Les équipements les plus gourmands</h3>
          {ranking.map(({ e, perYear, avg }, i) => (
            <div key={e.id} className="space-y-1.5">
              <div className="flex items-baseline justify-between gap-3">
                <span className="font-bold">{i + 1}. {e.name}</span>
                <span className="muted text-sm">environ {Math.round(perYear)} pile{perYear >= 1.5 ? "s" : ""}{e.rechargeable ? " rechargée" + (perYear >= 1.5 ? "s" : "") : ""} par an</span>
              </div>
              <div className="gauge-body" style={{ height: 14, padding: 2, borderWidth: 2 }}>
                <div className="gauge-fill" data-tone={i === 0 ? "low" : "ok"} style={{ width: `${Math.max(4, Math.round((perYear / top) * 100))}%` }} />
              </div>
              <p className="muted text-sm">Les piles tiennent en moyenne {frDuration(Math.round(avg))}.</p>
            </div>
          ))}
        </div>
      )}

      {formats.length > 0 && (
        <div className="space-y-3">
          <h3 className="flex items-center gap-2 font-extrabold"><ShoppingBasket size={18} /> Piles à prévoir sur 12 mois</h3>
          <div className="grid gap-2 sm:grid-cols-2">
            {formats.map((f) => {
              const need = Math.ceil(needs.byFormat[f]);
              const h = have(f);
              const short = Math.max(0, need - h);
              return (
                <div key={f} className="flex items-center justify-between gap-3 rounded-2xl p-3" style={{ background: "var(--field)" }}>
                  <div>
                    <b className="text-lg">{f} standard</b>
                    <p className="muted text-sm">environ {need}, tu en as {h}</p>
                  </div>
                  <span className={cn("chip", short > 0 ? "tone-amber" : "tone-green")}>{short > 0 ? `Il en manque ${short}` : "Stock suffisant"}</span>
                </div>
              );
            })}
          </div>
          <p className="muted text-sm">
            Estimation d'après {needs.measured} équipement{needs.measured > 1 ? "s" : ""} mesuré{needs.measured > 1 ? "s" : ""}
            {needs.fromReminder > 0 ? ` et ${needs.fromReminder} rappel${needs.fromReminder > 1 ? "s" : ""}` : ""}.
            Les piles rechargeables ne sont pas comptées : elles reviennent au stock.
          </p>
        </div>
      )}

      {ranking.length > 0 && waiting.length > 0 && (
        <p className="muted text-sm">{waiting.length} équipement{waiting.length > 1 ? "s" : ""} en cours de mesure : {waiting.map((e) => e.name).join(", ")}.</p>
      )}
    </article>
  );
}

function AboutCard() {
  return (
    <article className="glass-card p-5">
      <h3 className="text-lg font-extrabold">À propos et soutien</h3>
      <p className="muted mt-1 text-sm">
        Battery Inventory {VERSION}. Un projet libre et gratuit (licence MIT). S'il te rend service, tu peux lui mettre une étoile sur GitHub
        ou soutenir son développement avec un petit don : ça aide à le maintenir.
      </p>
      <div className="mt-4 flex flex-wrap gap-2">
        <a className="btn btn-sm" href={REPO_URL} target="_blank" rel="noopener noreferrer">Voir le projet sur GitHub</a>
        <a className="btn btn-sm btn-primary" href={KOFI_URL} target="_blank" rel="noopener noreferrer">Faire un don</a>
        <a className="btn btn-sm" href={ISSUES_URL} target="_blank" rel="noopener noreferrer">Signaler un problème</a>
      </div>
    </article>
  );
}

function MqttCard() {
  const [s, setS] = useState(null);
  useEffect(() => {
    let alive = true;
    const load = () => api("api/mqtt").then((j) => alive && setS(j)).catch(() => alive && setS(null));
    load();
    const t = setInterval(load, 5000);
    return () => { alive = false; clearInterval(t); };
  }, []);
  const good = s && s.state === "connecté";
  const bad = s && ["erreur", "déconnecté"].includes(s.state);
  return (
    <article className="glass-card p-5">
      <div className="flex flex-wrap items-center gap-3">
        <h3 className="text-lg font-extrabold">Liaison avec Home Assistant</h3>
        <span className={cn("chip", good ? "tone-green" : bad ? "tone-red" : "tone-slate")}>{s ? s.state : "…"}</span>
      </div>
      <p className="muted mt-2 text-sm">
        {s ? s.detail : "Vérification en cours…"}
        {good && s.entities > 0 ? ` ${s.entities} éléments (capteurs, interrupteurs, boutons) sont visibles dans Home Assistant.` : ""}
      </p>
    </article>
  );
}

function DeadBadge() {
  return <span className="chip tone-red"><BatteryWarning size={15} /> Piles mortes</span>;
}

function StatChip({ label, value, icon, tone, onClick }) {
  const Tag = onClick ? "button" : "div";
  return (
    <Tag type={onClick ? "button" : undefined} onClick={onClick} data-stat={label} className={cn("stat-chip", tone && `tone-${tone}`)}>
      {icon}<b>{value}</b><span>{label}</span>
    </Tag>
  );
}

function TabButton({ active, onClick, icon, label }) {
  return (
    <button type="button" onClick={onClick} aria-current={active ? "page" : undefined}>
      {icon}<span>{label}</span>
    </button>
  );
}

function EquipmentCard({ item, life, edit, remove, replace, dead, undo }) {
  const isDead = !!item.deadSince;
  const info = reminderInfo(item);
  const needs = info && (info.status === "soon" || info.status === "due");
  return (
    <article className={cn("glass-card eq-card", isDead && "is-dead", !isDead && needs && "is-due")}>
      <div className="eq-photo">
        <Photo src={item.photo} name={item.name} category={item.category} />
        {isDead && <div className="badge"><DeadBadge /></div>}
        <div className="corner">
          <IconButton label={`Modifier ${item.name}`} onClick={edit} icon={<Pencil size={18} />} />
          <IconButton label={`Supprimer ${item.name}`} danger onClick={remove} icon={<Trash2 size={18} />} />
        </div>
      </div>
      <div className="space-y-3 p-4 pt-3">
        <div>
          <h3 className="text-lg font-extrabold leading-tight">{item.name}</h3>
          <p className="muted text-sm">{item.location}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <b className="text-xl">{item.quantity} × {item.format}</b>
          <Pill tone={item.rechargeable ? "teal" : "blue"}>{typeLabel(item.rechargeable)}</Pill>
          <span className="chip tone-slate">{item.category}</span>
        </div>
        {isDead && <p className="text-sm font-bold" style={{ color: "var(--t-red-fg)" }}>Signalées le {fmtDate(item.deadSince)}</p>}
        {(item.lastChange || info || (life && life.count > 0)) && (
          <div className="space-y-1.5 text-sm">
            {item.lastChange && <p className="muted">Piles changées {sinceText(item.lastChange)}</p>}
            {life && life.avgDays && (
              <p className="muted flex items-start gap-1.5"><Hourglass size={15} className="mt-0.5 flex-none" />
                <span>Durée moyenne : {frDuration(Math.round(life.avgDays))}. Prochain remplacement estimé : {nextText(life)}.</span>
              </p>
            )}
            {life && life.count === 1 && <p className="muted">Encore un remplacement pour estimer la durée de vie de ces piles.</p>}
            {info && (
              <span className={cn("chip", needs ? "tone-amber" : "tone-slate")}><CalendarClock size={15} /> {reminderText(info)}</span>
            )}
          </div>
        )}
        <div className="flex flex-wrap gap-2">
          <button type="button" className="btn btn-sm" onClick={replace}>{isDead ? "Remplacer les piles mortes" : "Remplacer les piles"}</button>
          {isDead ? <button type="button" className="btn btn-sm" onClick={undo}>Pas mortes</button> : <button type="button" className="btn btn-sm btn-soft-danger" onClick={dead}>Piles mortes</button>}
        </div>
      </div>
    </article>
  );
}

function SettingsCard({ title, icon, items, placeholder, onAdd, onRemove }) {
  const [v, setV] = useState("");
  return (
    <article className="glass-card p-5">
      <div className="flex items-center gap-3">
        <div className="bubble tone-teal">{icon}</div>
        <h3 className="text-lg font-extrabold">{title}</h3>
      </div>
      <form onSubmit={(e) => { e.preventDefault(); onAdd(v).then((ok) => ok && setV("")); }} className="mt-4 flex gap-2">
        <input aria-label={placeholder} className="field" value={v} onChange={(e) => setV(e.target.value)} placeholder={placeholder} />
        <button className="btn btn-primary">Ajouter</button>
      </form>
      <div className="mt-4 flex flex-wrap gap-2">
        {items.map((x) => (
          <span key={x} className="chip tone-slate" style={{ paddingRight: 4 }}>
            {x}
            <button type="button" aria-label={`Retirer ${x}`} onClick={() => onRemove(x)} className="grid h-7 w-7 place-items-center rounded-full" style={{ background: "transparent", border: 0 }}><X size={15} /></button>
          </span>
        ))}
      </div>
    </article>
  );
}

function Photo({ src, name, category, small }) {
  const [Icon, tint] = catOf(category);
  if (small) {
    return (
      <div className="photo-sm">
        {src ? <img src={src} alt={name} /> : <div className={cn("ph", `ph-${tint}`)} style={{ width: "100%", height: "100%", display: "grid", placeItems: "center" }}><Icon size={26} /></div>}
      </div>
    );
  }
  return src ? <img src={src} alt={name} /> : <div className={cn("ph", `ph-${tint}`)}><Icon size={54} strokeWidth={1.6} /></div>;
}

function Stepper({ value, onChange, min = 1, max = 99, label }) {
  const n = Number(value) || 0;
  return (
    <div className="stepper">
      <button type="button" className="btn btn-icon" aria-label={`Moins : ${label}`} onClick={() => onChange(Math.max(min, n - 1))}><Minus size={18} /></button>
      <input aria-label={label} className="field" type="number" required min={min} max={max} step="1" inputMode="numeric" value={value}
        onChange={(e) => onChange(e.target.value === "" ? "" : parseInt(e.target.value, 10))} />
      <button type="button" className="btn btn-icon" aria-label={`Plus : ${label}`} onClick={() => onChange(Math.min(max, n + 1))}><Plus size={18} /></button>
    </div>
  );
}

function Segmented({ value, onChange, label }) {
  const options = [{ value: false, label: "Standard" }, { value: true, label: "Rechargeable" }];
  return (
    <div className="seg" role="radiogroup" aria-label={label}>
      {options.map((o) => (
        <button key={String(o.value)} type="button" role="radio" aria-checked={value === o.value} onClick={() => onChange(o.value)}>{o.label}</button>
      ))}
    </div>
  );
}

function EquipmentForm({ initial, save, formats, categories, notify, busy: saving }) {
  const todayStr = new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10);
  const [v, setV] = useState(
    initial
      ? { ...initial, lastChange: (initial.lastChange || "").slice(0, 10), reminderMonths: initial.reminderMonths || "" }
      : { name: "", category: categories[0], location: "", format: formats[0], rechargeable: false, quantity: 2, photo: "", lastChange: todayStr, reminderMonths: "" }
  );
  const [busy, setBusy] = useState(false);
  const set = (k, x) => setV((p) => ({ ...p, [k]: x }));
  async function pickPhoto(e) {
    const f = e.target.files && e.target.files[0];
    e.target.value = "";
    if (!f) return;
    setBusy(true);
    try {
      const r = await api("api/photo", { dataUrl: await compressImage(f) });
      set("photo", r.path);
    } catch (err) {
      notify("Cette photo n'a pas pu être lue", true);
    }
    setBusy(false);
  }
  return (
    <form onSubmit={(e) => { e.preventDefault(); save({ ...v, name: v.name.trim(), location: v.location.trim(), quantity: Number(v.quantity), lastChange: v.lastChange || null, reminderMonths: v.reminderMonths === "" ? null : Number(v.reminderMonths) }); }} className="grid gap-4">
      {v.photo ? (
        <div className="preview">
          <img src={v.photo} alt={v.name || "Photo de l'équipement"} />
          <div className="absolute bottom-2 right-2 flex gap-2">
            <label className="btn btn-sm cursor-pointer"><Camera size={17} /> Changer<input type="file" accept="image/*" onChange={pickPhoto} className="sr-only" /></label>
            <button type="button" className="btn btn-sm" onClick={() => set("photo", "")}>Retirer</button>
          </div>
        </div>
      ) : (
        <label className="dropzone">
          <ImagePlus size={30} />
          <span>{busy ? "Envoi de la photo…" : "Ajouter une photo"}</span>
          <span className="text-sm font-semibold" style={{ opacity: 0.8 }}>Prends-la maintenant ou choisis-en une</span>
          <input type="file" accept="image/*" onChange={pickPhoto} className="sr-only" />
        </label>
      )}
      <label className="block"><span className="label">Nom</span><input required className="field" value={v.name} onChange={(e) => set("name", e.target.value)} placeholder="Ex. Télécommande du salon" /></label>
      <label className="block"><span className="label">Emplacement</span><input required className="field" value={v.location} onChange={(e) => set("location", e.target.value)} placeholder="Ex. Salon" /></label>
      <div className="grid grid-cols-2 gap-3">
        <label className="block"><span className="label">Catégorie</span><Select value={v.category} onChange={(e) => set("category", e.target.value)} options={categories} /></label>
        <label className="block"><span className="label">Format</span><Select value={v.format} onChange={(e) => set("format", e.target.value)} options={formats} /></label>
      </div>
      <div><span className="label">Type de piles</span><Segmented label="Type de piles" value={v.rechargeable} onChange={(x) => set("rechargeable", x)} /></div>
      <div><span className="label">Nombre de piles</span><Stepper label="Nombre de piles" value={v.quantity} onChange={(x) => set("quantity", x)} /></div>
      <div className="grid grid-cols-2 gap-3">
        <label className="block"><span className="label">Piles changées le</span><input type="date" className="field" max={todayStr} value={v.lastChange} onChange={(e) => set("lastChange", e.target.value)} /></label>
        <label className="block"><span className="label">Rappel tous les</span>
          <select className="field" value={String(v.reminderMonths)} onChange={(e) => set("reminderMonths", e.target.value === "" ? "" : Number(e.target.value))}>
            {REMINDER_CHOICES.map((o) => <option key={String(o.value)} value={String(o.value)}>{o.label}</option>)}
            {v.reminderMonths !== "" && !REMINDER_CHOICES.some((o) => o.value === v.reminderMonths) && <option value={String(v.reminderMonths)}>{v.reminderMonths} mois</option>}
          </select>
        </label>
      </div>
      <p className="muted text-sm">
        {initial ? "Si tu changes le format, le type ou le nombre de piles, le stock est corrigé automatiquement." : "Les piles installées sont retirées du stock."}
      </p>
      <button disabled={busy || saving} className="btn btn-primary w-full">Enregistrer</button>
    </form>
  );
}

function StockForm({ stock, save, formats, busy }) {
  const first = lineOf(stock, formats[0], false);
  const [v, setV] = useState({ format: formats[0], rechargeable: false, quantity: 4, minimum: first ? first.minimum : 2 });
  const set = (k, x) =>
    setV((p) => {
      const n = { ...p, [k]: x };
      if (k === "format" || k === "rechargeable") {
        const line = lineOf(stock, n.format, n.rechargeable);
        if (line) n.minimum = line.minimum;
      }
      return n;
    });
  return (
    <form onSubmit={(e) => { e.preventDefault(); save({ ...v, quantity: Number(v.quantity), minimum: Number(v.minimum) || 0 }); }} className="grid gap-4">
      <label className="block"><span className="label">Format</span><Select value={v.format} onChange={(e) => set("format", e.target.value)} options={formats} /></label>
      <div><span className="label">Type de piles</span><Segmented label="Type de piles" value={v.rechargeable} onChange={(x) => set("rechargeable", x)} /></div>
      <div><span className="label">Nombre de piles à ajouter</span><Stepper label="Nombre de piles à ajouter" max={999} value={v.quantity} onChange={(x) => set("quantity", x)} /></div>
      <div><span className="label">Alerte quand il en reste</span><Stepper label="Seuil d'alerte" min={0} max={999} value={v.minimum} onChange={(x) => set("minimum", x)} /></div>
      <button disabled={busy} className="btn btn-primary w-full">Ajouter au stock</button>
    </form>
  );
}

function Gauge({ quantity, minimum, need }) {
  const full = Math.max(minimum * 2, quantity, need, 1);
  const pct = Math.round((quantity / full) * 100);
  const tone = quantity === 0 ? "empty" : quantity <= minimum ? "low" : "ok";
  return (
    <div className="gauge" role="img" aria-label={`${quantity} pile${plural(quantity)} en stock, alerte à ${minimum}`}>
      <div className="gauge-body">
        <div className="gauge-fill" data-tone={tone} style={{ width: `${pct}%` }} />
        {minimum > 0 && <i className="gauge-tick" style={{ left: `calc(${Math.min(100, (minimum / full) * 100)}% - 1px)` }} />}
      </div>
      <div className="gauge-nub" />
    </div>
  );
}

function StockCard({ item, need, change, setMin, charged }) {
  const isLow = item.quantity <= item.minimum;
  const [min, setMinLocal] = useState(String(item.minimum));
  useEffect(() => setMinLocal(String(item.minimum)), [item.minimum]);
  return (
    <article className={cn("glass-card space-y-4 p-5", isLow && "is-low")} style={isLow ? { borderColor: "rgba(217,119,6,.65)", boxShadow: "var(--shadow), 0 0 0 3px rgba(245,158,11,.18)" } : undefined}>
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-1.5">
          <h3 className="text-3xl font-extrabold leading-none tracking-tight">{item.format}</h3>
          <Pill tone={item.rechargeable ? "teal" : "blue"}>{typeLabel(item.rechargeable)}</Pill>
        </div>
        <b className="text-5xl font-extrabold leading-none" style={isLow ? { color: "var(--t-amber-fg)" } : undefined}>{item.quantity}</b>
      </div>
      <Gauge quantity={item.quantity} minimum={item.minimum} need={need} />
      <div className="space-y-1 text-sm">
        {isLow && <p className="font-bold" style={{ color: "var(--t-amber-fg)" }}>Stock faible : pense à en racheter.</p>}
        <p className="muted">Pour tout remplacer d'un coup : {need} pile{plural(need)}{need > item.quantity ? " (il en manque)" : ""}</p>
      </div>
      {item.rechargeable && item.charging > 0 && (
        <div className="tone-teal flex items-center justify-between gap-2 rounded-2xl p-2 pl-4 text-sm font-bold" style={{ background: "var(--t-bg)", color: "var(--t-fg)" }}>
          <span>{item.charging} en recharge</span>
          <button type="button" className="btn btn-sm" onClick={charged}>Recharge terminée</button>
        </div>
      )}
      <div className="flex items-end justify-between gap-3">
        <label className="text-sm font-bold">
          <span className="label">Alerte à</span>
          <input type="number" min="0" step="1" className="field" style={{ width: 96 }} value={min} onChange={(e) => setMinLocal(e.target.value)}
            onBlur={() => Number(min) !== item.minimum && setMin(min)} onKeyDown={(e) => e.key === "Enter" && e.target.blur()} />
        </label>
        <div className="flex gap-2">
          <IconButton label={`Retirer une pile ${item.format}`} onClick={() => change(-1)} icon={<Minus size={20} />} />
          <IconButton label={`Ajouter une pile ${item.format}`} onClick={() => change(1)} icon={<Plus size={20} />} primary />
        </div>
      </div>
    </article>
  );
}

function IconButton({ icon, onClick, danger, primary, label }) {
  return (
    <button type="button" aria-label={label} title={label} onClick={onClick}
      className={cn("btn btn-icon", primary && "btn-primary", danger && "btn-soft-danger")}>
      {icon}
    </button>
  );
}

function Pill({ children, tone = "blue" }) {
  return <span className={cn("chip", `tone-${tone}`)}>{children}</span>;
}

function Modal({ title, close, children }) {
  const ref = useRef(null);
  useEffect(() => { ref.current && ref.current.focus(); }, []);
  return (
    <div className="overlay" onMouseDown={(e) => e.target === e.currentTarget && close()}>
      <div ref={ref} tabIndex={-1} role="dialog" aria-modal="true" aria-label={title} className="sheet glass glass-strong" style={{ outline: "none" }}>
        <div className="mb-4 flex items-center justify-between gap-3">
          <h2 className="text-xl font-extrabold">{title}</h2>
          <IconButton label="Fermer" onClick={close} icon={<X size={20} />} />
        </div>
        {children}
      </div>
    </div>
  );
}

function Select({ options, ...p }) {
  return (
    <select {...p} className="field">
      {options.map((x) => (typeof x === "string" ? <option key={x}>{x}</option> : <option key={x.value} value={x.value}>{x.label}</option>))}
    </select>
  );
}

function Empty({ icon, title, text, action }) {
  return (
    <div className="grid place-items-center gap-3 px-6 py-12 text-center">
      <div className="bubble tone-teal" style={{ width: 64, height: 64 }}>{icon}</div>
      <div><p className="text-lg font-extrabold">{title}</p>{text && <p className="muted mt-1">{text}</p>}</div>
      {action}
    </div>
  );
}
