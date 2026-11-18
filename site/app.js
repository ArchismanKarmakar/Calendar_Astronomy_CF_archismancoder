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
  } catch (e) { console.warn(e); }
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
function thumbURL(img) {
  if (!img) return "";
  if (img.source === "own") return uploads.get(img.id)?.url || "";
  if (img.thumb) return img.thumb;
  if (img.source === "commons") return img.thumb_url || "";
  return `api/img?src=${img.source}&id=${img.id}&r=${img.source === "noirlab" ? "screen" : "thumb300y"}`;
}
function renderTiles() {
  const ol = $("#tiles");
  ol.innerHTML = "";
  const d = defaults();
  for (const s of SLOTS) {
    const img = imgInfo(state.images[s]);
    ol.append(h("li", { class: state.images[s] !== d[s] ? "changed" : null },
      h("button", { class: "tile-btn", type: "button", onclick: () => openPicker(s), "aria-label": `${slotName(s)}: ${img?.object || "no picture"}. Change picture` },
        h("span", { class: "ph" }, h("img", { src: thumbURL(img), alt: "", loading: "lazy", onerror: thumbFallback(img) }),
          img?.fit === "band" ? h("span", { class: "tag" }, "panorama") : null),
        h("span", { class: "cap" }, h("span", { class: "m" }, slotName(s)), h("span", { class: "o" }, img?.object || "—")))));
  }
}
function thumbFallback(img) {
  return (e) => {
    const el = e.target;
    if (!img || ["own", "licensed", "commons"].includes(img.source) || el.dataset.fb) { el.style.visibility = "hidden"; return; }
    el.dataset.fb = "1";
    el.src = `api/img?src=${img.source}&id=${img.id}&r=screen`;
  };
}

