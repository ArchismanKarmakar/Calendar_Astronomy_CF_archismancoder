#!/usr/bin/env python3
"""Block the same countries on every site and Worker in a Cloudflare account.

What it does (dry run unless you pass --apply):

  1. Every zone (domain) in the account gets one WAF custom rule,
     "Block countries (managed)", that blocks the listed countries. A zone rule covers every
     hostname on that domain: Pages and Workers custom domains included.
  2. Workers that already have a custom domain or route get their *.workers.dev address and
     preview URLs switched off. Those addresses aren't on your domain, so zone rules
     never see them. Workers with no custom domain are only reported (switching them off
     would take them offline).
  3. Pages projects are listed with their *.pages.dev address. With --pages-redirect, an
     account Bulk Redirect sends <project>.pages.dev (and its preview subdomains) to the
     project's custom domain, where the zone rule applies.

Usage:
  export CF_API_TOKEN=...   # Create a token at dash.cloudflare.com/profile/api-tokens with:
                            #   Zone > Zone > Read, Zone > Zone WAF > Edit,
                            #   Account > Workers Scripts > Edit, Account > Cloudflare Pages > Read,
                            #   Account > Account Filter Lists > Edit and
                            #   Account > Bulk URL Redirects > Edit (only for --pages-redirect)
  python3 tools/cf_geoblock.py --countries PK,TR,CN,BD,AZ,KP            # see what would change
  python3 tools/cf_geoblock.py --countries PK,TR,CN,BD,AZ,KP --apply    # change it
  python3 tools/cf_geoblock.py --countries PK,TR,CN,BD,AZ,KP --apply --pages-redirect

Free plan: 5 custom rules per zone. Run again any time to change the countries; the
managed rule is updated in place, not duplicated.
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request

API = os.environ.get("CF_API_BASE", "https://api.cloudflare.com/client/v4")
REF = "geo-block-managed"
DESC = "Block countries (managed by cf_geoblock.py)"
LIST_NAME = "pages_dev_to_custom_domain"


class CF:
    def __init__(self, token):
        self.token = token

    def call(self, method, path, body=None, ok404=False):
        req = urllib.request.Request(API + path, method=method,
                                     data=None if body is None else json.dumps(body).encode(),
                                     headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if ok404 and e.code == 404:
                return None
            try:
                j = json.load(e)
                msg = "; ".join(x.get("message", "") for x in j.get("errors", [])) or str(j)
            except Exception:
                msg = e.reason
            raise RuntimeError(f"{method} {path}: HTTP {e.code}: {msg}") from None

    def pages(self, path):
        out, page = [], 1
        while True:
            sep = "&" if "?" in path else "?"
            j = self.call("GET", f"{path}{sep}page={page}&per_page=50")
            res = j.get("result") or []
            out += res
            info = j.get("result_info") or {}
            if not res or page >= (info.get("total_pages") or 1):
                return out
            page += 1


def expression(codes):
    return "(ip.src.country in {" + " ".join(f'"{c}"' for c in codes) + "})"


def countries_in(expr):
    return set(re.findall(r'ip\.src\.country (?:eq|==) "([A-Z0-9]{2})"', expr)) | (
        set(re.findall(r'"([A-Z0-9]{2})"', m.group(1))) if (m := re.search(r"ip\.src\.country in \{([^}]*)\}", expr)) else set())


def do_zones(cf, codes, apply, only):
    want = expression(codes)
    for z in cf.pages("/zones"):
        if only and z["name"] not in only:
            continue
        zid, name = z["id"], z["name"]
        rs = cf.call("GET", f"/zones/{zid}/rulesets/phases/http_request_firewall_custom/entrypoint", ok404=True)
        rules = (rs or {}).get("result", {}).get("rules", []) if rs else []
        mine = next((r for r in rules if r.get("ref") == REF), None)
        same = next((r for r in rules if r is not mine and r.get("action") == "block" and r.get("enabled", True)
                     and countries_in(r.get("expression", "")) >= set(codes)), None)
        rule = {"ref": REF, "description": DESC, "expression": want, "action": "block", "enabled": True}
        if mine and mine.get("expression") == want and mine.get("enabled", True):
            print(f"  {name}: up to date")
        elif same and not mine:
            print(f"  {name}: already blocked by your rule \"{same.get('description', '')}\"; nothing to add")
        elif mine:
            print(f"  {name}: update the managed rule to {', '.join(codes)}")
            if apply:
                cf.call("PATCH", f"/zones/{zid}/rulesets/{rs['result']['id']}/rules/{mine['id']}", rule)
        elif rs:
            print(f"  {name}: add the block rule ({len(rules)} custom rules already)")
            if apply:
                cf.call("POST", f"/zones/{zid}/rulesets/{rs['result']['id']}/rules", rule)
        else:
            print(f"  {name}: create the zone's custom-rules list with the block rule")
            if apply:
                cf.call("PUT", f"/zones/{zid}/rulesets/phases/http_request_firewall_custom/entrypoint",
                        {"name": "default", "kind": "zone", "phase": "http_request_firewall_custom", "rules": [rule]})


def do_workers(cf, acc, apply):
    scripts = [s["id"] for s in cf.pages(f"/accounts/{acc}/workers/scripts")]
    if not scripts:
        print("  no Workers")
        return
    on_domain = {}
    for d in cf.call("GET", f"/accounts/{acc}/workers/domains").get("result") or []:
        on_domain.setdefault(d.get("service"), []).append(d.get("hostname"))
    for z in cf.pages("/zones"):
        for r in cf.call("GET", f"/zones/{z['id']}/workers/routes").get("result") or []:
            if r.get("script"):
                on_domain.setdefault(r["script"], []).append(r.get("pattern"))
    for s in scripts:
        sub = cf.call("GET", f"/accounts/{acc}/workers/scripts/{s}/subdomain", ok404=True)
        st = (sub or {}).get("result") or {}
        dev, prev = st.get("enabled", True), st.get("previews_enabled", True)
        doms = on_domain.get(s)
        if not dev and not prev:
            print(f"  {s}: workers.dev and previews already off" + (f" (served on {', '.join(doms)})" if doms else ""))
        elif doms:
            print(f"  {s}: turn off workers.dev/preview URLs; it stays on {', '.join(doms)}")
            if apply:
                cf.call("POST", f"/accounts/{acc}/workers/scripts/{s}/subdomain", {"enabled": False, "previews_enabled": False})
        else:
            print(f"  {s}: ONLY on workers.dev, which zone rules can't protect. Add a custom domain, then run again.")


def do_pages(cf, acc, apply, redirect):
    projects = cf.pages(f"/accounts/{acc}/pages/projects")
    if not projects:
        print("  no Pages projects")
        return
    items = []
    for p in projects:
        dev = p.get("subdomain") or f"{p['name']}.pages.dev"
        doms = [d for d in p.get("domains") or [] if not d.endswith(".pages.dev")]
        if doms:
            print(f"  {p['name']}: {dev} -> https://{doms[0]}" + ("" if redirect else "  (add --pages-redirect to send it there)"))
            items.append({"redirect": {"source_url": f"{dev}/", "target_url": f"https://{doms[0]}/", "status_code": 301,
                                       "include_subdomains": True, "subpath_matching": True,
                                       "preserve_path_suffix": True, "preserve_query_string": True}})
        else:
            print(f"  {p['name']}: ONLY on {dev}, which zone rules can't protect. Add a custom domain, then run again.")
    if not (redirect and items):
        return
    lists = cf.call("GET", f"/accounts/{acc}/rules/lists").get("result") or []
    lst = next((x for x in lists if x["name"] == LIST_NAME), None)
    print(f"  bulk redirect list '{LIST_NAME}': {'replace' if lst else 'create'} with {len(items)} entries")
    if not apply:
        return
    if not lst:
        lst = cf.call("POST", f"/accounts/{acc}/rules/lists", {"name": LIST_NAME, "kind": "redirect",
                                                               "description": "pages.dev -> custom domain (cf_geoblock.py)"})["result"]
    cf.call("PUT", f"/accounts/{acc}/rules/lists/{lst['id']}/items", items)
    rs = cf.call("GET", f"/accounts/{acc}/rulesets/phases/http_request_redirect/entrypoint", ok404=True)
    rules = [r for r in ((rs or {}).get("result", {}).get("rules") or []) if r.get("ref") != REF + "-pages"]
    keep = [{k: r[k] for k in ("ref", "description", "expression", "action", "action_parameters", "enabled") if k in r} for r in rules]
    keep.append({"ref": REF + "-pages", "description": "pages.dev -> custom domain (cf_geoblock.py)",
                 "expression": f"http.request.full_uri in ${LIST_NAME}", "action": "redirect", "enabled": True,
                 "action_parameters": {"from_list": {"name": LIST_NAME, "key": "http.request.full_uri"}}})
    cf.call("PUT", f"/accounts/{acc}/rulesets/phases/http_request_redirect/entrypoint",
            {"name": "default", "kind": "root", "phase": "http_request_redirect", "rules": keep})


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--countries", required=True, help="two-letter codes, comma separated, e.g. PK,TR,CN")
    ap.add_argument("--apply", action="store_true", help="make the changes (default: only show them)")
    ap.add_argument("--account", help="account ID (default: the token's only account)")
    ap.add_argument("--zones", help="only these domains, comma separated")
    ap.add_argument("--pages-redirect", action="store_true", help="redirect each project's pages.dev to its custom domain")
    a = ap.parse_args()
    codes = sorted({c.strip().upper() for c in a.countries.split(",") if c.strip()})
    if not codes or any(not re.fullmatch(r"[A-Z0-9]{2}", c) for c in codes):
        sys.exit("--countries takes two-letter codes, e.g. PK,TR,CN")
    tok = os.environ.get("CF_API_TOKEN")
    if not tok:
        sys.exit("Set CF_API_TOKEN first (see the top of this file for the permissions).")
    cf = CF(tok)
    acc = a.account
    if not acc:
        accs = cf.pages("/accounts")
        if len(accs) != 1:
            sys.exit("This token sees several accounts; pass --account <id>:\n" + "\n".join(f"  {x['id']}  {x['name']}" for x in accs))
        acc = accs[0]["id"]
    print(("Applying" if a.apply else "Dry run (add --apply to change anything)") + f": block {', '.join(codes)}\n")
    steps = [("Domains (WAF custom rule)", lambda: do_zones(cf, codes, a.apply, set(a.zones.split(",")) if a.zones else None)),
             ("Workers (workers.dev and preview URLs)", lambda: do_workers(cf, acc, a.apply)),
             ("Pages projects (pages.dev)", lambda: do_pages(cf, acc, a.apply, a.pages_redirect))]
    failed = False
    for title, fn in steps:
        print(title)
        try:
            fn()
        except RuntimeError as e:
            failed = True
            print(f"  !! {e}")
        print()
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
