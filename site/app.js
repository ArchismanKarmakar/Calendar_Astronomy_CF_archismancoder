/* The Deep Space Explorer 2027 — calendar maker front end. No framework; the heavy
   lifting happens in worker.js (the kit's Python, run by Pyodide). */
"use strict";
(() => {
const CFG = window.SITE_CONFIG || {};
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const h = (tag, attrs = {}, ...kids) => {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "html") el.innerHTML = v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const c of kids.flat()) if (c != null && c !== false) el.append(c.nodeType ? c : String(c));
  return el;
};
const store = {
  get(k, d) { try { const v = localStorage.getItem(k); return v ? JSON.parse(v) : d; } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* private mode */ } },
};
const getJSON = async (u) => { const r = await fetch(u); if (!r.ok) throw new Error(`${u}: HTTP ${r.status}`); return r.json(); };

const SLOTS = ["cover", "01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12"];
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
  "November", "December"];
const slotName = (s) => (s === "cover" ? "Cover" : MONTHS[+s - 1]);
const PAPER = { ISO: { wall: "A3 portrait", desk: "A5 landscape" }, US: { wall: "Tabloid 11×17 in", desk: "Half-letter landscape" } };
const SRC_NAME = { eso: "ESO", esahubble: "ESA/Hubble", esawebb: "ESA/Webb", noirlab: "NOIRLab", commons: "Wikimedia Commons",
  licensed: "Photographer", own: "Your photo" };

let CITIES = [], LIB = { slots: [], images: {} }, BUILD = {}, SAMPLE = null, HOLS = [], READY = null, FESTS = [];
const holCache = new Map();
const state = {
  code: null, format: "wall", paper: null, week: null, dpi: 200, title: "", subtitle: "",
  hol: "auto",  // "auto" = the city's country, "" = none, or a holiday file key such as "IN"
  fest: "auto", // "auto" = the city's default festival set, "" = none, or a set key such as "bengali"
  images: {},   // slot -> image id
  extra: {},    // id -> metadata for images added on this site (ESO/ESA lookups and own photos)
};
const uploads = new Map(); // own-photo id -> {bytes: ArrayBuffer, ext, url}
const sent = new Set();    // own photos already handed to the worker

const imgInfo = (id) => LIB.images[id] || state.extra[id];
const cityOf = (code) => CITIES.find((c) => c.code === code);

/* ------------------------------------------------------------ boot */
async function boot() {
  bindRedLight();
  try {
    [CITIES, LIB, BUILD] = await Promise.all([getJSON("data/cities.json"), getJSON("data/library.json"),
      getJSON("data/build.json")]);
  } catch (e) {
    $("#hero-city").textContent = "The site data is missing — run make_site.py and push again.";
    console.error(e);
    return;
  }
  [SAMPLE, HOLS, READY, FESTS] = await Promise.all([getJSON("sample/pages.json").catch(() => null),
    getJSON("data/holidays.json").catch(() => []), getJSON("data/downloads.json").catch(() => null),
    getJSON("data/festivals.json").catch(() => [])]);
  restore();
  renderEditions();
  fillCities();
  fillHolidays();
  fillPreviewPages();
  syncForm();
  renderTiles();
  bindForm();
  renderSample("wall");
  renderDonate();
  hero();
  if (CFG.author) { $("#author").textContent = CFG.author.name; $("#author").href = CFG.author.url; }
  $("#build-info").textContent = BUILD.built ? ` · data updated ${BUILD.built.slice(0, 10)}` : "";
}

/* ------------------------------------------------------------ state */
function defaults() {
  const out = {};
  for (const s of LIB.slots) {
    const ds = [].concat(s.default);
    out[s.slot] = ds.find((id) => LIB.images[id]) || s.options[0];
  }
  return out;
}
function detectCode() {
  let tz = "";
  try { tz = Intl.DateTimeFormat().resolvedOptions().timeZone || ""; } catch (e) { /* old browser */ }
  const exact = CITIES.filter((c) => c.tz === tz);
  if (exact.length) return (exact.find((c) => c.print_edition) || exact[0]).code;
  const off = -new Date(2027, 0, 15).getTimezoneOffset();
  let best = null, bestD = 1e9;
  for (const c of CITIES) {
    const o = tzOffset(c.tz);
    if (o != null && Math.abs(o - off) < bestD) { bestD = Math.abs(o - off); best = c; }
  }
  return (best || CITIES.find((c) => c.code === "UK") || CITIES[0]).code;
}
function tzOffset(tz) {
  try {
    const d = new Date(Date.UTC(2027, 0, 15, 12));
    const s = d.toLocaleString("en-US", { timeZone: tz, hour12: false, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
    const [md, t] = s.split(", ");
    const [mo, da, yr] = md.split("/").map(Number);
    const [hh, mi] = t.split(":").map(Number);
    return (Date.UTC(yr, mo - 1, da, hh % 24, mi) - d) / 60000;
  } catch (e) { return null; }
}
function restore() {
  const saved = store.get("dse27", {});
  Object.assign(state, { format: "wall", dpi: 200 }, saved);
  state.images = Object.assign(defaults(), saved.images || {});
  // drop own photos (their bytes aren't kept between visits) and unknown ids
  for (const s of SLOTS) {
    const i = imgInfo(state.images[s]);
    if (!i || i.source === "own") state.images[s] = defaults()[s];
  }
  for (const [id, m] of Object.entries(state.extra)) if (m.source === "own") delete state.extra[id];
  fromHash();
  if (!state.code || !cityOf(state.code)) state.code = detectCode();
}
function save() {
  const { code, format, paper, week, dpi, title, subtitle, images, extra, hol, fest } = state;
  store.set("dse27", { code, format, paper, week, dpi, title, subtitle, images, extra, hol, fest });
}
function shareURL() {
  const d = defaults();
  const p = new URLSearchParams({ city: state.code, fmt: state.format, dpi: state.dpi });
  if (state.paper) p.set("paper", state.paper);
  if (state.week != null) p.set("week", state.week);
  if (state.hol !== "auto") p.set("hol", state.hol || "none");
  const changed = SLOTS.filter((s) => state.images[s] !== d[s] && imgInfo(state.images[s])?.source !== "own")
    .map((s) => {
      const i = imgInfo(state.images[s]);
      return `${s}.${i.id}${LIB.images[i.id] ? "" : "." + i.source}`;
    });
  if (changed.length) p.set("img", changed.join(","));
  return `${location.origin}${location.pathname}#${p}`;
}
function fromHash() {
  if (!location.hash.includes("=")) return;
  const p = new URLSearchParams(location.hash.slice(1));
  if (p.get("city")) state.code = p.get("city");
  if (["wall", "desk"].includes(p.get("fmt"))) state.format = p.get("fmt");
  if (["150", "200", "300"].includes(p.get("dpi"))) state.dpi = +p.get("dpi");
  if (["ISO", "US"].includes(p.get("paper"))) state.paper = p.get("paper");
  if (["0", "6"].includes(p.get("week"))) state.week = +p.get("week");
  if (p.get("hol")) state.hol = p.get("hol") === "none" ? "" : p.get("hol");
  const pending = [];
  for (const part of (p.get("img") || "").split(",").filter(Boolean)) {
    const [slot, id, src] = part.split(".");
    if (!SLOTS.includes(slot)) continue;
    if (LIB.images[id]) state.images[slot] = id;
    else if (["eso", "esahubble", "esawebb"].includes(src)) pending.push([slot, id, src]);
  }
  // images added by ID: look them up, then select
  pending.forEach(async ([slot, id, src]) => {
    try {
      const m = await lookup(id, src);
      state.extra[m.id] = m;
      state.images[slot] = m.id;
      renderTiles(); save();
    } catch (e) { console.warn("could not restore", id, e); }
  });
}

/* ------------------------------------------------------------ hero */
async function hero() {
  const c = cityOf(state.code);
  if (!c) return;
  try {
    const ed = await getJSON(`data/editions/${c.code}.json`);
    const dark = Object.values(ed.illum).filter((v) => v <= 25).length;
    const ecl = ed.events.filter((e) => e.cat === "eclipse" && e.local_visible).length;
    const met = ed.events.filter((e) => e.cat === "meteor").length;
    const com = ed.events.filter((e) => e.cat === "comet").length;
    const ul = $("#stats");
    ul.innerHTML = "";
    const chip = (n, label) => h("li", {}, h("b", {}, String(n)), ` ${label}`);
    ul.append(h("li", { class: "city" }, `From ${c.city} in 2027:`), chip(dark, "dark-sky nights"),
      chip(ecl, ecl === 1 ? "eclipse you can see" : "eclipses you can see"), chip(met, "meteor-shower peaks"), chip(com, "comets"));
    countUp(ul);
    ticker(ed, c);
  } catch (e) { console.warn(e); }
}
function countUp(ul) {
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  $$("b", ul).forEach((b) => {
    const to = +b.textContent, t0 = performance.now();
    const step = (t) => { const k = Math.min(1, (t - t0) / 900); b.textContent = String(Math.round(to * (1 - (1 - k) ** 3))); if (k < 1) requestAnimationFrame(step); };
    requestAnimationFrame(step);
  });
}
/** A slow band of 2027's highlights, as seen from the visitor's city. */
function ticker(ed, c) {
  const box = $("#ticker");
  if (!box) return;
  const big = (e) => e.cat === "eclipse" || e.cat === "conj_planet" || e.cat === "interstellar"
    || (e.cat === "meteor" && (parseInt(e.zhr, 10) >= 50 || /outburst/i.test(e.name)))
    || (e.cat === "planet" && /opposition/i.test(e.name)) || (e.cat === "moon_extreme" && /Supermoon/.test(e.name))
    || (e.cat === "comet" && /mag/.test(e.short));
  const seen = new Set();
  const items = ed.events.filter(big).filter((e) => !seen.has(e.short) && seen.add(e.short)).map((e) => {
    const d = new Date(e.local_date + "T12:00:00Z");
    const when = d.toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });
    const note = e.cat === "eclipse" ? (e.local_visible ? `visible from ${c.city}` : "not visible here")
      : e.cat === "meteor" && e.zhr ? `up to ${e.zhr} an hour` : "";
    const name = e.short === e.short.toUpperCase() ? e.name.split(" — ")[0] : e.short;
    return h("li", { class: e.cat === "eclipse" && e.local_visible ? "hot" : null },
      h("time", { datetime: e.local_date }, when), h("b", {}, name), note ? h("span", {}, note) : null);
  });
  if (!items.length) return;
  const list = h("ul", {}, items);
  box.innerHTML = "";
  const copy = list.cloneNode(true);
  copy.setAttribute("aria-hidden", "true");
  box.append(list, copy);
  box.style.setProperty("--dur", `${Math.max(40, items.length * 4.5)}s`);
  $("#ticker-wrap").hidden = false;
}

