/* Wikimedia Commons, straight from the browser (Commons answers cross-site requests when
   asked with origin=*), so Commons photos work even when this site's own API is down.
   Same licence rules as kit/imgmeta.py and lib/sources.js. */
"use strict";
window.Commons = (() => {
  const API = "https://commons.wikimedia.org/w/api.php";
  const MIN_PIXELS = 4000;
  const strip = (s) => {
    const d = document.createElement("div");
    d.innerHTML = String(s || "");
    return d.textContent.replace(/\s+/g, " ").trim();
  };
  function verdict(short) {
    const u = String(short || "").toUpperCase().replace(/-/g, " ");
    if (!u) return { ok: false, reason: "no licence stated" };
    if (/\bNC\b|NONCOMMERCIAL|NON COMMERCIAL/.test(u)) return { ok: false, reason: "non-commercial only" };
    if (/\bND\b|NO DERIV/.test(u)) return { ok: false, reason: "no derivatives allowed" };
    if (u.includes("CC0") || u.includes("PUBLIC DOMAIN") || /^PD\b/.test(u)) return { ok: true, reason: "public domain" };
    if (u.includes("CC BY") || u.startsWith("ATTRIBUTION")) return { ok: true, sa: /\bSA\b/.test(u), reason: "free licence" };
    if (u.includes("GFDL")) return { ok: true, gfdl: true, reason: "GNU FDL" };
    return { ok: false, reason: `licence not recognised (${short})` };
  }
  /** 'File:X.jpg' from a title, a Commons/Wikipedia page or a media-viewer link; null otherwise. */
  function title(text) {
    let t = String(text || "").trim();
    try { t = decodeURIComponent(t); } catch (e) { /* keep */ }
    const m = t.match(/(?:File|Image|Datei|Fichier):([^#?&|/]+\.(?:jpe?g|png|tiff?))/i);
    return m ? "File:" + m[1].replace(/_/g, " ").trim() : null;
  }
  /** Small preview that works before the licence check: Commons redirects to its own thumbnail. */
  const thumb = (t, w = 640) => `https://commons.wikimedia.org/wiki/Special:FilePath/${encodeURIComponent(t.replace(/^File:/, ""))}?width=${w}`;
  const cache = new Map();
  /** Full details and a verdict for one or more files: Map title -> info. */
  async function info(titles) {
    const want = [].concat(titles).filter((t) => !cache.has(t));
    for (let i = 0; i < want.length; i += 40) {
      const q = new URLSearchParams({ action: "query", format: "json", origin: "*", prop: "imageinfo",
        titles: want.slice(i, i + 40).join("|"), iiprop: "url|size|extmetadata|mime", iiurlwidth: "640" });
      const r = await fetch(`${API}?${q}`);
      if (!r.ok) throw new Error(`Wikimedia Commons answered HTTP ${r.status}`);
      const data = await r.json();
      const norm = new Map(((data.query || {}).normalized || []).map((n) => [n.to, n.from]));
      for (const p of Object.values((data.query || {}).pages || {})) {
        const asked = norm.get(p.title) || p.title;
        if ("missing" in p || !p.imageinfo) { cache.set(asked, { ok: false, reason: "not found on Wikimedia Commons" }); continue; }
        const ii = p.imageinfo[0], em = ii.extmetadata || {};
        const get = (k) => strip((em[k] || {}).value);
        const short = get("LicenseShortName");
        const v = verdict(short);
        const w = ii.width || 0, h = ii.height || 0;
        if (v.ok && Math.max(w, h) < MIN_PIXELS) Object.assign(v, { ok: false, reason: `too small for print (${w}×${h} px)` });
        const artist = get("Artist") || get("Credit") || "Unknown author";
        cache.set(asked, Object.assign(v, {
          license: short, license_url: get("LicenseUrl"), page: ii.descriptionurl, pixels: [w, h],
          credit: (get("Attribution") || `${artist} / Wikimedia Commons`).slice(0, 300),
          file_url: ii.size && ii.size > 90e6 ? ii.thumburl.replace(/\/\d+px-/, "/8000px-") : ii.url,
          thumb_url: ii.thumburl, title_text: get("ObjectName") || p.title.replace(/^File:/, "").replace(/\.[a-z]+$/i, ""),
        }));
      }
    }
    const out = new Map();
    for (const t of [].concat(titles)) out.set(t, cache.get(t));
    return out;
  }
  return { verdict, title, thumb, info };
})();
