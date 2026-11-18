// Image sources the site may proxy. Only these hosts, only these renditions.
// cdn() may return several mirror URLs; they are tried in order.
export const SOURCES = {
  eso: {
    name: "ESO",
    page: (id) => `https://www.eso.org/public/images/${id}/`,
    cdn: (id, r) => `https://cdn.eso.org/images/${r}/${id}.jpg`,
  },
  esahubble: {
    name: "ESA/Hubble",
    page: (id) => `https://esahubble.org/images/${id}/`,
    cdn: (id, r) => `https://cdn.esahubble.org/archives/images/${r}/${id}.jpg`,
  },
  esawebb: {
    name: "ESA/Webb",
    page: (id) => `https://esawebb.org/images/${id}/`,
    cdn: (id, r) => `https://cdn.esawebb.org/archives/images/${r}/${id}.jpg`,
  },
  noirlab: {
    name: "NOIRLab",
    page: (id) => `https://noirlab.edu/public/images/${id}/`,
    cdn: (id, r) => [`https://noirlab.edu/public/media/archives/images/${r}/${id}.jpg`,
      `https://storage.noirlab.edu/media/archives/images/${r}/${id}.jpg`],
    noLookup: true, // curated images only (no page reading)
  },
};
export const RENDITIONS = ["publicationjpg", "large", "screen", "wallpaper5", "wallpaper4", "thumb300y", "thumb700x"];
export const ID_RE = /^[a-z0-9][a-z0-9_-]{2,40}$/;

export function guessSource(id) {
  if (/^(weic|potm)\d/.test(id)) return "esawebb";
  return /^(heic|opo|potw|ann|sci)\d/.test(id) ? "esahubble" : "eso";
}

// Accept an ID or a page / CDN URL.
export function parseId(text) {
  const t = String(text || "").trim().replace(/\/+$/, "");
  const m = t.match(/(eso\.org|esahubble\.org|spacetelescope\.org|esawebb\.org)\/(?:public\/)?(?:archives\/)?images\/(?:[a-z0-9_]+\/)?([a-z0-9_-]+?)(?:\.(?:jpg|tif|png))?$/i);
  if (m) {
    const host = m[1].toLowerCase();
    return { source: host === "esawebb.org" ? "esawebb" : host === "eso.org" ? "eso" : "esahubble", id: m[2].toLowerCase() };
  }
  return { source: null, id: t.toLowerCase() };
}

// Only answer requests made by this site's own pages (stops hot-linking the proxy).
export function sameSite(request, env) {
  if (env && env.ALLOW_ANY_ORIGIN === "1") return true;
  const site = request.headers.get("sec-fetch-site");
  if (site && !["same-origin", "none"].includes(site)) return false;
  const origin = request.headers.get("origin");
  if (origin && new URL(origin).host !== new URL(request.url).host) return false;
  return true;
}

export function json(obj, status = 200, extra = {}) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", ...extra },
  });
}

// ---------------------------------------------------------------- Wikimedia Commons
// Free-licence photos by astrophotographers. Same rules as kit/imgmeta.py:
// public domain / CC0, CC BY, CC BY-SA are accepted; NC, ND and GFDL-only are refused.
export const COMMONS_API = "https://commons.wikimedia.org/w/api.php";
export const COMMONS_UA = "DeepSpaceExplorer2027-calendar/1.0 (calendar image lookup)";
export const MIN_PIXELS = 4000;

export function commonsTitle(text) {
  let t = String(text || "").trim();
  try { t = decodeURIComponent(t); } catch (e) { /* keep as typed */ }
  const m = t.match(/(?:File|Image|Datei|Fichier):([^#?&|]+)$/) || t.match(/(?:File|Image):([^#?&|/]+)/);
  return m ? "File:" + m[1].replace(/_/g, " ").trim() : null;
}

export function licenceVerdict(short) {
  const u = String(short || "").toUpperCase().replace(/-/g, " ");
  if (!u) return { ok: false, sa: false, reason: "no licence stated" };
  if (/\bNC\b|NONCOMMERCIAL|NON COMMERCIAL/.test(u)) return { ok: false, sa: false, reason: "non-commercial only" };
  if (/\bND\b|NO DERIV/.test(u)) return { ok: false, sa: false, reason: "no derivatives allowed" };
  if (u.includes("CC0") || u.includes("PUBLIC DOMAIN") || /^PD\b/.test(u)) return { ok: true, sa: false, reason: "public domain" };
  if (u.includes("CC BY") || u.startsWith("ATTRIBUTION") || u.includes("COPYRIGHTED FREE USE"))
    return { ok: true, sa: /\bSA\b/.test(u) || u.includes("BY SA"), reason: "free licence" };
  if (u.includes("GFDL")) return { ok: false, sa: false, reason: "GFDL only (requires printing the full licence text)" };
  return { ok: false, sa: false, reason: `licence not recognised: ${short}` };
}

export function isCommonsUpload(u) {
  try { const x = new URL(u); return x.protocol === "https:" && x.hostname === "upload.wikimedia.org"; }
  catch (e) { return false; }
}