/* ------------------------------------------------------------ ready-made */
function renderEditions() {
  const box = $("#editions");
  box.innerHTML = "";
  if (!READY || !READY.items || !READY.items.length) {
    box.append(h("p", { class: "ed-empty" }, "Ready-made calendars are being prepared. Meanwhile, make your own below."));
    return;
  }
  for (const it of READY.items) {
    const f = it.files;
    const link = (fmt, label) => f[fmt] ? h("a", { href: f[fmt].file, download: "", "aria-label": `Download the ${it.label} ${label.toLowerCase()} calendar, ${f[fmt].paper}, ${f[fmt].mb} MB PDF` },
      h("span", {}, label), h("small", {}, `${f[fmt].paper.split(" ")[0]} · ${Math.round(f[fmt].mb)} MB`)) : null;
    box.append(h("article", { class: "ed" },
      h("img", { src: it.cover, alt: `Cover of the ${it.label} edition`, loading: "lazy", width: 112, height: 158 }),
      h("div", {},
        h("h3", {}, it.label),
        h("p", { class: "meta" }, `${it.tzname}, computed for ${it.city}`),
        h("span", { class: "hol" }, it.holidays ? h("i") : null, it.holidays ? `${it.holidays} public holidays` : "No public holidays"),
        it.festivals ? h("span", { class: "hol" }, h("i", { class: "f" }), it.festivals) : null,
        h("div", { class: "dl" }, link("wall", "Wall"), link("desk", "Desk")))));
  }
}

/* ------------------------------------------------------------ holidays */
function fillHolidays() {
  const sel = $("#holidays");
  sel.innerHTML = "";
  sel.append(h("option", { value: "" }, "No holidays"));
  const c = cityOf(state.code);
  const local = c && c.holiday_key && c.holiday_key.includes("-") ? c.holiday_key : null;
  if (local) sel.append(h("option", { value: local }, `${HOLS.find((x) => x.key === c.country)?.name || c.country} (${local.split("-")[1]})`));
  const g = h("optgroup", { label: "Countries" });
  for (const x of HOLS) g.append(h("option", { value: x.key }, x.name));
  sel.append(g);
}
function holKey() {
  if (state.hol !== "auto") return state.hol;
  const c = cityOf(state.code);
  const k = c && c.holiday_key;
  if (!k) return "";
  const base = k.split("-")[0];
  return HOLS.some((x) => x.key === base) ? k : "";
}
function festKey() {
  const c1 = cityOf(state.code);
  if (state.fest && state.fest !== "auto" && !FESTS.some((f) => f.key === state.fest && f.country === (c1 && c1.country))) return "";
  if (state.fest !== "auto") return state.fest;
  const c = cityOf(state.code);
  return (c && c.festivals) || "";
}
async function festivalSpec() {
  const key = festKey();
  if (!key) return null;
  if (!holCache.has("f:" + key)) holCache.set("f:" + key, await getJSON(`data/festivals/${key}.json`));
  const d = holCache.get("f:" + key);
  return { name: d.name, days: d.days };
}
async function holidaySpec() {
  const key = holKey();
  if (!key) return null;
  if (!holCache.has(key)) holCache.set(key, await getJSON(`data/holidays/${key}.json`));
  const d = holCache.get(key);
  return { country: d.name, days: d.days };
}

/* ------------------------------------------------------------ red light */
function bindRedLight() {
  const b = $("#redlight");
  const on = () => document.documentElement.dataset.theme === "red";
  b.setAttribute("aria-pressed", on());
  b.addEventListener("click", () => {
    if (on()) delete document.documentElement.dataset.theme; else document.documentElement.dataset.theme = "red";
    b.setAttribute("aria-pressed", on());
    try { localStorage.setItem("dse27-red", on() ? "1" : "0"); } catch (e) { /* ignore */ }
  });
}

/* ------------------------------------------------------------ sample */
function renderSample(fmt) {
  const strip = $("#strip");
  strip.innerHTML = "";
  strip.className = "strip " + fmt;
  if (!SAMPLE) { strip.append(h("p", { class: "hint" }, "Sample pages appear here after make_site.py runs.")); return; }
  const ed = cityOf(SAMPLE.edition);
  $("#sample-ed").textContent = ed ? ed.label : SAMPLE.edition;
  const names = SAMPLE.pages[fmt] || [];
  const label = (i) => (i === 0 ? "Cover" : i === 1 ? "How to read" : i === names.length - 1 ? "Year at a glance" : MONTHS[i - 2]);
  names.forEach((n, i) => {
    strip.append(h("figure", { style: "margin:0" },
      h("button", { type: "button", "aria-label": `Open ${label(i)}`, onclick: () => openLightbox(fmt, i) },
        h("img", { src: `sample/${n}`, alt: `${label(i)} page`, loading: i < 3 ? "eager" : "lazy" })),
      h("figcaption", {}, label(i))));
  });
}
let lb = { fmt: "wall", i: 0 };
function openLightbox(fmt, i) {
  lb = { fmt, i };
  showLb();
  $("#lightbox").showModal();
}
function showLb() {
  const names = SAMPLE.pages[lb.fmt];
  lb.i = (lb.i + names.length) % names.length;
  $("#lb-img").src = `sample/${names[lb.i]}`;
}
$("#lightbox .prev").addEventListener("click", () => { lb.i--; showLb(); });
$("#lightbox .next").addEventListener("click", () => { lb.i++; showLb(); });
$("#lightbox").addEventListener("keydown", (e) => {
  if (e.key === "ArrowLeft") { lb.i--; showLb(); }
  if (e.key === "ArrowRight") { lb.i++; showLb(); }
});
$("#lightbox").addEventListener("click", (e) => { if (e.target.id === "lightbox") $("#lightbox").close(); });

