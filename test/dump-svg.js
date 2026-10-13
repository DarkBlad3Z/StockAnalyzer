// Serialises one slide's chart to a standalone .svg file, so you can eyeball a
// chart without opening a browser (and rasterise it in CI with ImageMagick or
// rsvg-convert to diff against a committed reference).
//
// Usage: node test/dump-svg.js <slide-number> <out.svg>
//        node test/dump-svg.js 3 giants.svg
//
// Slides with a grid of panels (the sector grid) are tiled three across.
// Note: ImageMagick's built-in SVG renderer ignores paint-order and nested <svg>
// positioning. The deck does not rely on paint-order, but tiled output will look
// wrong there - use rsvg-convert or a browser for that one.
const fs = require("fs");
const path = require("path");
require(path.join(__dirname, "dom-shim.js"));

const ROOT = path.dirname(__dirname);
const html = fs.readFileSync(path.join(ROOT, "index.html"), "utf8");
const m = html.match(/<script>([\s\S]*)<\/script>/);
if (!m) { console.error("no <script> block in index.html"); process.exit(1); }

console.warn = () => {};
const log = console.log;
console.log = () => {};
(0, eval)(m[1] + "\n;globalThis.__slides=slides;globalThis.__go=go;globalThis.__built=built;");
console.log = log;

const n = Number(process.argv[2]);
const out = process.argv[3];
if (!n || !out) {
  console.error("usage: node test/dump-svg.js <slide-number 1-%d> <out.svg>",
                globalThis.__slides.length);
  process.exit(1);
}

const esc = s => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
function ser(node) {
  if (node.tagName === "svg") node.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  const attrs = Object.entries(node.attrs)
    .map(([k, v]) => ` ${k}="${String(v).replace(/"/g, "&quot;")}"`).join("");
  const text = node.textContent != null ? esc(node.textContent) : "";
  return `<${node.tagName}${attrs}>${text}${node.children.map(ser).join("")}</${node.tagName}>`;
}

globalThis.__go(n - 1);
const svgs = globalThis.__built[n - 1].find("svg");
if (!svgs.length) { console.error("slide %d has no chart", n); process.exit(1); }

let body;
if (svgs.length === 1) {
  body = ser(svgs[0]);
} else {
  const cols = 3, w = 430, h = 320, rows = Math.ceil(svgs.length / cols);
  body = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${cols * w} ${rows * h}">` +
    `<rect width="${cols * w}" height="${rows * h}" fill="#faf7f1"/>` +
    svgs.map((s, i) => {
      s.setAttribute("x", (i % cols) * w);
      s.setAttribute("y", Math.floor(i / cols) * h);
      s.setAttribute("width", w);
      s.setAttribute("height", h);
      return ser(s);
    }).join("") + `</svg>`;
}

fs.writeFileSync(out, body.replace("<svg ", '<svg style="background:#faf7f1" '));
console.log("wrote %s  (%d svg element(s), %d bytes)", out, svgs.length, body.length);
