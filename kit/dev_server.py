#!/usr/bin/env python3
"""
Preview the website on your own computer before pushing:

    python dev_server.py            # then open http://localhost:8027

Serves ../site and stands in for the Cloudflare functions: /api/img returns your
downloaded copy from photos/options/ (any size requested), /api/meta reads an
image's page from ESO / ESA-Hubble with imgmeta.py.
"""
import argparse
import http.server
import json
import mimetypes
import os
import sys
import urllib.parse

import util

SITE = os.path.abspath(os.path.join(util.HERE, "..", "site"))
mimetypes.add_type("application/wasm", ".wasm")
mimetypes.add_type("text/javascript", ".mjs")


class Handler(http.server.SimpleHTTPRequestHandler):
    extra = {}

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=SITE, **kw)

    def log_message(self, fmt, *args):
        if "/api/" in self.path or (args and str(args[1]) >= "400"):
            sys.stderr.write("  " + fmt % args + "\n")

    def send_json(self, obj, status=200):
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def translate_path(self, path):
        for prefix, root in self.extra.items():  # e.g. a local Pyodide copy for offline testing
            if path.startswith(prefix):
                return os.path.join(root, urllib.parse.unquote(path[len(prefix):].split("?")[0]))
        return super().translate_path(path)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = dict(urllib.parse.parse_qsl(u.query))
        if u.path == "/api/img":
            iid = q.get("id", "")
            lib = util.library()
            if q.get("src") == "commons":  # map the Commons URL back to the downloaded copy
                iid = next((k for k, o in lib.items() if o.get("file_url") == q.get("u")), "")
            o = lib.get(iid, {"id": iid})
            p = util.option_path(o)
            if not os.path.exists(p):
                return self.send_json({"error": f"{iid} isn't in photos/options/ (run fetch_images.py)"}, 404)
            if q.get("r", "").startswith("thumb"):
                t = os.path.join(SITE, "thumbs", f"{iid}.jpg")
                p = t if os.path.exists(t) else p
            with open(p, "rb") as f:
                b = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(b)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(b)
            return
        if u.path == "/api/meta":
            import imgmeta
            try:
                if "File:" in q.get("id", "") or "wikimedia" in q.get("id", "") or "wikipedia" in q.get("id", ""):
                    m = imgmeta.commons_fetch(q["id"])
                    if not m.pop("ok"):
                        return self.send_json({"error": f"This photo can't be used in a calendar: {m['reason']}"}, 422)
                    m.pop("reason", None)
                    m["renditions"] = []
                    m.pop("downloads", None)
                    return self.send_json(m)
                m = imgmeta.fetch(q.get("id", ""), q.get("src"))
            except Exception as e:
                return self.send_json({"error": str(e)}, 502)
            m["renditions"] = list(m.pop("downloads"))
            return self.send_json(m)
        return super().do_GET()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8027)
    ap.add_argument("--pyodide-dir", help="serve a local Pyodide at /pyodide/ (set pyodide: '/pyodide/' in config.js)")
    a = ap.parse_args()
    if a.pyodide_dir:
        Handler.extra["/pyodide/"] = os.path.abspath(a.pyodide_dir)
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    print(f"Serving {SITE} at http://localhost:{a.port}  (Ctrl+C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