/* ------------------------------------------------------------ form */
function fillCities() {
  const sel = $("#city");
  const regions = [...new Set(CITIES.map((c) => c.region))];
  for (const r of regions) {
    const g = h("optgroup", { label: r });
    for (const c of CITIES.filter((x) => x.region === r).sort((a, b) => a.label.localeCompare(b.label))) {
      g.append(h("option", { value: c.code }, c.label.includes(c.city) ? c.label : `${c.label} — ${c.city}`));
    }
    sel.append(g);
  }
}
function fillPreviewPages() {
  const sel = $("#pv-page");
  sel.append(h("option", { value: "cover" }, "Cover"));
  MONTHS.forEach((m, i) => sel.append(h("option", { value: `month:${i + 1}` }, m)));
  sel.append(h("option", { value: "legend" }, "How to read"), h("option", { value: "year" }, "Year at a glance"));
  sel.value = "month:1";
}
const effPaper = () => state.paper || cityOf(state.code).paper;
const effWeek = () => (state.week != null ? state.week : cityOf(state.code).week_start);
function syncForm() {
  const c = cityOf(state.code);
  $("#city").value = state.code;
  $("#city-hint").textContent = `Times in ${c.tzname}, daylight saving included. Eclipse visibility, occultations and when each target is highest are computed for ${c.city} (${Math.abs(c.lat).toFixed(1)}° ${c.lat >= 0 ? "N" : "S"}).`;
  $$('input[name="format"]').forEach((r) => (r.checked = r.value === state.format));
  $$('input[name="paper"]').forEach((r) => (r.checked = r.value === effPaper()));
  $$('input[name="week"]').forEach((r) => (r.checked = +r.value === effWeek()));
  $$('input[name="dpi"]').forEach((r) => (r.checked = +r.value === state.dpi));
  $("#wall-size").textContent = `${PAPER[effPaper()].wall}, 15 pages`;
  $("#desk-size").textContent = `${PAPER[effPaper()].desk}, 15 pages`;
  const big = state.dpi === 300 && state.format === "wall";
  $("#dpi-hint").textContent = big
    ? "300 dpi wall calendars are large (~40 MB) and need a desktop or laptop browser with plenty of memory."
    : state.dpi === 150 ? "Fastest; fine for an office or home printer." : "Sharp on home and most online print services.";
  $("#title").placeholder = "The Deep Space Explorer";
  $("#subtitle").placeholder = "An astronomer's Eye on the Cosmos";
  $("#title").value = state.title || "";
  fillHolidays();
  const hk = holKey();
  $("#holidays").value = hk;
  const c0 = cityOf(state.code);
  const fset = FESTS.find((f) => f.country === (c0 && c0.country));
  $("#fest-row").hidden = !fset;
  if (fset) {
    $("#fest-name").textContent = fset.name;
    $("#fest-list").textContent = fset.list;
    $("#festivals").checked = festKey() === fset.key;
    $("#festivals").dataset.key = fset.key;
  }
  $("#hol-hint").textContent = hk
    ? "Shown in red on their dates. Holidays set by moon sighting are marked as estimates."
    : "A pure sky calendar: no public holidays.";
  $("#subtitle").value = state.subtitle || "";
}
function bindForm() {
  $("#city").addEventListener("change", (e) => { state.code = e.target.value; state.paper = null; state.week = null; if (state.hol) state.hol = "auto"; state.fest = "auto"; changed(); hero(); });
  $("#festivals").addEventListener("change", (e) => {
    const c = cityOf(state.code);
    const want = e.target.checked ? e.target.dataset.key : "";
    state.fest = want === ((c && c.festivals) || "") ? "auto" : want;
    changed();
  });
  $("#holidays").addEventListener("change", (e) => {
    const c = cityOf(state.code);
    state.hol = e.target.value === (c && c.holiday_key) ? "auto" : e.target.value;
    changed();
  });
  $$('input[name="format"]').forEach((r) => r.addEventListener("change", () => { state.format = r.value; changed(); }));
  $$('input[name="paper"]').forEach((r) => r.addEventListener("change", () => { state.paper = r.value; changed(); }));
  $$('input[name="week"]').forEach((r) => r.addEventListener("change", () => { state.week = +r.value; changed(); }));
  $$('input[name="dpi"]').forEach((r) => r.addEventListener("change", () => { state.dpi = +r.value; changed(false); }));
  $$('input[name="sfmt"]').forEach((r) => r.addEventListener("change", () => renderSample(r.value)));
  let t;
  for (const id of ["title", "subtitle"]) {
    $("#" + id).addEventListener("input", (e) => {
      state[id] = e.target.value.trim();
      clearTimeout(t);
      t = setTimeout(() => changed(false, $("#pv-page").value === "cover"), 600);
    });
  }
  $("#reset-images").addEventListener("click", () => { state.images = defaults(); renderTiles(); changed(); });
  $("#pv-go").addEventListener("click", () => preview());
  $("#pv-page").addEventListener("change", () => { if (engineUsed) preview(); });
  $("#build").addEventListener("click", buildAll);
  $("#share").addEventListener("click", async () => {
    const url = shareURL();
    try { await navigator.clipboard.writeText(url); $("#share").textContent = "Link copied"; }
    catch (e) { prompt("Copy this link", url); }
    setTimeout(() => ($("#share").textContent = "Copy a link to these settings"), 2500);
  });
}
function changed(redraw = true, force = false) {
  syncForm();
  save();
  $("#result").hidden = true;
  if (engineUsed && (redraw || force)) schedulePreview();
}

/* ------------------------------------------------------------ tiles */
const IC = window.ImgCheck;
function thumbURL(img, big = false) {
  if (!img) return "";
  if (img.source === "own") return uploads.get(img.id)?.url || "";
  if (img.thumb) return img.thumb;
  if (img.source === "commons") return img.thumb_url || "";
  if (img.source === "licensed") return img.file || "";
  return `api/img?src=${img.source}&id=${img.id}&r=${img.source === "noirlab" ? "screen" : big ? "thumb700x" : "thumb300y"}`;
}
/** <img> that never disappears: on error it tries the observatory's other size, then
    becomes a drawn placeholder with the object's name. */