/* ------------------------------------------------------------ picker */
let pickSlot = "01";
function openPicker(slot) {
  pickSlot = slot;
  $("#pk-title").textContent = `Choose the ${slot === "cover" ? "cover" : slotName(slot)} picture`;
  showTab("suggested");
  $("#picker").showModal();
}
$$("#picker .tabs button").forEach((b) => b.addEventListener("click", () => showTab(b.dataset.tab)));
$("#picker").addEventListener("click", (e) => { if (e.target.id === "picker") $("#picker").close(); });
function choose(id) {
  state.images[pickSlot] = id;
  $("#picker").close();
  renderTiles();
  if (pickSlot !== "cover") $("#pv-page").value = `month:${+pickSlot}`; else $("#pv-page").value = "cover";
  changed();
}
function card(img) {
  const on = state.images[pickSlot] === img.id;
  const px = img.pixels && img.pixels[0] ? `${img.pixels[0].toLocaleString()} × ${img.pixels[1].toLocaleString()} px` : "";
  return h("button", { class: "card" + (on ? " on" : ""), type: "button", onclick: () => choose(img.id), "aria-pressed": on },
    h("span", { class: "ph" }, h("img", { src: thumbURL(img), alt: "", loading: "lazy", onerror: thumbFallback(img) })),
    h("span", { class: "cap" },
      h("span", { class: "t" }, img.object || img.title),
      h("span", { class: "s" }, [SRC_NAME[img.source] || img.source, img.source === "own" ? "" : img.id, img.fit === "band" ? "panorama" : ""].filter(Boolean).join(", ")),
      px ? h("span", { class: "c" }, px) : null,
      img.note ? h("span", { class: "c" }, img.note) : null,
      h("span", { class: "c" }, img.credit)));
}
function showTab(tab) {
  $$("#picker .tabs button").forEach((b) => b.setAttribute("aria-selected", b.dataset.tab === tab));
  const body = $("#pk-body");
  body.innerHTML = "";
  if (tab === "suggested") {
    const s = LIB.slots.find((x) => x.slot === pickSlot);
    body.append(h("p", { class: "hint", style: "margin:0 0 14px" }, pickSlot === "cover"
      ? "Pictures that work as a full-page cover."
      : `Objects well placed in ${slotName(pickSlot)} evenings. Any picture can go on any page — see All pictures.`));
    body.append(h("div", { class: "grid" }, s.options.map((id) => card(LIB.images[id]))));
  } else if (tab === "all") {
    const all = [...Object.values(LIB.images), ...Object.values(state.extra)];
    body.append(h("div", { class: "grid" }, all.map(card)));
  } else if (tab === "id") {
    idTab(body);
  } else {
    ownTab(body);
  }
}
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
function metaForm(m, { own = false } = {}) {
  const wrap = h("div", { class: "form2" });
  const credit = h("textarea", { rows: 2, required: true }, m.credit || "");
  wrap.append(h("label", { class: "field full" }, h("span", {}, own ? "Credit — printed under the photo (required)" : "Credit — printed in full under the picture"), credit));
  const inputs = { credit };
  for (const [k, label, req] of FIELDS) {
    const i = h("input", { value: m[k] || "", required: req ? true : null, autocomplete: "off" });
    inputs[k] = i;
    wrap.append(h("label", { class: "field" }, h("span", {}, label + (req ? " (required)" : "")), i));
  }
  const band = h("input", { type: "checkbox" });
  band.checked = m.fit === "band";
  wrap.append(h("label", { class: "check full" }, band, h("span", {}, "Panorama: show it as a full-width band instead of filling the photo area")));
  inputs.band = band;
  return { el: wrap, read: () => {
    const o = {};
    for (const [k] of FIELDS) o[k] = inputs[k].value.trim();
    o.credit = credit.value.trim();
    o.fit = band.checked ? "band" : "cover";
    return o;
  } };
}
function idTab(body) {
  const input = h("input", { placeholder: "eso1733a, weic2326a, or a Wikimedia Commons / Wikipedia image link", autocomplete: "off", spellcheck: "false" });
  const src = h("select", {}, h("option", { value: "" }, "Site: guess"), h("option", { value: "eso" }, "ESO"), h("option", { value: "esahubble" }, "ESA/Hubble"), h("option", { value: "esawebb" }, "ESA/Webb"));
  const go = h("button", { class: "btn small", type: "submit" }, "Look up");
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
  } }, h("label", { class: "field" }, h("span", {}, "Image ID or link"), input), h("label", { class: "field", style: "flex:0 0 auto" }, h("span", {}, "From"), src), go);
  body.append(h("p", { class: "hint", style: "margin:0 0 14px" }, "Find a picture on ",
    h("a", { href: "https://www.eso.org/public/images/", target: "_blank", rel: "noopener" }, "eso.org/public/images"), " or ",
    h("a", { href: "https://esahubble.org/images/", target: "_blank", rel: "noopener" }, "esahubble.org/images"), " or ",
    h("a", { href: "https://esawebb.org/images/", target: "_blank", rel: "noopener" }, "esawebb.org/images"),
    ", or a photo on ", h("a", { href: "https://commons.wikimedia.org/wiki/Category:Astronomical_images", target: "_blank", rel: "noopener" }, "Wikimedia Commons"),
    ", and paste its ID or link. Commons photos are checked for a licence that allows reuse with credit, and for print resolution."), form, out);
  setTimeout(() => input.focus(), 30);
}
function foundCard(out, m) {
  const f = metaForm(m);
  const ok = h("input", { type: "checkbox" });
  const use = h("button", { class: "btn primary", type: "button", disabled: true }, `Use for ${slotName(pickSlot)}`);
  ok.addEventListener("change", () => (use.disabled = !ok.checked));
  use.addEventListener("click", () => {
    const v = f.read();
    if (!v.credit || !v.object) { alert("The credit and object name are needed."); return; }
    const meta = Object.assign({}, m, v, { license: m.license || "CC BY 4.0" });
    state.extra[meta.id] = meta;
    choose(meta.id);
  });
  const px = m.pixels && m.pixels[0] ? `${m.pixels[0].toLocaleString()} × ${m.pixels[1].toLocaleString()} px` : "size unknown";
  const small = m.pixels && m.pixels[0] && Math.max(...m.pixels) < 2500;
  out.append(h("div", { class: "found" },
    h("div", {}, h("img", { src: m.source === "commons" ? m.thumb_url : `api/img?src=${m.source}&id=${m.id}&r=thumb700x`, alt: m.title, onerror: thumbFallback(m) }),
      h("p", { class: "fine", style: "margin-top:8px" }, `${SRC_NAME[m.source]}${m.source === "commons" ? "" : " " + m.id}, ${px}, ${m.license || "CC BY 4.0"}. `, h("a", { href: m.page, target: "_blank", rel: "noopener" }, "Open its page")),
      m.note ? h("p", { class: "fine" }, m.note) : null),
    h("div", {}, h("h3", { style: "font-size:24px;margin-bottom:10px" }, m.title),
      m.warning ? h("p", { class: "warn" }, m.warning) : null,
      small ? h("p", { class: "warn" }, "This picture is small; it will look soft when printed large.") : null,
      f.el,
      h("label", { class: "check" }, ok, h("span", {}, "I've checked the credit against the image's page.")),
      use)));
}
function ownTab(body) {
  const file = h("input", { type: "file", accept: "image/jpeg,image/png,image/tiff,image/webp" });
  const pv = h("div");
  let picked = null;
  const f = metaForm({});
  const ok = h("input", { type: "checkbox" });
  const lic = h("input", { placeholder: "e.g. © 2026 Your Name — leave empty if not needed", autocomplete: "off" });
  const use = h("button", { class: "btn primary", type: "button" }, `Use for ${slotName(pickSlot)}`);
  const err = h("p", { class: "warn", hidden: true });
  file.addEventListener("change", async () => {
    pv.innerHTML = "";
    picked = file.files[0] || null;
    if (!picked) return;
    if (picked.size > 120e6) { err.hidden = false; err.textContent = "That file is over 120 MB; save a smaller JPEG first."; picked = null; return; }
    const url = URL.createObjectURL(picked);
    const img = h("img", { src: url, alt: "Your photo", style: "border-radius:10px;max-height:220px;width:auto" });
    pv.append(img);
    img.onload = () => {
      picked.w = img.naturalWidth; picked.h = img.naturalHeight;
      if (picked.w / picked.h > 2.6) f.el.querySelector('input[type="checkbox"]').checked = true;
      pv.append(h("p", { class: "fine" }, `${picked.w.toLocaleString()} × ${picked.h.toLocaleString()} px`
        + (Math.max(picked.w, picked.h) < 2500 ? " — small for print; it may look soft." : "")));
    };
    picked.url = url;
  });
  use.addEventListener("click", async () => {
    const v = f.read();
    err.hidden = true;
    const miss = !picked ? "Choose a photo first." : !v.credit ? "Add the credit line." : !v.object ? "Name the object." : !ok.checked ? "Confirm you may use the photo." : "";
    if (miss) { err.hidden = false; err.textContent = miss; return; }
    const ext = (picked.name.split(".").pop() || "jpg").toLowerCase().replace("jpeg", "jpg");
    const id = `own-${Date.now().toString(36)}`;
    uploads.set(id, { bytes: await picked.arrayBuffer(), ext, url: picked.url });
    state.extra[id] = Object.assign({ id, source: "own", title: v.object, license: lic.value.trim(), pixels: [picked.w || 0, picked.h || 0],
      focus: null, zoom: 1, note: "", renditions: [] }, v);
    choose(id);
  });
  body.append(h("p", { class: "hint", style: "margin:0 0 14px" }, "Your photo is read on this device and never uploaded. It's kept until you close this tab."),
    h("label", { class: "field" }, h("span", {}, "Photo (JPEG, PNG, TIFF or WebP)"), file), pv, f.el,
    h("label", { class: "field" }, h("span", {}, "Licence or copyright line (optional)"), lic),
    h("label", { class: "check" }, ok, h("span", {}, "I took this photo, or I have permission to print it.")), err, use);
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
