// Petites fonctions d'affichage (les vraies règles de calcul sont dans le serveur).
export const typeLabel = (rechargeable) => (rechargeable ? "Rechargeable" : "Standard");
const plural = (n) => (n > 1 ? "s" : "");
export const describe = (q, format, rechargeable) =>
  `${q} pile${plural(q)} ${format} ${rechargeable ? "rechargeable" : "standard"}${plural(q)}`;
export const lineOf = (stock, format, rechargeable) => stock.find((x) => x.format === format && x.rechargeable === rechargeable);

// ---------- Dates, durées et rappels (mêmes règles que le serveur) ----------
const SOON_DAYS = 14;

export function parseDay(text) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(text || ""));
  return m ? { y: +m[1], m: +m[2], d: +m[3] } : null;
}
export const localToday = (now = new Date()) => ({ y: now.getFullYear(), m: now.getMonth() + 1, d: now.getDate() });
const utcMs = (x) => Date.UTC(x.y, x.m - 1, x.d);
export const daysBetween = (a, b) => Math.round((utcMs(b) - utcMs(a)) / 86400000);

export function addMonths(x, n) {
  const total = x.y * 12 + (x.m - 1) + n;
  const y = Math.floor(total / 12);
  const m = (total % 12) + 1;
  const last = new Date(Date.UTC(y, m, 0)).getUTCDate();
  return { y, m, d: Math.min(x.d, last) };
}
const iso = (x) => `${String(x.y).padStart(4, "0")}-${String(x.m).padStart(2, "0")}-${String(x.d).padStart(2, "0")}`;

// status : ok | soon | due | unknown ; null s'il n'y a pas de rappel
export function reminderInfo(e, today = localToday()) {
  const n = e.reminderMonths;
  if (!n) return null;
  const start = e.lastChange ? parseDay(e.lastChange) : null;
  if (!start) return { status: "unknown", due: null, days: null };
  const due = addMonths(start, n);
  const days = daysBetween(today, due);
  return { status: days <= 0 ? "due" : days <= SOON_DAYS ? "soon" : "ok", due: iso(due), days };
}

// « 3 jours », « 5 semaines », « 8 mois », « 2 ans »
export function frDuration(days) {
  if (days < 14) return `${days} jour${days > 1 ? "s" : ""}`;
  if (days < 60) return `${Math.round(days / 7)} semaines`;
  if (days < 730) return `${Math.round(days / 30.44)} mois`;
  return `${Math.round(days / 365.25)} ans`;
}
export function sinceText(isoText, now = Date.now()) {
  const t = Date.parse(isoText);
  if (Number.isNaN(t)) return "";
  const days = Math.max(0, Math.floor((now - t) / 86400000));
  return days === 0 ? "aujourd'hui" : days === 1 ? "hier" : `il y a ${frDuration(days)}`;
}
export function reminderText(info) {
  if (!info) return "";
  if (info.status === "unknown") return "Rappel : indique la date du dernier changement";
  const { days } = info;
  if (info.status === "ok") return `Rappel dans ${frDuration(days)}`;
  if (info.status === "soon") return days === 1 ? "À changer demain" : `À changer bientôt, dans ${frDuration(days)}`;
  return days === 0 ? "À changer aujourd'hui" : `À changer depuis ${frDuration(-days)}`;
}
export const REMINDER_CHOICES = [
  { value: "", label: "Aucun" },
  { value: 3, label: "3 mois" },
  { value: 6, label: "6 mois" },
  { value: 12, label: "1 an" },
  { value: 24, label: "2 ans" },
];

// ---------- Durée de vie des piles et bilan (calculés à partir de l'historique) ----------
const DAY = 86400000;
const MONTHS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"];
const MIN_INTERVAL_DAYS = 2;   // deux changements à moins de 2 jours d'écart = erreur de manipulation, on les ignore
const RECENT = 5;              // la moyenne porte sur les 5 derniers intervalles

// Dates où les piles d'un équipement ont été changées : installation, remplacements, et la date saisie à la main.
export function changeDates(e, history) {
  const t = [];
  for (const h of history) {
    if (h.equipmentId === e.id && (h.type === "installation" || h.type === "remplacement")) {
      const v = Date.parse(h.date);
      if (!Number.isNaN(v)) t.push(v);
    }
  }
  if (e.lastChange) {
    const v = Date.parse(e.lastChange);
    if (!Number.isNaN(v)) t.push(v);
  }
  t.sort((a, b) => a - b);
  return t.filter((v, i) => i === 0 || v - t[i - 1] >= DAY);   // la date saisie et la ligne d'historique du même jour comptent une fois
}

// count = nombre de durées mesurées ; avgDays seulement à partir de 2 mesures (sinon ce serait inventé)
export function lifeStats(e, history) {
  const dates = changeDates(e, history);
  const intervals = [];
  for (let i = 1; i < dates.length; i++) {
    const days = (dates[i] - dates[i - 1]) / DAY;
    if (days >= MIN_INTERVAL_DAYS) intervals.push(days);
  }
  const recent = intervals.slice(-RECENT);
  const enough = recent.length >= 2;
  const avgDays = enough ? recent.reduce((a, b) => a + b, 0) / recent.length : null;
  const last = dates.length ? dates[dates.length - 1] : null;
  return {
    count: intervals.length,
    avgDays,
    last,
    nextAt: enough && last ? last + avgDays * DAY : null,
    perYear: enough ? (e.quantity * 365) / avgDays : null,
  };
}

// « début février », « mi-janvier », « fin mars 2027 »
export function approxMonth(ts, now = Date.now()) {
  const d = new Date(ts);
  const day = d.getDate();
  const month = MONTHS[d.getMonth()];
  const year = d.getFullYear() !== new Date(now).getFullYear() ? ` ${d.getFullYear()}` : "";
  return `${day <= 10 ? "début " : day <= 20 ? "mi-" : "fin "}${month}${year}`;
}
export function nextText(stats, now = Date.now()) {
  if (!stats.nextAt) return "";
  const days = Math.round((stats.nextAt - now) / DAY);
  if (days <= 0) return "à prévoir maintenant";
  if (days <= 14) return `dans environ ${frDuration(days)}`;
  return approxMonth(stats.nextAt, now);
}

// Piles standard à prévoir sur 12 mois, par format : d'après la durée mesurée, sinon d'après le rappel de l'équipement.
export function yearlyNeeds(equipment, statsById) {
  const byFormat = {};
  let measured = 0, fromReminder = 0;
  for (const e of equipment) {
    if (e.rechargeable) continue;   // les rechargeables reviennent au stock : pas d'achat
    const s = statsById[e.id];
    let perYear = null;
    if (s && s.perYear) { perYear = s.perYear; measured++; }
    else if (e.reminderMonths) { perYear = (e.quantity * 12) / e.reminderMonths; fromReminder++; }
    if (perYear == null) continue;
    byFormat[e.format] = (byFormat[e.format] || 0) + perYear;
  }
  return { byFormat, measured, fromReminder };
}