function photo(img, { big = false, cls = "" } = {}) {
  const wrap = h("span", { class: "ph " + cls });
  if (!img) return wrap;
  const el = h("img", { src: thumbURL(img, big), alt: "", loading: "lazy", decoding: "async" });
  el.addEventListener("load", () => wrap.classList.add("loaded"));
  el.addEventListener("error", () => {
    const official = !["own", "licensed", "commons"].includes(img.source);
    if (official && !el.dataset.fb) { el.dataset.fb = "1"; el.src = `api/img?src=${img.source}&id=${img.id}&r=screen`; return; }
    el.remove();
    wrap.classList.add("none");
    wrap.append(h("span", { class: "ph-fallback" }, h("b", {}, img.object || img.title || "Picture"),
      h("small", {}, "Preview unavailable · prints at full size")));
  });
  wrap.append(el);
  return wrap;
}
/** How sharply a picture prints on the current page and paper. */
function printFit(img, slot) {
  if (!IC || !img || !img.pixels || !img.pixels[0]) return null;
  const ppi = IC.quickPpi(img.pixels[0], img.pixels[1], img.fit, state.format, effPaper(), slot);
  return { ppi, level: ppi >= 180 ? "pass" : ppi >= 120 ? "warn" : "fail",
    label: ppi >= 240 ? "Print sharp" : ppi >= 180 ? "Sharp" : ppi >= 120 ? "Soft up close" : "Too small" };
}
/** Re-run the full checks on an uploaded photo for the current format and paper. */
function ownVerdict(img, slot) {
  const u = img && uploads.get(img.id);
  if (!IC || !u || !u.info) return null;
  return IC.evaluate(Object.assign({}, u.info, ownCtx(slot, img.fit), { tones: u.tones[slotKind(slot)] || u.info.tones }));
}
const slotKind = (slot) => `${state.format}-${effPaper()}-${slot === "cover" ? "cover" : "month"}`;
function ownCtx(slot, fit) {
  return { fit: fit || "cover", format: state.format, paper: effPaper(), slot, dpi: state.dpi,
    paperName: (effPaper() === "ISO" ? { wall: "A3", desk: "A5" } : { wall: "Tabloid", desk: "half-letter" })[state.format] };
}
function renderTiles() {
  const ol = $("#tiles");
  ol.innerHTML = "";
  const d = defaults();
  for (const s of SLOTS) {
    const img = imgInfo(state.images[s]);
    const v = img && img.source === "own" ? ownVerdict(img, s) : null;
    const bad = v && v.some((x) => x.level === "fail");
    const fit = img && img.source !== "own" ? printFit(img, s) : null;
    const flag = bad ? "fail" : fit && fit.level !== "pass" ? fit.level : "";
    ol.append(h("li", { class: [state.images[s] !== d[s] ? "changed" : "", flag ? "flag-" + flag : ""].join(" ").trim() || null },
      h("button", { class: "tile-btn", type: "button", onclick: () => openPicker(s),
        "aria-label": `${slotName(s)}: ${img?.object || "no picture"}${bad ? " (doesn't fit this page)" : ""}. Change picture` },
        photo(img),
        h("span", { class: "cap" }, h("span", { class: "m" }, slotName(s)), h("span", { class: "o" }, img?.object || "—")),
        flag ? h("span", { class: "flag", title: bad ? "This photo doesn't fit the current page" : fit.label }, "!") : null)));
  }
}

/* ------------------------------------------------------------ picker */
const pk = { slot: "01", view: "lib", filter: "suggested", src: "", q: "", focus: null };
const SRC_FILTERS = [["", "Every source"], ["eso", "ESO"], ["esahubble", "Hubble"], ["esawebb", "Webb"], ["noirlab", "NOIRLab"], ["commons", "Commons"]];
function openPicker(slot) {
  pk.slot = slot; pk.view = "lib"; pk.filter = "suggested"; pk.q = ""; pk.src = "";
  pk.focus = state.images[slot];
  renderPicker();
  const d = $("#picker");
  if (!d.open) d.showModal();
  requestAnimationFrame(() => $("#pk-rail .on")?.scrollIntoView({ block: "nearest", inline: "center" }));
}
$("#picker").addEventListener("click", (e) => { if (e.target.id === "picker") $("#picker").close(); });
$("#picker").addEventListener("close", () => { renderTiles(); });
function choose(id, { close = false } = {}) {
  state.images[pk.slot] = id;
  pk.focus = id;
  renderTiles();
  $("#pv-page").value = pk.slot === "cover" ? "cover" : `month:${+pk.slot}`;
  changed();
  if (close) { $("#picker").close(); return; }
  renderPicker({ keepScroll: true });
}
function renderPicker({ keepScroll = false } = {}) {
  const grid = $("#pk-body .pk-grid");
  const top = keepScroll && grid ? grid.scrollTop : 0;
  $("#pk-title").textContent = pk.slot === "cover" ? "Cover picture" : `${slotName(pk.slot)} picture`;
  $("#pk-sub").textContent = pk.slot === "cover"
    ? "Fills the whole front page."
    : `Fills the ${state.format === "wall" ? "top half of the page" : "left panel"}; it is also the month's target object.`;
  // month rail
  const rail = $("#pk-rail");
  rail.innerHTML = "";
  for (const s of SLOTS) {
    const img = imgInfo(state.images[s]);
    rail.append(h("button", { type: "button", class: s === pk.slot ? "on" : null, "aria-current": s === pk.slot ? "true" : null,
      onclick: () => { pk.slot = s; pk.focus = state.images[s]; pk.filter = "suggested"; renderPicker(); } },
      photo(img), h("span", {}, s === "cover" ? "Cover" : MONTHS[+s - 1].slice(0, 3))));
  }
  $$("#pk-views button").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.view === pk.view)));
  const body = $("#pk-body");
  body.innerHTML = "";
  body.dataset.view = pk.view;
  if (pk.view === "lib") libView(body, top);
  else if (pk.view === "id") idTab(body);
  else ownTab(body);
}
$$("#pk-views button").forEach((b) => b.addEventListener("click", () => { pk.view = b.dataset.view; renderPicker(); }));
$("#pk-done").addEventListener("click", () => $("#picker").close());

