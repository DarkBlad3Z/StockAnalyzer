// Executes every slide builder in index.html under the DOM shim and asserts the
// generated SVG is sane. Catches the failure modes that are invisible in a
// screenshot of slide 1:
//
//   * a builder that throws (one bad slide, seven working ones, no error anywhere)
//   * NaN / Infinity coordinates from a log scale fed a zero or negative value
//   * dots or labels drawn outside the viewBox
//   * labels overlapping each other
//   * halo and fill text passes out of sync (the two-pass legibility trick)
//
// Usage: node test/check-charts.js        (from the repo root)
// Exit code 1 on any failure, so it drops straight into CI.
const fs = require("fs");
const path = require("path");
require(path.join(__dirname, "dom-shim.js"));

const ROOT = path.dirname(__dirname);
const html = fs.readFileSync(path.join(ROOT, "index.html"), "utf8");
const m = html.match(/<script>([\s\S]*)<\/script>/);
if (!m) { console.error("no <script> block found in index.html"); process.exit(1); }

const warnings = [];
console.warn = (...a) => warnings.push(a.join(" "));
const log = console.log;
console.log = () => {};
(0, eval)(m[1] + "\n;globalThis.__slides=slides;globalThis.__go=go;globalThis.__built=built;");
console.log = log;

const slides = globalThis.__slides, go = globalThis.__go, built = globalThis.__built;
let failures = 0;

console.log("slide                         svg  dots  labels  tables   issues");
console.log("-".repeat(74));

for (let i = 0; i < slides.length; i++) {
  let host;
  try { go(i); host = built[i]; }
  catch (e) {
    console.log(`${String(i + 1).padStart(2)} ${slides[i].label.padEnd(26)} THREW: ${e.message}`);
    failures++; continue;
  }
  const svgs = host.find("svg");
  let dots = 0, fills = 0, halos = 0, bad = 0, oob = 0, labOut = 0, labOverlap = 0;

  svgs.forEach(s => {
    const vb = (s.getAttribute("viewBox") || "0 0 0 0").split(" ").map(Number);
    s.find("circle").forEach(c => {
      dots++;
      const x = +c.getAttribute("cx"), y = +c.getAttribute("cy"), r = +c.getAttribute("r");
      if (![x, y, r].every(Number.isFinite) || r <= 0) bad++;
      else if (x < 0 || y < 0 || x > vb[2] || y > vb[3]) oob++;
    });
    const texts = s.find("text");
    halos += texts.filter(t => t.getAttribute("fill") === "none").length;
    const labels = texts.filter(t => t.getAttribute("fill") === "#15130f" &&
                                     t.getAttribute("font-weight") === "700");
    fills += labels.length;
    const boxes = labels.map(t => {
      const fs_ = +t.getAttribute("font-size");
      const w = (t.textContent || "").length * fs_ * 0.54 + 4;
      const x = +t.getAttribute("x"), y = +t.getAttribute("y");
      const an = t.getAttribute("text-anchor");
      const x0 = an === "start" ? x : an === "end" ? x - w : x - w / 2;
      return { x: x0, y: y - fs_, w, h: fs_ + 2 };
    });
    boxes.forEach(b => {
      if (b.x < -1 || b.y < -1 || b.x + b.w > vb[2] + 1 || b.y + b.h > vb[3] + 1) labOut++;
    });
    for (let a = 0; a < boxes.length; a++)
      for (let c = a + 1; c < boxes.length; c++) {
        const p = boxes[a], q = boxes[c];
        if (!(p.x + p.w < q.x || q.x + q.w < p.x || p.y + p.h < q.y || q.y + q.h < p.y)) labOverlap++;
      }
  });

  const issues = [];
  if (bad) issues.push(`${bad} bad coords`);
  if (oob) issues.push(`${oob} dots outside canvas`);
  if (labOut) issues.push(`${labOut} labels outside canvas`);
  if (labOverlap) issues.push(`${labOverlap} label overlaps`);
  if (fills !== halos) issues.push(`halo/fill mismatch ${halos}/${fills}`);
  if (issues.length) failures++;

  console.log(`${String(i + 1).padStart(2)} ${slides[i].label.padEnd(26)}` +
    `${String(svgs.length).padStart(3)}${String(dots).padStart(6)}` +
    `${String(fills).padStart(8)}${String(host.find("table").length).padStart(8)}   ` +
    (issues.length ? issues.join(", ") : "ok"));
}

console.log("");
if (warnings.length) {
  console.log("labels the placer could not fit (expected in dense regions):");
  warnings.forEach(w => console.log("  " + w));
  console.log("");
}
if (failures) { console.log(`FAILED: ${failures} slide(s) with issues`); process.exit(1); }
console.log(`PASS: ${slides.length} slides, geometry clean, zero label overlaps`);
