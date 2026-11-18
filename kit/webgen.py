"""
Entry point used by the website. It runs inside Pyodide (Python compiled to
WebAssembly) in the visitor's browser, with the same render code as the kit, so
a calendar made on the site matches one built with `python build.py`.

The site writes into Pyodide's in-memory file system:
  data/editions/<CODE>.json   precomputed events for the city (make_site.py)
  photos/web/<id>.<ext>       each chosen image (downloaded or uploaded)
then calls generate(spec_json) and reads back the PDF.
"""
import json
import os

import util

os.chdir(util.HERE)
SLOTS = ["cover"] + [f"{m:02d}" for m in range(1, 13)]


def prepare(spec):
    import skycalc
    loc = util.read_json(spec["edition_path"])
    ed = loc["edition"]
    for k in ("paper", "week_start"):
        if spec.get(k) is not None:
            ed[k] = spec[k]
    if spec.get("label"):
        ed["label"] = spec["label"]
    hol = spec.get("holidays")  # {"country": "India", "days": {"2027-01-26": "Republic Day", ...}} or None
    if hol and hol.get("days"):
        loc["holidays"], loc["holiday_country"] = hol["days"], hol.get("country", "")
    else:
        loc.pop("holidays", None)
    fest = spec.get("festivals")  # {"name": "Bengali festivals", "days": {...}} or None
    if fest and fest.get("days"):
        loc["festivals"], loc["festival_name"] = fest["days"], fest.get("name", "")
    else:
        loc.pop("festivals", None)
    imgs = {}
    for slot in SLOTS:
        o = dict(spec["images"][slot])
        o["slot"] = slot
        for k, v in (("license", "CC BY 4.0"), ("catalog", ""), ("kind", ""), ("constellation", ""),
                     ("distance", ""), ("fit", "cover"), ("focus", None), ("zoom", 1.0), ("note", ""),
                     ("object", o.get("title") or "Photograph")):
            o.setdefault(k, v)
        imgs[slot] = o
    lat, lon = ed["city"][1], ed["city"][2]
    for m in range(1, 13):
        o = imgs[f"{m:02d}"]
        md = loc["months"][str(m)]
        try:
            md["transit"], md["transit_alt"] = skycalc.transit_simple(lat, lon, ed["tz"], m, o["ra"], o["dec"],
                                                                        loc["year"])
        except Exception:  # no position given (own photo) or unreadable
            md["transit"], md["transit_alt"] = None, None
    util.write_json("data/edition_WEB.json", loc)
    return loc, imgs


def generate(spec_json, progress=None):
    spec = json.loads(spec_json)
    import build
    import render as R
    R.register_fonts()
    loc, imgs = prepare(spec)
    cfg = dict(util.read_json("brand.json"))
    for k in ("title", "subtitle"):
        if spec.get(k):
            cfg[k] = spec[k][:60]
    what = spec.get("pages", "all")
    if what == "all":
        kw = dict(parts=("cover", "legend", "months", "year"))
    elif what == "cover":
        kw = dict(parts=("cover",))
    elif what == "legend":
        kw = dict(parts=("legend",))
    elif what == "year":
        kw = dict(parts=("year",))
    else:  # "month:N"
        kw = dict(parts=("months",), months=[int(what.split(":")[1])])
    out = spec.get("out", "out/calendar.pdf")
    build.build_pdf("WEB", spec["format"], imgs, int(spec.get("dpi", 200)), cfg, "out", fn=out, progress=progress,
                    **kw)
    return out