function libList() {
  const all = [...Object.values(LIB.images), ...Object.values(state.extra).filter((m) => !LIB.images[m.id])];
  let list;
  if (pk.filter === "suggested" && !pk.q) {
    const s = LIB.slots.find((x) => x.slot === pk.slot);
    list = (s ? s.options : []).map((id) => LIB.images[id]).filter(Boolean);
    const cur = imgInfo(state.images[pk.slot]);
    if (cur && !list.includes(cur)) list.unshift(cur);
  } else {
    const q = pk.q.toLowerCase();
    list = all.filter((m) => (!pk.src || m.source === pk.src)
      && (!q || [m.object, m.title, m.catalog, m.constellation, m.kind, m.id, m.credit].join(" ").toLowerCase().includes(q)));
  }
  return list;
}
function libView(body, top) {
  const count = Object.keys(LIB.images).length + Object.values(state.extra).filter((m) => !LIB.images[m.id]).length;
  const search = h("input", { type: "search", placeholder: "Search: Orion, M31, nebula, Webb…", value: pk.q, autocomplete: "off", spellcheck: "false", "aria-label": "Search pictures" });
  let t;
  search.addEventListener("input", () => { clearTimeout(t); t = setTimeout(() => { pk.q = search.value.trim(); if (pk.q) pk.filter = "all"; drawGrid(); syncChips(); }, 120); });
  const chip = (key, label) => h("button", { type: "button", class: "chip", "data-k": key, onclick: () => { pk.filter = key; if (key === "suggested") { pk.q = ""; search.value = ""; pk.src = ""; } drawGrid(); syncChips(); } }, label);
  const srcSel = h("select", { "aria-label": "Source", onchange: (e) => { pk.src = e.target.value; pk.filter = "all"; drawGrid(); syncChips(); } },
    SRC_FILTERS.map(([v, l]) => h("option", { value: v, selected: v === pk.src ? true : null }, l)));
  const chips = h("div", { class: "chips" }, chip("suggested", pk.slot === "cover" ? "Suggested for the cover" : `Suggested for ${slotName(pk.slot)}`), chip("all", `All pictures · ${count}`));
  const syncChips = () => $$(".chip", chips).forEach((c) => c.setAttribute("aria-pressed", String(c.dataset.k === pk.filter)));
  const grid = h("div", { class: "pk-grid", role: "listbox", "aria-label": "Pictures" });
  const aside = h("aside", { class: "pk-detail", "aria-live": "polite" });
  const drawGrid = () => {
    const list = libList();
    grid.innerHTML = "";
    if (!list.length) grid.append(h("p", { class: "pk-empty" }, "Nothing matches. Try another word, or look it up by ID."));
    list.forEach((m, i) => grid.append(card(m, i)));
    drawDetail(aside, imgInfo(pk.focus) || list[0]);
  };
  syncChips();
  body.append(h("div", { class: "pk-tools" }, chips, h("div", { class: "pk-find" }, search, srcSel)),
    h("div", { class: "pk-main" }, grid, aside));
  drawGrid();
  grid.scrollTop = top || 0;
  grid.addEventListener("mouseleave", () => drawDetail(aside, imgInfo(pk.focus) || imgInfo(state.images[pk.slot])));
  grid.addEventListener("keydown", (e) => {
    const cards = $$(".card", grid), i = cards.indexOf(document.activeElement);
    if (i < 0) return;
    const cols = Math.max(1, Math.round(grid.clientWidth / cards[0].offsetWidth));
    const to = { ArrowRight: i + 1, ArrowLeft: i - 1, ArrowDown: i + cols, ArrowUp: i - cols }[e.key];
    if (to != null && cards[to]) { e.preventDefault(); cards[to].focus(); }
  });
}
function card(img, i) {
  const on = state.images[pk.slot] === img.id;
  const fit = img.source === "own" ? null : printFit(img, pk.slot);
  const own = img.source === "own" ? ownVerdict(img, pk.slot) : null;
  const ownBad = own && own.some((x) => x.level === "fail");
  const b = h("button", { class: "card" + (on ? " on" : ""), type: "button", role: "option", "aria-selected": String(on), style: `--i:${Math.min(i, 14)}`,
    onclick: () => { if (ownBad) { pk.focus = img.id; drawDetail($(".pk-detail"), img); return; } choose(img.id); },
    onmouseenter: () => drawDetail($(".pk-detail"), img), onfocus: () => drawDetail($(".pk-detail"), img) },
    photo(img),
    h("span", { class: "badges" },
      h("span", { class: "src" }, SRC_NAME[img.source] || img.source),
      img.fit === "band" ? h("span", { class: "src" }, "Panorama") : null),
    h("span", { class: "cap" }, h("span", { class: "t" }, img.object || img.title),
      h("span", { class: "s" }, [img.kind, img.constellation].filter(Boolean).join(" · ") || img.title || ""),
      fit ? h("span", { class: `q q-${fit.level}`, title: `${Math.round(fit.ppi)} ppi on this page` }, fit.label) : null,
      ownBad ? h("span", { class: "q q-fail" }, "Doesn't fit this page") : null),
    h("span", { class: "tick", "aria-hidden": "true", html: '<svg viewBox="0 0 16 16"><path d="M3.5 8.5l3 3 6-7" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>' }));
  return b;
}
function drawDetail(aside, img) {
  if (!aside) return;
  aside.innerHTML = "";
  if (!img) return;
  const on = state.images[pk.slot] === img.id;
  const fit = img.source === "own" ? null : printFit(img, pk.slot);
  const px = img.pixels && img.pixels[0] ? `${img.pixels[0].toLocaleString()} × ${img.pixels[1].toLocaleString()} px` : "";
  const facts = [["Type", img.kind], ["Catalogue", img.catalog], ["Constellation", img.constellation], ["Distance", img.distance],
    ["Size", px], ["Licence", img.license || (img.source === "own" ? "" : "CC BY 4.0")]].filter(([, v]) => v);
  const v = img.source === "own" ? ownVerdict(img, pk.slot) : null;
  const bad = v && v.some((x) => x.level === "fail");
  aside.append(
    photo(img, { big: true, cls: "pk-hero" }),
    h("div", { class: "pk-info" },
      h("p", { class: "eyebrow" }, SRC_NAME[img.source] || img.source, img.source === "own" ? "" : ` · ${img.id}`),
      h("h4", {}, img.object || img.title),
      img.title && img.title !== img.object ? h("p", { class: "dim" }, img.title) : null,
      fit ? h("p", { class: `fitline q-${fit.level}` }, h("i"), `${fit.label}: ${Math.round(fit.ppi)} ppi on ${paperLabel()}`) : null,
      v ? checklist(v, true) : null,
      h("dl", {}, facts.flatMap(([k, val]) => [h("dt", {}, k), h("dd", {}, val)])),
      h("p", { class: "credit" }, h("span", {}, "Credit "), img.credit || "—"),
      img.note ? h("p", { class: "note" }, img.note) : null,
      img.page ? h("a", { class: "src-link", href: img.page, target: "_blank", rel: "noopener" }, "Open the original page") : null),
    h("div", { class: "pk-act" },
      bad ? h("p", { class: "warn" }, "This photo can't be used on this page as it is.")
        : on ? h("button", { class: "btn ghost wide", type: "button", onclick: () => $("#picker").close() }, "Selected · Done")
          : h("button", { class: "btn primary wide", type: "button", onclick: () => choose(img.id, { close: true }) }, `Use for ${pk.slot === "cover" ? "the cover" : slotName(pk.slot)}`)));
}
const paperLabel = () => `${(effPaper() === "ISO" ? { wall: "A3", desk: "A5" } : { wall: "Tabloid", desk: "half-letter" })[state.format]} ${state.format === "wall" ? "wall" : "desk"} ${pk.slot === "cover" ? "cover" : "pages"}`;
function checklist(items, compact = false) {
  const shown = compact ? items.filter((x) => x.level !== "pass" || ["ppi", "light", "crop"].includes(x.id)) : items;
  return h("ul", { class: "checks" + (compact ? " compact" : "") }, shown.map((x) => h("li", { class: x.level },
    h("i", { "aria-hidden": "true" }), h("div", {}, h("b", {}, x.title), x.detail && !compact ? h("span", {}, x.detail) : null,
      h("span", { class: "sr" }, ` (${x.level === "pass" ? "OK" : x.level === "warn" ? "warning" : "problem"})`)))));
}

/* ------------------------------------------------------------ look up by ID */
async function lookup(text, src) {
  const q = new URLSearchParams({ id: text.trim() });
  if (src) q.set("src", src);
  const r = await fetch(`api/meta?${q}`);
  let j = {};
  try { j = await r.json(); } catch (e) { /* not JSON */ }
  if (!r.ok) throw new Error(j.error || `Lookup failed (HTTP ${r.status}).`);
  return j;
}
const FIELDS = [["object", "Object", true], ["catalog", "Catalogue number"], ["kind", "Type of object"],
  ["constellation", "Constellation"], ["distance", "Distance"], ["ra", "RA (hh:mm:ss)"], ["dec", "Dec (±dd:mm:ss)"]];
