// Vérifie que l'interface (JavaScript) et le serveur (Python) calculent exactement les mêmes échéances de rappel.
import { execFileSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { reminderInfo, parseDay } from "../../frontend/src/helpers.js";

const here = path.dirname(fileURLToPath(import.meta.url));
const addon = path.resolve(here, "../../battery_inventory");
// Cas tirés au sort (graine fixe) : la même liste est envoyée au serveur Python.
let seed = 7;
const rnd = () => ((seed = (seed * 1664525 + 1013904223) % 4294967296) / 4294967296);
const day0 = Date.UTC(2020, 0, 1);
const fmt = (ms) => new Date(ms).toISOString().slice(0, 10);
const cases = [];
for (let i = 0; i < 2000; i++) {
  const start = day0 + Math.floor(rnd() * 3000) * 86400000;
  const today = start + Math.floor(rnd() * 1500) * 86400000;
  const n = [1, 2, 3, 6, 12, 18, 24, 36][Math.floor(rnd() * 8)];
  cases.push({ start: fmt(start), today: fmt(today), n });
}
const py = `
import json, sys
from datetime import date
sys.path.insert(0, ${JSON.stringify(addon)})
import logic
out = []
for c in json.load(sys.stdin):
    i = logic.reminder_info({"reminderMonths": c["n"], "lastChange": c["start"] + "T12:00:00.000Z"}, date.fromisoformat(c["today"]))
    out.append(i)
print(json.dumps(out))
`;
const expected = JSON.parse(execFileSync("python3", ["-c", py], { input: JSON.stringify(cases) }).toString());
let bad = 0;
cases.forEach((c, i) => {
  const r = reminderInfo({ reminderMonths: c.n, lastChange: c.start + "T12:00:00.000Z" }, parseDay(c.today));
  const e = expected[i];
  if (r.status !== e.status || r.due !== e.due || r.days !== e.days) { bad++; if (bad < 4) console.log("ECART", c, r, e); }
});
console.log(bad ? `ECHEC ${bad} écarts sur ${cases.length}` : `TOUT PASSE : interface et serveur donnent les mêmes résultats sur ${cases.length} cas`);
process.exit(bad ? 1 : 0);
