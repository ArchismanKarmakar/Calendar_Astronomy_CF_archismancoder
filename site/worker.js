/* Runs the calendar's Python render code (kit/) inside Pyodide, off the main thread.
   Messages in:  {type:"init", cfg}  then  {type:"run", job, spec, fetches, uploads, edition}
   Messages out: {type:"status"|"progress"|"done"|"error", ...} */
"use strict";
const KIT = "/home/pyodide/kit";
let py = null;
let booting = null;
const have = new Set(); // image files already in the in-memory file system

const post = (m, transfer) => self.postMessage(m, transfer || []);
const status = (job, text, frac) => post({ type: "progress", job, text, frac });

async function getBytes(url, onProgress) {
  const res = await fetch(url);
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try { msg = (await res.json()).error || msg; } catch (e) { /* not JSON */ }
    throw new Error(msg);
  }
  const total = Number(res.headers.get("content-length") || 0);
  if (!res.body || !onProgress) return new Uint8Array(await res.arrayBuffer());
  const reader = res.body.getReader();
  const chunks = [];
  let got = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    chunks.push(value);
    got += value.length;
    onProgress(got, total);
  }
  const out = new Uint8Array(got);
  let o = 0;
  for (const c of chunks) { out.set(c, o); o += c.length; }
  return out;
}

async function init(cfg, job) {
  status(job, "Starting Python in your browser…", 0.02);
  importScripts(cfg.pyodide + "pyodide.js");
  py = await self.loadPyodide({ indexURL: cfg.pyodide });
  status(job, "Loading image and PDF libraries (first time only)…", 0.08);
  await py.loadPackage(["numpy", "pillow", "scipy", "tzdata", "micropip", "charset-normalizer"], {
    messageCallback: () => {}, errorCallback: (e) => console.warn(e),
  });
  status(job, "Loading the calendar engine…", 0.2);
  const micropip = py.pyimport("micropip");
  if (cfg.reportlab.endsWith(".whl")) {
    const whl = await getBytes("py/" + cfg.reportlab);
    py.FS.writeFile("/tmp/" + cfg.reportlab, whl);
    await micropip.install("emfs:/tmp/" + cfg.reportlab, { deps: false });
  } else {
    await micropip.install(cfg.reportlab, { deps: false });
  }
  const zip = await getBytes("py/kit.zip?v=" + encodeURIComponent(cfg.version || ""));
  py.FS.mkdirTree(KIT);
  py.FS.writeFile("/tmp/kit.zip", zip);
  py.runPython(`import zipfile; zipfile.ZipFile("/tmp/kit.zip").extractall("${KIT}")`);
  for (const d of ["fonts", "data/editions", "photos/web", "out"]) py.FS.mkdirTree(`${KIT}/${d}`);
  await Promise.all(cfg.fonts.map(async (f) => {
    py.FS.writeFile(`${KIT}/fonts/${f}.ttf`, await getBytes(`fonts/${f}.ttf`));
  }));
  py.runPython(`import sys; sys.path.insert(0, "${KIT}"); import webgen`);
}

function rmTree(dir) {
  try {
    for (const f of py.FS.readdir(dir)) {
      if (f === "." || f === "..") continue;
      const p = `${dir}/${f}`;
      if (py.FS.isDir(py.FS.stat(p).mode)) rmTree(p); else py.FS.unlink(p);
    }
  } catch (e) { /* missing */ }
}

async function run(msg) {
  const { job, spec, fetches, uploads, edition, cfg } = msg;
  if (!py) {
    booting = booting || init(cfg, job);
    await booting;
  }
  const warnings = [];
  // edition data
  const edPath = `data/editions/${spec.code}.json`;
  if (!have.has(edPath)) {
    py.FS.writeFile(`${KIT}/${edPath}`, await getBytes(edition));
    have.add(edPath);
  }
  spec.edition_path = edPath;
  // images: uploads arrive as bytes, the rest come through /api/img
  for (const u of uploads || []) {
    const p = `${KIT}/photos/web/${u.key}.${u.ext}`;
    py.FS.writeFile(p, new Uint8Array(u.bytes));
    have.add(p);
  }
  const need = fetches.filter((f) => !have.has(`${KIT}/photos/web/${f.key}.jpg`));
  let i = 0;
  for (const f of need) {
    i++;
    const p = `${KIT}/photos/web/${f.key}.jpg`;
    const label = `Downloading picture ${i} of ${need.length} (${f.id})`;
    status(job, label + "…", 0.25 + 0.2 * (i - 1) / need.length);
    try {
      const b = await getBytes(f.url, (got, total) => {
        const mb = (got / 1e6).toFixed(1) + (total ? ` of ${(total / 1e6).toFixed(0)} MB` : " MB");
        status(job, `${label}: ${mb}`, 0.25 + 0.2 * (i - 1 + (total ? got / total : 0.5)) / need.length);
      });
      py.FS.writeFile(p, b);
      have.add(p);
    } catch (e) {
      warnings.push(`${f.id}: ${e.message}`);
    }
  }
  for (const slot of Object.keys(spec.images)) {
    const im = spec.images[slot];
    const p = `${KIT}/photos/web/${im._key}.${im._ext || "jpg"}`;
    im.file = have.has(p) ? p : "/missing.jpg";
  }
  // a full build starts from a clean background cache (keeps memory in check)
  if (spec.pages === "all") rmTree(`${KIT}/build/bg`);
  const out = `out/${job}.pdf`;
  spec.out = out;
  py.globals.set("SPEC", JSON.stringify(spec));
  const base = spec.pages === "all" ? 0.45 : 0.3;
  py.globals.set("PROG", (done, total, label) => {
    status(job, done >= total ? "Saving the PDF…" : `Drawing ${label} (${done + 1} of ${total})…`,
      base + (1 - base) * 0.97 * (done / Math.max(1, total)));
  });
  await py.runPythonAsync("import webgen; webgen.generate(SPEC, PROG)");
  const pdf = py.FS.readFile(`${KIT}/${out}`);
  py.FS.unlink(`${KIT}/${out}`);
  post({ type: "done", job, pdf, warnings }, [pdf.buffer]);
}

self.onmessage = async (ev) => {
  const msg = ev.data;
  if (msg.type !== "run") return;
  try {
    await run(msg);
  } catch (e) {
    const text = String((e && e.message) || e);
    const short = text.includes("Traceback") ? text.trim().split("\n").slice(-1)[0] : text;
    post({ type: "error", job: msg.job, message: short, detail: text.slice(-4000) });
  }
};
