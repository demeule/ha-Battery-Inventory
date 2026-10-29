// Compile l'interface en UN seul fichier HTML (CSS et JavaScript inclus) :
//   ../battery_inventory/web/index.html
// Usage : npm install && npm run build
const esbuild = require("esbuild");
const fs = require("fs");
const path = require("path");
const cp = require("child_process");

const root = __dirname;
const addon = path.join(root, "..", "battery_inventory");
const version = (/^version:\s*"?([^"\s]+)"?/m.exec(fs.readFileSync(path.join(addon, "config.yaml"), "utf8")) || [])[1] || "dev";

fs.mkdirSync(path.join(root, "dist"), { recursive: true });
cp.execSync("npx tailwindcss -c tailwind.config.cjs -i src/input.css -o dist/app.css --minify", { cwd: root, stdio: "inherit" });

const result = esbuild.buildSync({
  entryPoints: [path.join(root, "src/main.jsx")],
  bundle: true,
  minify: true,
  write: false,
  format: "iife",
  target: ["es2019"],
  define: { "process.env.NODE_ENV": '"production"', __APP_VERSION__: JSON.stringify(version) },
  loader: { ".js": "jsx" },
  legalComments: "none",
});
const js = result.outputFiles[0].text.replace(/<\/script/gi, "<\\/script");
const css = fs.readFileSync(path.join(root, "dist/app.css"), "utf8");
const icon = fs.readFileSync(path.join(root, "assets/icon-180.png")).toString("base64");

const html = `<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#0f766e">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="description" content="Battery Inventory : inventaire des piles de la maison">
<title>\u{1F50B} Battery Inventory</title>
<link rel="icon" type="image/png" href="data:image/png;base64,${icon}">
<link rel="apple-touch-icon" href="data:image/png;base64,${icon}">
<style>${css}</style></head>
<body><div id="root"></div><script>${js}</script></body></html>`;

fs.mkdirSync(path.join(addon, "web"), { recursive: true });
fs.writeFileSync(path.join(addon, "web", "index.html"), html);
console.log(`OK battery_inventory/web/index.html (${(html.length / 1024).toFixed(0)} Ko, version ${version})`);