function metaForm(m, { own = false, onBand = null } = {}) {
  const wrap = h("div", { class: "form2" });
  const credit = h("textarea", { rows: 2, required: true }, m.credit || "");
  wrap.append(h("label", { class: "field full" }, h("span", {}, own ? "Credit printed under the photo (required)" : "Credit, printed in full under the picture"), credit));
  const inputs = { credit };
  for (const [k, label, req] of FIELDS) {
    const i = h("input", { value: m[k] || "", required: req ? true : null, autocomplete: "off" });
    inputs[k] = i;
    wrap.append(h("label", { class: "field" }, h("span", {}, label + (req ? " (required)" : "")), i));
  }
  const band = h("input", { type: "checkbox" });
  band.checked = m.fit === "band";
  if (onBand) band.addEventListener("change", () => onBand(band.checked));
  wrap.append(h("label", { class: "check full" }, band, h("span", {}, "Panorama: show it whole as a full-width band instead of filling the photo area")));
  inputs.band = band;
  return { el: wrap, band, read: () => {
    const o = {};
    for (const [k] of FIELDS) o[k] = inputs[k].value.trim();
    o.credit = credit.value.trim();
    o.fit = band.checked ? "band" : "cover";
    return o;
  } };
}
function idTab(body) {
  const input = h("input", { placeholder: "eso1733a, weic2326a, heic0506a, or a Wikimedia Commons link", autocomplete: "off", spellcheck: "false" });
  const src = h("select", {}, h("option", { value: "" }, "Guess from the ID"), h("option", { value: "eso" }, "ESO"), h("option", { value: "esahubble" }, "ESA/Hubble"), h("option", { value: "esawebb" }, "ESA/Webb"));
  const go = h("button", { class: "btn primary", type: "submit" }, "Look up");
  const out = h("div");
  const form = h("form", { class: "lookup", onsubmit: async (e) => {
    e.preventDefault();
    out.innerHTML = "";
    if (!input.value.trim()) return;
    go.disabled = true;
    out.append(h("p", { class: "hint" }, "Reading the image's page…"));
    try {
      const m = await lookup(input.value, src.value);
      out.innerHTML = "";
      foundCard(out, m);
    } catch (err) {
      out.innerHTML = "";
      out.append(h("p", { class: "warn" }, err.message));
    } finally { go.disabled = false; }
  } }, h("label", { class: "field" }, h("span", {}, "Image ID or link"), input), h("label", { class: "field narrow" }, h("span", {}, "From"), src), go);
  body.append(h("div", { class: "pk-pane" }, h("p", { class: "lead" }, "Use any picture from ",
    h("a", { href: "https://www.eso.org/public/images/", target: "_blank", rel: "noopener" }, "ESO"), ", ",
    h("a", { href: "https://esahubble.org/images/", target: "_blank", rel: "noopener" }, "ESA/Hubble"), ", ",
    h("a", { href: "https://esawebb.org/images/", target: "_blank", rel: "noopener" }, "ESA/Webb"), " or ",
    h("a", { href: "https://commons.wikimedia.org/wiki/Category:Astronomical_images", target: "_blank", rel: "noopener" }, "Wikimedia Commons"),
    ". Paste its ID or link. The credit, size and licence are read from its page; Commons photos must allow reuse with credit and be at least 4000 px."), form, out));
  setTimeout(() => input.focus(), 30);
}
function foundCard(out, m) {
  const f = metaForm(m);
  const ok = h("input", { type: "checkbox" });
  const use = h("button", { class: "btn primary", type: "button", disabled: true }, `Use for ${slotName(pk.slot)}`);
  ok.addEventListener("change", () => (use.disabled = !ok.checked));
  use.addEventListener("click", () => {
    const v = f.read();
    if (!v.credit || !v.object) { alert("The credit and object name are needed."); return; }
    const meta = Object.assign({}, m, v, { license: m.license || "CC BY 4.0" });
    state.extra[meta.id] = meta;
    choose(meta.id, { close: true });
  });
  const fit = printFit(m, pk.slot);
  const px = m.pixels && m.pixels[0] ? `${m.pixels[0].toLocaleString()} × ${m.pixels[1].toLocaleString()} px` : "size unknown";
  out.append(h("div", { class: "found" },
    h("div", {}, photo(Object.assign({}, m, { thumb: m.source === "commons" ? m.thumb_url : null }), { big: true, cls: "pk-hero" }),
      h("p", { class: "fine" }, `${SRC_NAME[m.source]}${m.source === "commons" ? "" : " " + m.id} · ${px} · ${m.license || "CC BY 4.0"} · `, h("a", { href: m.page, target: "_blank", rel: "noopener" }, "page")),
      fit ? h("p", { class: `fitline q-${fit.level}` }, h("i"), `${fit.label}: ${Math.round(fit.ppi)} ppi on ${paperLabel()}`) : null,
      m.note ? h("p", { class: "fine" }, m.note) : null),
    h("div", {}, h("h4", { class: "found-t" }, m.title),
      m.warning ? h("p", { class: "warn" }, m.warning) : null,
      fit && fit.level === "fail" ? h("p", { class: "warn" }, "This picture is too small for this page; it would print blurry.") : null,
      f.el,
      h("label", { class: "check" }, ok, h("span", {}, "I've checked the credit against the image's page.")),
      use)));
}

/* ------------------------------------------------------------ your own photo */
async function analyse(file, slot, fit) {
  const head = new Uint8Array(await file.slice(0, 1 << 20).arrayBuffer());
  const type = IC.sniff(head);
  const info = Object.assign({ type, bytes: file.size }, IC.header(head, type));
  if (!["jpeg", "png", "webp"].includes(type)) return { info, tones: {} };
  // Decode through an <img> (the browser applies EXIF rotation), then work on a ~1600 px copy.
  const url = URL.createObjectURL(file);
  const el = new Image();
  el.src = url;
  try { await el.decode(); } catch (e) { URL.revokeObjectURL(url); info.w = 0; info.h = 0; return { info, tones: {} }; }
  info.w = el.naturalWidth; info.h = el.naturalHeight;
  const k = Math.min(1, 1600 / Math.max(info.w, info.h));
  const cv = document.createElement("canvas");
  cv.width = Math.max(1, Math.round(info.w * k)); cv.height = Math.max(1, Math.round(info.h * k));
  const cx = cv.getContext("2d", { willReadFrequently: true });
  cx.imageSmoothingQuality = "medium";
  cx.drawImage(el, 0, 0, cv.width, cv.height);
  const rgba = cx.getImageData(0, 0, cv.width, cv.height).data;
  // brightness under the text, for each page shape the photo may land on
  const tones = {};
  for (const format of ["wall", "desk"]) for (const paper of ["ISO", "US"]) for (const kind of ["cover", "month"]) {
    const z = IC.zone(format, paper, kind === "cover" ? "cover" : "01");
    const k2 = IC.keep(cv.width, cv.height, z), a = cv.width / cv.height, b = z.w / z.h;
    const crop = fit === "band" ? [1, 1] : a > b ? [k2, 1] : [1, k2];
    tones[`${format}-${paper}-${kind}`] = IC.tones(rgba, cv.width, cv.height, z.text, crop);
  }
  info.tones = tones[`${state.format}-${effPaper()}-${slot === "cover" ? "cover" : "month"}`];
  // fine detail from a full-resolution 512 px square at the centre
  try {
    const s = Math.min(512, info.w, info.h);
    const c2 = document.createElement("canvas");
    c2.width = c2.height = s;
    const x2 = c2.getContext("2d", { willReadFrequently: true });
    x2.drawImage(el, Math.floor((info.w - s) / 2), Math.floor((info.h - s) / 2), s, s, 0, 0, s, s);
    const d = x2.getImageData(0, 0, s, s).data, g = new Float32Array(s * s);
    for (let i = 0; i < s * s; i++) g[i] = 0.2126 * d[4 * i] + 0.7152 * d[4 * i + 1] + 0.0722 * d[4 * i + 2];
    info.detail = IC.detail(g, s);
  } catch (e) { info.detail = null; }
  URL.revokeObjectURL(url);
  return { info, tones };
}
function framePreview(url, slot, fit) {
  const z = IC.zone(state.format, effPaper(), slot);
  const [x0, y0, x1, y1] = z.text;
  return h("figure", { class: "frame" + (fit === "band" ? " band" : ""), style: `aspect-ratio:${z.w.toFixed(3)} / ${z.h.toFixed(3)}` },
    h("img", { src: url, alt: "How your photo fills the page" }),
    h("span", { class: "textzone", style: `left:${x0 * 100}%;top:${y0 * 100}%;width:${(x1 - x0) * 100}%;height:${(y1 - y0) * 100}%` }, h("span", {}, "Month name, dates and events print here")),
    h("figcaption", {}, `How it fills the ${z.label} (${paperLabel()})`));
}
function ownTab(body) {
  const file = h("input", { type: "file", accept: "image/jpeg,image/png,image/webp", class: "sr" });
  const drop = h("label", { class: "drop" }, file,
    h("span", { class: "drop-ico", "aria-hidden": "true", html: '<svg viewBox="0 0 24 24"><path d="M12 16V4m0 0-4.5 4.5M12 4l4.5 4.5M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>' }),
    h("b", {}, "Drop your astrophoto here, or choose a file"),
    h("span", {}, "JPEG, PNG or WebP. It's checked and read on this device, never uploaded."));
  const result = h("div", { class: "own-result" });
  const pane = h("div", { class: "pk-pane own" },
    h("p", { class: "lead" }, `Before it can go on ${pk.slot === "cover" ? "the cover" : `the ${slotName(pk.slot)} page`}, your photo is checked for print size, shape, brightness behind the text, sharpness, blown highlights and file format, for the ${paperLabel()} you've chosen.`),
    drop, result);
  body.append(pane);
  ["dragenter", "dragover"].forEach((t) => drop.addEventListener(t, (e) => { e.preventDefault(); drop.classList.add("over"); }));
  ["dragleave", "drop"].forEach((t) => drop.addEventListener(t, () => drop.classList.remove("over")));
  drop.addEventListener("drop", (e) => { e.preventDefault(); if (e.dataTransfer.files[0]) handle(e.dataTransfer.files[0]); });
  file.addEventListener("change", () => file.files[0] && handle(file.files[0]));

  let picked = null;
  async function handle(f) {
    drop.classList.add("compact");
    $("b", drop).textContent = "Drop another photo, or choose a file";
    result.innerHTML = "";
    result.append(h("div", { class: "checking" }, h("span", { class: "spin" }), "Checking your photo…"));
    if (picked && picked.url) URL.revokeObjectURL(picked.url);
    picked = { file: f, url: URL.createObjectURL(f), fit: "cover" };
    try {
      const a = await analyse(f, pk.slot, "cover");
      Object.assign(picked, a);
      if (a.info.w / a.info.h > 2.6) { picked.fit = "band"; picked = Object.assign(picked, await analyse(f, pk.slot, "band")); }
    } catch (e) {
      picked.info = { type: "unknown", bytes: f.size, w: 0, h: 0 };
      picked.tones = {};
    }
    draw();
  }
  function draw() {
    result.innerHTML = "";
    const items = IC.evaluate(Object.assign({}, picked.info, ownCtx(pk.slot, picked.fit)));
    const fails = items.filter((x) => x.level === "fail"), warns = items.filter((x) => x.level === "warn");
    const verdict = fails.length ? ["fail", "This photo can't be used here", `Fix ${fails.length === 1 ? "the problem" : "the problems"} below and try again, or choose another photo.`]
      : warns.length ? ["warn", "Usable, with a few cautions", "Read the notes below and check the preview before printing."]
        : ["pass", "Ready for print", "It meets every check for this page."];
    const f = metaForm({ fit: picked.fit }, { own: true, onBand: async (on) => { picked.fit = on ? "band" : "cover"; Object.assign(picked, await analyse(picked.file, pk.slot, picked.fit)); draw(); } });
    const ok = h("input", { type: "checkbox" });
    const lic = h("input", { placeholder: "e.g. © 2026 Your Name (optional)", autocomplete: "off" });
    const ack = warns.length && !fails.length ? h("input", { type: "checkbox" }) : null;
    const err = h("p", { class: "warn", hidden: true });
    const use = h("button", { class: "btn primary", type: "button", disabled: fails.length ? true : null }, `Use for ${pk.slot === "cover" ? "the cover" : slotName(pk.slot)}`);
    use.addEventListener("click", async () => {
      const v = f.read();
      const miss = !v.credit ? "Add the credit line." : !v.object ? "Name the object in the photo." : !ok.checked ? "Confirm you may print this photo."
        : ack && !ack.checked ? "Tick that you've read the cautions." : "";
      if (miss) { err.hidden = false; err.textContent = miss; return; }
      use.disabled = true;
      let bytes = await picked.file.arrayBuffer(), ext = picked.info.type === "png" ? "png" : "jpg";
      if (picked.info.type === "webp") {  // the print engine takes JPEG and PNG
        const el = new Image(); el.src = picked.url; await el.decode();
        const c = document.createElement("canvas"); c.width = el.naturalWidth; c.height = el.naturalHeight;
        c.getContext("2d").drawImage(el, 0, 0);
        bytes = await (await new Promise((r) => c.toBlob(r, "image/jpeg", 0.95))).arrayBuffer();
        ext = "jpg";
      }
      const id = `own-${Date.now().toString(36)}`;
      uploads.set(id, { bytes, ext, url: picked.url, info: picked.info, tones: picked.tones });
      picked = null; // keep the object URL alive for the tile
      state.extra[id] = Object.assign({ id, source: "own", title: v.object, license: lic.value.trim(), pixels: [0, 0],
        focus: null, zoom: 1, note: "", renditions: [] }, v);
      state.extra[id].pixels = [uploads.get(id).info.w, uploads.get(id).info.h];
      choose(id, { close: true });
    });
    result.append(h("div", { class: `verdict v-${verdict[0]}` }, h("i"), h("div", {}, h("b", {}, verdict[1]), h("span", {}, verdict[2]))),
      h("div", { class: "own-grid" },
        h("div", {}, picked.info.w ? framePreview(picked.url, pk.slot, picked.fit) : null),
        checklist(items)),
      fails.length ? null : h("div", { class: "own-form" }, f.el,
        h("label", { class: "field" }, h("span", {}, "Licence or copyright line (optional)"), lic),
        h("label", { class: "check" }, ok, h("span", {}, "I took this photo, or I have permission to print it.")),
        ack ? h("label", { class: "check" }, ack, h("span", {}, "I've read the cautions and checked how it looks.")) : null,
        err, use));
  }
}

