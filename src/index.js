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
    if (request.method !== "GET" && request.method !== "HEAD") {
      return new Response("Method not allowed", { status: 405, headers: { allow: "GET, HEAD" } });
    }
    return handler({ request, env, waitUntil: (p) => ctx.waitUntil(p) });
  },
};
