// GET /api/meta?id=eso1733a[&src=eso|esahubble]   (id may also be a page URL)
// Reads an image's title, credit, size, object and position from its ESO or
// ESA/Hubble page. Same rules as kit/imgmeta.py. The site asks the visitor to check
// the credit before using it.
import { SOURCES, RENDITIONS, ID_RE, guessSource, parseId, sameSite, json, COMMONS_API, COMMONS_UA, MIN_PIXELS,
  commonsTitle, licenceVerdict } from "../../lib/sources.js";

const stripHtml = (s) => String(s || "").replace(/<[^>]+>/g, "").replace(/&amp;/g, "&").replace(/&quot;/g, '"')
  .replace(/&#39;|&apos;/g, "'").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/\s+/g, " ").trim();

async function commonsLookup(title) {
  const q = new URLSearchParams({ action: "query", format: "json", prop: "imageinfo", titles: title,
    iiprop: "url|size|extmetadata|mime", iiurlwidth: "6000" });
  let r;
  try {
    r = await fetch(`${COMMONS_API}?${q}`, { headers: { "user-agent": COMMONS_UA }, cf: { cacheEverything: true, cacheTtl: 86400 } });
  } catch (e) {
    return json({ error: `Could not reach Wikimedia Commons: ${e.message}` }, 502);
  }
  if (!r.ok) return json({ error: `Wikimedia Commons answered HTTP ${r.status}.` }, 502);
  const data = await r.json();
  const page = Object.values((data.query || {}).pages || {})[0];
  if (!page || "missing" in page) return json({ error: `${title} was not found on Wikimedia Commons.` }, 404);
  const ii = (page.imageinfo || [{}])[0];
  const em = ii.extmetadata || {};
  const get = (k) => stripHtml((em[k] || {}).value);
  const short = get("LicenseShortName");
  const v = licenceVerdict(short);
  const w = ii.width || 0, h = ii.height || 0;
  if (v.ok && Math.max(w, h) < MIN_PIXELS) { v.ok = false; v.reason = `too small for print (${w}x${h} px)`; }
  if (!v.ok) return json({ error: `This photo can't be used in a calendar: ${v.reason} (licence: ${short || "none"}).` }, 422);
  const artist = get("Artist") || get("Credit") || "Unknown author";
  const credit = get("Attribution") || `${artist} / Wikimedia Commons`;
  const slug = page.title.toLowerCase().replace(/^file:/, "").replace(/\.(jpe?g|png|tiff?)$/, "").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 36);
  const big = ii.thumburl && ii.thumbwidth && ii.thumbwidth < w ? ii.thumburl : ii.url;
  return json({
    id: `wm-${slug}`, source: "commons", title: get("ObjectName") || page.title.replace(/^File:/, "").replace(/\.[a-z]+$/i, ""),
    credit: credit.slice(0, 300), license: short, page: ii.descriptionurl, pixels: [w, h], renditions: [],
    file_url: big, thumb_url: (ii.thumburl || "").replace(/\/\d+px-/, "/640px-"),
    object: "", catalog: "", kind: "", constellation: "", distance: "", ra: "", dec: "", fit: w / Math.max(1, h) > 2.6 ? "band" : "cover",
    focus: null, zoom: 1, rotate: "auto",
    note: v.sa ? "CC BY-SA: the calendar page that uses it is shared under the same licence." : "",
  }, 200, { "cache-control": "public, max-age=86400" });
}

