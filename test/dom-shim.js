// Minimal DOM shim - just enough to execute the deck's slide builders under plain
// node and inspect the SVG they produce. Not a browser: no layout, no CSS, no
// text metrics. Enough to catch NaN coordinates, points outside the canvas,
// overlapping labels and builders that throw.
class N {
  constructor(tag, ns) {
    this.tagName = (tag || "").toLowerCase();
    this.ns = ns || null;
    this.attrs = {};
    this.children = [];
    this.childNodes = this.children;
    this._text = null;
    this._html = "";
    this.style = { cssText: "", setProperty() {} };
    this.dataset = {};
    this.listeners = {};
    const set = new Set();
    this.classList = {
      _s: set,
      add: (...c) => c.forEach(x => set.add(x)),
      remove: (...c) => c.forEach(x => set.delete(x)),
      toggle: (c, on) => { const v = on == null ? !set.has(c) : !!on; v ? set.add(c) : set.delete(c); return v; },
      contains: c => set.has(c),
    };
  }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  getAttribute(k) { return this.attrs[k]; }
  appendChild(c) { this.children.push(c); c.parentNode = this; return c; }
  addEventListener(t, f) { (this.listeners[t] = this.listeners[t] || []).push(f); }
  set className(v) { this.classList._s = new Set(String(v).split(/\s+/).filter(Boolean)); }
  get className() { return [...this.classList._s].join(" "); }
  set textContent(v) { this._text = v == null ? null : String(v); }
  get textContent() { return this._text; }
  set innerHTML(v) { this._html = String(v); if (v === "") this.children.length = 0; }
  get innerHTML() { return this._html; }
  get firstChild() { return this.children[0]; }
  find(tag, out) {
    out = out || [];
    if (this.tagName === tag) out.push(this);
    this.children.forEach(c => c.find && c.find(tag, out));
    return out;
  }
  allHtml() {
    let s = this._html || "";
    this.children.forEach(c => { s += c.allHtml ? c.allHtml() : ""; });
    return s;
  }
}
Object.defineProperty(N.prototype, "disabled", {
  set(v) { this._dis = v; }, get() { return this._dis; },
});

const ids = {};
["prev", "next", "label", "deck", "dots", "tip"].forEach(id => { ids[id] = new N("div"); });

global.document = {
  createElement: t => new N(t),
  createElementNS: (ns, t) => new N(t, ns),
  getElementById: id => (ids[id] = ids[id] || new N("div")),
};
global.window = global;
global.innerWidth = 1400;
global.innerHeight = 1000;
global.scrollTo = () => {};
global.addEventListener = () => {};
global.__ids = ids;
global.__N = N;
