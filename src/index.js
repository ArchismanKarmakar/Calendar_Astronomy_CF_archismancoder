// Cloudflare Worker entry: serves /api/img and /api/meta; everything else is the static site
// (the `site/` folder), which Cloudflare serves directly without running this code.
import { onRequestGet as img } from "../functions/api/img.js";
import { onRequestGet as meta } from "../functions/api/meta.js";

const ROUTES = { "/api/img": img, "/api/meta": meta };

export default {
  async fetch(request, env, ctx) {
    const { pathname } = new URL(request.url);
    const handler = ROUTES[pathname];
    if (!handler) return env.ASSETS.fetch(request);
    const blocked = (env.BLOCKED_COUNTRIES || "").toUpperCase().split(/[\s,]+/).filter(Boolean);
    const country = request.cf && request.cf.country;
    if (country && blocked.includes(country)) {
      return new Response("Not available in your region.", { status: 403, headers: { "content-type": "text/plain; charset=utf-8" } });
    }
    if (request.method !== "GET" && request.method !== "HEAD") {
      return new Response("Method not allowed", { status: 405, headers: { allow: "GET, HEAD" } });
    }
    return handler({ request, env, waitUntil: (p) => ctx.waitUntil(p) });
  },
};