/* ------------------------------------------------------------ worker */
let worker = null, engineUsed = false, jobN = 0;
const pending = new Map();
function getWorker() {
  if (worker) return worker;
  worker = new Worker("worker.js?v=" + encodeURIComponent(BUILD.kit || ""));
  worker.onmessage = (ev) => {
    const m = ev.data;
    const p = pending.get(m.job);
    if (!p) return;
    if (m.type === "progress") p.onProgress(m.text, m.frac);
    else if (m.type === "done") { pending.delete(m.job); p.resolve(m); }
    else if (m.type === "error") { pending.delete(m.job); p.reject(Object.assign(new Error(m.message), { detail: m.detail })); }
  };
  worker.onerror = (e) => {
    for (const [, p] of pending) p.reject(new Error(e.message || "The calendar engine stopped. Reload the page and try again."));
    pending.clear();
    sent.clear();
    worker = null;
  };
  return worker;
}
function rendition(img) {
  const r = img.renditions || [];
  if (r.includes("publicationjpg")) return "publicationjpg";
  if (r.includes("large")) return "large";
  return r[0] || "screen";
}
function makeSpec(pages, dpi) {
  const images = {}, fetches = [], ups = [];
  for (const s of SLOTS) {
    const i = Object.assign({}, imgInfo(state.images[s]));
    delete i.thumb;
    if (i.source === "own") {
      const u = uploads.get(i.id);
      i._key = i.id; i._ext = u.ext;
      if (!sent.has(i.id)) { ups.push({ key: i.id, ext: u.ext, bytes: u.bytes.slice(0) }); sent.add(i.id); }
    } else if (i.source === "commons") {  // Wikimedia Commons file, through our proxy
      i._key = i.id; i._ext = "jpg";
      if (!fetches.some((f) => f.key === i._key)) fetches.push({ key: i._key, id: i.id, url: `api/img?src=commons&u=${encodeURIComponent(i.file_url)}` });
    } else if (i.source === "licensed") {  // photographer image hosted with the site
      i._key = i.id; i._ext = "jpg";
      if (!fetches.some((f) => f.key === i._key)) fetches.push({ key: i._key, id: i.id, url: i.file });
    } else {
      const r = rendition(i);
      i._key = `${i.id}-${r}`; i._ext = "jpg";
      if (!fetches.some((f) => f.key === i._key)) {
        fetches.push({ key: i._key, id: i.id, url: `api/img?src=${i.source}&id=${i.id}&r=${r}` });
      }
    }
    images[s] = i;
  }
  const c = cityOf(state.code);
  return {
    spec: { code: c.code, format: state.format, paper: effPaper(), week_start: effWeek(), dpi, pages,
      title: state.title, subtitle: state.subtitle, images },
    fetches, uploads: ups, edition: `data/editions/${c.code}.json`,
  };
}
async function runJob(pages, dpi, onProgress) {
  const w = getWorker();
  engineUsed = true;
  const job = `j${++jobN}`;
  const m = makeSpec(pages, dpi);
  m.spec.holidays = await holidaySpec().catch(() => null);
  m.spec.festivals = await festivalSpec().catch(() => null);
  const cfg = { pyodide: CFG.pyodide || "https://cdn.jsdelivr.net/pyodide/v0.27.7/full/", reportlab: BUILD.reportlab,
    fonts: BUILD.fonts, version: BUILD.kit };
  return new Promise((resolve, reject) => {
    pending.set(job, { resolve, reject, onProgress });
    w.postMessage(Object.assign({ type: "run", job, cfg }, m), m.uploads.map((u) => u.bytes));
  });
}