const unescape = (s) => s
  .replace(/&#(\d+);/g, (_, n) => String.fromCodePoint(+n))
  .replace(/&#x([0-9a-f]+);/gi, (_, n) => String.fromCodePoint(parseInt(n, 16)))
  .replace(/&quot;/g, '"').replace(/&apos;|&#39;/g, "'").replace(/&lt;/g, "<").replace(/&gt;/g, ">")
  .replace(/&nbsp;/g, " ").replace(/&deg;/g, "°").replace(/&rsquo;/g, "’").replace(/&lsquo;/g, "‘")
  .replace(/&ldquo;/g, "“").replace(/&rdquo;/g, "”").replace(/&ndash;/g, "–").replace(/&mdash;/g, "—")
  .replace(/&amp;/g, "&");

export function htmlToLines(page) {
  let p = page.replace(/<(script|style|noscript)[^>]*>[\s\S]*?<\/\1>/gi, " ");
  p = p.replace(/<br\s*\/?>/gi, "\n");
  p = p.replace(/<\/?(p|div|tr|td|th|li|ul|h[1-6]|table|section|dt|dd)(\s[^>]*)?>/gi, "\n");
  p = p.replace(/<[^>]+>/g, "");
  return p.split("\n").map((x) => unescape(x).replace(/\s+/g, " ").trim()).filter(Boolean);
}

function labelValue(lines, label, nth = 0) {
  const lab = label.toLowerCase();
  let found = 0;
  for (let i = 0; i < lines.length; i++) {
    const low = lines[i].toLowerCase();
    if (low === lab + ":" || low === lab || low.startsWith(lab + ":")) {
      if (found < nth) { found++; continue; }
      const rest = lines[i].length > lab.length + 1 ? lines[i].slice(lab.length + 1).replace(/^[\s:]+|[\s:]+$/g, "") : "";
      return rest || lines[i + 1] || "";
    }
  }
  return "";
}

const STOP = ["about the image", "about the object", "image formats", "id:", "related", "usage of", "coordinates",
  "release date", "wallpapers", "colours & filters", "mounted image", "zoomable"];

function creditFrom(lines) {
  for (let i = 0; i < lines.length; i++) {
    if (/^credit/i.test(lines[i])) {
      const rest = lines[i].replace(/^credits?\s*:?\s*/i, "").trim();
      const parts = rest ? [rest] : [];
      for (const nxt of lines.slice(i + 1, i + 6)) {
        if (STOP.some((s) => nxt.toLowerCase().startsWith(s))) break;
        parts.push(nxt);
        if (parts.join(" ").length > 30 && !/(,|\/|and|&)$/.test(nxt)) break;
      }
      return parts.join(" ").replace(/\s+/g, " ").trim().slice(0, 400);
    }
  }
  return "";
}

function kind(t) {
  const skip = new Set(["milky way", "local universe", "early universe", "type", "appearance", "solar system",
    "unspecified", "illustration", "x - illustrations"]);
  const toks = t.split(":").map((x) => x.trim()).filter((x) => x && !skip.has(x.toLowerCase()));
  if (!toks.length) return "";
  if (toks.length >= 2) {
    const adj = ["spiral", "elliptical", "irregular", "barred", "lenticular", "planetary", "emission", "reflection",
      "dark", "globular", "open", "interacting", "dwarf"];
    const last = toks[toks.length - 1];
    return adj.includes(last.toLowerCase()) ? `${last} ${toks[0].toLowerCase()}` : `${toks[0]} (${last.toLowerCase()})`;
  }
  return toks[0];
}

function coord(v) {
  const p = v.replace(/[°'"hms]/g, " ").split(/\s+/).filter(Boolean);
  if (p.length < 2 || !/^[+-]?\d+$/.test(p[0])) return "";
  const b = parseFloat(p[1]), c = p.length > 2 ? parseFloat(p[2]) : 0;
  if (Number.isNaN(b) || Number.isNaN(c)) return "";
  return `${p[0]}:${String(Math.trunc(b)).padStart(2, "0")}:${String(Math.min(59, Math.round(c))).padStart(2, "0")}`;
}

export function parsePage(page, id, source) {
  const lines = htmlToLines(page);
  let title = "";
  let m = page.match(/<meta[^>]+property=["']og:title["'][^>]+content=["']([^"']+)/i);
  if (m) title = unescape(m[1]).trim();
  if (!title) {
    m = page.match(/<h1[^>]*>([\s\S]*?)<\/h1>/i) || page.match(/<title>([\s\S]*?)<\/title>/i);
    title = m ? unescape(m[1]).replace(/<[^>]+>|\s*\|.*$/g, "").trim() : id;
  }
  const size = labelValue(lines, "Size");
  const px = (size.replace(/,/g, "").match(/\d+/g) || []).slice(0, 2).map(Number);
  const name = labelValue(lines, "Name");
  const names = name ? name.split(",").map((x) => x.trim()).filter(Boolean) : [];
  const catRe = /^(NGC|IC|M|Messier|Sh2|RCW|LBN|LDN|Abell|Arp|ESO|Barnard|B|Cederblad|vdB|Gum|Collinder|Melotte|Hen|PGC|UGC|HD|HR)[\s-]?\d/i;
  const cat = names.filter((x) => catRe.test(x));
  const obj = names.find((x) => !cat.includes(x)) || names[0] || title;
  const esc = id.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const rends = [...new Set([...page.matchAll(new RegExp(`/images/([a-z0-9_]+)/${esc}\\.jpg`, "g"))].map((x) => x[1]))]
    .filter((r) => RENDITIONS.includes(r))
    .sort((a, b) => RENDITIONS.indexOf(a) - RENDITIONS.indexOf(b));
  const dist = labelValue(lines, "Distance").replace(/light years?/i, "ly").trim();
  return {
    id, source, title, credit: creditFrom(lines), license: "CC BY 4.0", page: SOURCES[source].page(id),
    pixels: px.length === 2 ? px : [0, 0],
    renditions: rends.length ? rends : ["publicationjpg", "large", "screen"],
    object: obj.slice(0, 60), catalog: cat.join(" / ").slice(0, 40), kind: kind(labelValue(lines, "Type", 1)),
    constellation: labelValue(lines, "Constellation").slice(0, 30), distance: dist.slice(0, 30),
    ra: coord(labelValue(lines, "Position (RA)")), dec: coord(labelValue(lines, "Position (Dec)")),
    fit: px.length === 2 && px[1] && px[0] / px[1] > 2.6 ? "band" : "cover", focus: null, zoom: 1, note: "",
  };
}

export async function onRequestGet({ request, env }) {
  if (!sameSite(request, env)) return json({ error: "This lookup only serves this site." }, 403);
  const u = new URL(request.url);
  const ct = commonsTitle(u.searchParams.get("id"));
  if (ct) return commonsLookup(ct);
  const parsed = parseId(u.searchParams.get("id"));
  const id = parsed.id;
  const source = u.searchParams.get("src") || parsed.source || guessSource(id);
  if (!SOURCES[source] || SOURCES[source].noLookup || !ID_RE.test(id)) {
    return json({ error: "That isn't an ESO, ESA/Hubble or ESA/Webb image ID (for example eso1733a, heic1509a or weic2326a)." }, 400);
  }
  const url = SOURCES[source].page(id);
  let res;
  try {
    res = await fetch(url, {
      headers: { "user-agent": "Mozilla/5.0 (2027 calendar maker)" },
      cf: { cacheEverything: true, cacheTtl: 60 * 60 * 24 },
    });
  } catch (e) {
    return json({ error: `Could not reach ${SOURCES[source].name}: ${e.message}` }, 502);
  }
  if (res.status === 404) {
    return json({ error: `No image called ${id} on ${SOURCES[source].name}. Check the ID, or try the other site.` }, 404);
  }
  if (!res.ok) return json({ error: `${SOURCES[source].name} answered HTTP ${res.status}.` }, 502);
  const meta = parsePage(await res.text(), id, source);
  if (!meta.credit) meta.warning = "The credit wasn't found on the page; type it in exactly as the page shows it.";
  return json(meta, 200, { "cache-control": "public, max-age=86400" });
}
