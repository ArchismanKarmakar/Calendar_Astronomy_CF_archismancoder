// GET /api/img?src=eso|esahubble|esawebb|noirlab&id=eso1208a&r=publicationjpg
// Streams an ESO or ESA/Hubble image through this site so the browser can read its
// pixels (their CDNs don't send CORS headers). Cached at Cloudflare's edge.
import { SOURCES, RENDITIONS, ID_RE, sameSite, json, isCommonsUpload, COMMONS_UA } from "../../lib/sources.js";

const MAX_BYTES = 220e6; // the biggest single JPEGs the site ever asks for

export async function onRequestGet({ request, env }) {
  if (!sameSite(request, env)) return json({ error: "This image proxy only serves this site." }, 403);
  const u = new URL(request.url);
  const src = u.searchParams.get("src") || "";
  if (src === "commons") {  // a Wikimedia Commons file: only upload.wikimedia.org
    const target = u.searchParams.get("u") || "";
    if (!isCommonsUpload(target)) return json({ error: "Only upload.wikimedia.org files can be loaded." }, 400);
    let up;
    try {
      up = await fetch(target, { headers: { "user-agent": COMMONS_UA }, cf: { cacheEverything: true, cacheTtl: 2592000 } });
    } catch (e) {
      return json({ error: `Could not reach Wikimedia Commons: ${e.message}` }, 502);
    }
    if (!up.ok) return json({ error: `Wikimedia Commons answered HTTP ${up.status}.` }, up.status === 404 ? 404 : 502);
    const type = up.headers.get("content-type") || "";
    if (!type.startsWith("image/")) return json({ error: "That Commons file is not an image." }, 502);
    const len = Number(up.headers.get("content-length") || 0);
    if (len > MAX_BYTES) return json({ error: "That Commons file is too large for the browser." }, 413);
    const h = new Headers({ "content-type": type, "cache-control": "public, max-age=2592000, immutable" });
    if (len) h.set("content-length", String(len));
    return new Response(up.body, { headers: h });
  }
  const id = (u.searchParams.get("id") || "").toLowerCase();
  const r = u.searchParams.get("r") || "publicationjpg";
  if (!SOURCES[src] || !ID_RE.test(id) || !RENDITIONS.includes(r)) {
    return json({ error: "Unknown image. Use src=eso|esahubble|esawebb|noirlab, an image ID, and a known size." }, 400);
  }
  const urls = [].concat(SOURCES[src].cdn(id, r));
  let up = null, url = urls[0];
  for (const u of urls) {
    url = u;
    try {
      up = await fetch(u, {
        headers: { "user-agent": "Mozilla/5.0 (2027 calendar maker)" },
        cf: { cacheEverything: true, cacheTtl: 60 * 60 * 24 * 30 },
      });
    } catch (e) {
      up = null;
      continue;
    }
    if (up.ok) break;
  }
  if (!up) return json({ error: `Could not reach ${SOURCES[src].name}.` }, 502);
  if (!up.ok) {
    return json({ error: `${SOURCES[src].name} has no ${r} file for ${id} (HTTP ${up.status}).` },
      up.status === 404 ? 404 : 502);
  }
  const type = up.headers.get("content-type") || "";
  if (!type.startsWith("image/")) return json({ error: `${url} did not return an image.` }, 502);
  const len = Number(up.headers.get("content-length") || 0);
  if (len > MAX_BYTES) {
    return json({ error: `${id} ${r} is ${Math.round(len / 1e6)} MB — too large for the browser.`, bytes: len }, 413);
  }
  const headers = new Headers({
    "content-type": type,
    "cache-control": "public, max-age=2592000, immutable",
    "x-image-source": url,
  });
  if (len) headers.set("content-length", String(len));
  return new Response(up.body, { headers });
}