/* ------------------------------------------------------------ preview */
let pdfjs = null, pvBusy = false, pvAgain = false, pvTimer = null;
function loadScript(src) {
  return new Promise((ok, bad) => document.head.append(h("script", { src, onload: ok, onerror: () => bad(new Error("Could not load " + src)) })));
}
async function getPdfjs() {
  if (pdfjs) return pdfjs;
  const base = (CFG.cdn && CFG.cdn.pdfjs) || "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/";
  await loadScript(base + "pdf.min.js");
  pdfjs = window.pdfjsLib;
  pdfjs.GlobalWorkerOptions.workerSrc = base + "pdf.worker.min.js";
  return pdfjs;
}
function schedulePreview() { clearTimeout(pvTimer); pvTimer = setTimeout(preview, 400); }
async function preview() {
  if (pvBusy) { pvAgain = true; return; }
  pvBusy = true;
  const box = $("#pv-box"), empty = $("#pv-empty"), go = $("#pv-go");
  box.classList.add("busy");
  go.disabled = true;
  const page = $("#pv-page").value;
  try {
    const dpi = state.format === "wall" ? 60 : 96;
    const [res, lib] = await Promise.all([runJob(page, dpi, (t) => { if (!$("#pv-canvas").classList.contains("on")) empty.textContent = t; go.textContent = "Drawing…"; }), getPdfjs()]);
    const doc = await lib.getDocument({ data: res.pdf }).promise;
    const pg = await doc.getPage(1);
    const vp1 = pg.getViewport({ scale: 1 });
    const maxW = Math.min(box.clientWidth - 32, 900), maxH = window.innerHeight * 0.7;
    const scale = Math.min(maxW / vp1.width, maxH / vp1.height);
    const ratio = window.devicePixelRatio || 1;
    const vp = pg.getViewport({ scale: scale * ratio });
    const cv = $("#pv-canvas");
    cv.width = vp.width; cv.height = vp.height;
    cv.style.width = `${vp.width / ratio}px`; cv.style.height = `${vp.height / ratio}px`;
    await pg.render({ canvasContext: cv.getContext("2d"), viewport: vp }).promise;
    cv.classList.add("on");
    empty.hidden = true;
    showWarnings(res.warnings);
  } catch (e) {
    empty.hidden = false;
    $("#pv-canvas").classList.remove("on");
    empty.textContent = "The preview failed: " + e.message;
    console.error(e.detail || e);
  } finally {
    pvBusy = false;
    box.classList.remove("busy");
    go.disabled = false;
    go.textContent = "Update preview";
    if (pvAgain) { pvAgain = false; preview(); }
  }
}
function showWarnings(list) {
  const w = $("#warn");
  if (!list || !list.length) { w.hidden = true; return; }
  w.hidden = false;
  w.textContent = `Some pictures couldn't be downloaded, so those pages use stand-in art marked PLACEHOLDER: ${list.join("; ")}. Try again, or pick another picture.`;
}

/* ------------------------------------------------------------ build */
let lastUrl = null;
async function buildAll() {
  const btn = $("#build");
  const bad = SLOTS.filter((s) => {
    const i = imgInfo(state.images[s]);
    const v = i && i.source === "own" ? ownVerdict(i, s) : null;
    return v && v.some((x) => x.level === "fail");
  });
  if (bad.length) {
    $("#warn").hidden = false;
    $("#warn").textContent = `Your photo for ${bad.map(slotName).join(", ")} doesn't fit the current format or paper. Open it to see why, or choose another picture.`;
    return;
  }
  btn.disabled = true;
  $("#result").hidden = true;
  $("#progress").hidden = false;
  $("#warn").hidden = true;
  const bar = $("#bar"), st = $("#status");
  const t0 = performance.now();
  try {
    const res = await runJob("all", state.dpi, (text, frac) => { st.textContent = text; bar.style.width = `${Math.round(frac * 100)}%`; });
    bar.style.width = "100%";
    const c = cityOf(state.code);
    const paperName = effPaper() === "ISO" ? (state.format === "wall" ? "A3" : "A5") : (state.format === "wall" ? "Tabloid" : "HalfLetter");
    const name = `DeepSpaceExplorer2027_${c.code}_${state.format === "wall" ? "Wall" : "Desk"}_${paperName}.pdf`;
    if (lastUrl) URL.revokeObjectURL(lastUrl);
    lastUrl = URL.createObjectURL(new Blob([res.pdf], { type: "application/pdf" }));
    const a = $("#download");
    a.href = lastUrl;
    a.download = name;
    a.textContent = `Download your calendar (${(res.pdf.byteLength / 1e6).toFixed(1)} MB PDF)`;
    $("#result-note").textContent = `Built in ${Math.round((performance.now() - t0) / 1000)} s. Print at 100% ("actual size") on ${PAPER[effPaper()][state.format]} paper; the PDF includes bleed for print shops.`;
    $("#result").hidden = false;
    st.textContent = "Done.";
    showWarnings(res.warnings);
  } catch (e) {
    st.textContent = "";
    $("#warn").hidden = false;
    const mem = /memory|allocation|RangeError/i.test(e.message);
    $("#warn").textContent = mem
      ? "Your browser ran out of memory. Choose Good or Home printer quality, or use a desktop browser."
      : `The build stopped: ${e.message}`;
    console.error(e.detail || e);
  } finally {
    btn.disabled = false;
  }
}

/* ------------------------------------------------------------ donate */
function renderDonate() {
  const d = CFG.donate || {};
  const box = $("#donate");
  const cards = [];
  if (d.upi && d.upi.id) {
    const link = (amt) => `upi://pay?${new URLSearchParams(Object.assign({ pa: d.upi.id, pn: d.upi.name || "", tn: d.upi.note || "", cu: "INR" }, amt ? { am: String(amt) } : {}))}`;
    const qr = h("div", { class: "qr", role: "img", "aria-label": "UPI QR code" });
    const amounts = h("div", { class: "amounts" }, (d.upi.amounts || []).map((a) => h("a", { class: "btn ghost", href: link(a) }, `₹${a}`)),
      h("a", { class: "btn ghost", href: link() }, "Any amount"));
    cards.push(h("div", { class: "give" }, h("h3", {}, "UPI (India)"),
      h("p", {}, "Scan with any UPI app, or tap an amount on your phone."), qr, amounts,
      h("p", { class: "upi-id" }, d.upi.id)));
    loadScript((CFG.cdn && CFG.cdn.qrcode) || "https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js")
      .then(() => new window.QRCode(qr, { text: link(), width: 360, height: 360, correctLevel: window.QRCode.CorrectLevel.M }))
      .catch(() => qr.replaceWith(h("p", { class: "hint" }, "Open this page on your phone to pay by UPI.")));
  }
  const intl = [["kofi", "Ko-fi"], ["buymeacoffee", "Buy Me a Coffee"], ["paypal", "PayPal"], ["github_sponsors", "GitHub Sponsors"]]
    .filter(([k]) => d[k]).map(([k, label]) => h("a", { class: "btn ghost", href: d[k], target: "_blank", rel: "noopener" }, label));
  for (const o of d.other || []) if (o.url) intl.push(h("a", { class: "btn ghost", href: o.url, target: "_blank", rel: "noopener" }, o.label || "Donate"));
  if (intl.length) {
    cards.push(h("div", { class: "give" }, h("h3", {}, "Cards and PayPal"),
      h("p", {}, "From anywhere in the world, one-off or monthly."), h("div", { class: "links" }, intl)));
  }
  cards.push(h("div", { class: "give" }, h("h3", {}, "Other ways to help"),
    h("p", {}, "Share the calendar with your astronomy club or class, print one for a friend, or tell us about a wrong date."),
    h("div", { class: "links" }, h("button", { class: "btn ghost sm", type: "button", onclick: async (e) => {
      const url = location.origin + location.pathname;
      try { if (navigator.share) await navigator.share({ title: "Deep Space Explorer 2027", url }); else { await navigator.clipboard.writeText(url); e.target.textContent = "Link copied"; } }
      catch (err) { /* cancelled */ }
    } }, "Share the site"))));
  if (!(d.upi && d.upi.id) && !intl.length) {
    cards.unshift(h("div", { class: "give" }, h("h3", {}, "Donations open soon"),
      h("p", {}, "Payment links haven't been added yet.")));
  }
  box.append(...cards);
}

boot();
})();
