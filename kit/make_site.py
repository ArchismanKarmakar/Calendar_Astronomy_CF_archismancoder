#!/usr/bin/env python3
"""
Build the website's data into ../site (then commit and push; Cloudflare Pages
serves the folder as it is, with no build step).

    python make_site.py                  # everything, including the ready-made PDFs
    python make_site.py --no-ready       # skip the ready-made PDFs and previews (fast)
    python make_site.py --ready IN UK    # which editions get ready-made PDFs

Writes:
  site/data/cities.json            every city / time zone the site offers
  site/data/editions/<CODE>.json   that city's 2027 events, Moon and dark nights
  site/data/library.json           every image (suggested per page + your additions)
  site/thumbs/<id>.jpg             thumbnails from photos/options (if downloaded)
  site/fonts/*.ttf                 the calendar's fonts
  site/py/kit.zip                  the Python render code the browser runs
  site/py/reportlab-*.whl          ReportLab for the browser (pure Python)
  site/data/holidays/<KEY>.json    public holidays for each country (2027)
  site/downloads/*.pdf             ready-made calendars (+ cover thumbnails)
  site/sample/*.jpg                page previews of the first ready-made edition
"""
import argparse
import glob
import io
import json
import os
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone

import util

os.chdir(util.HERE)
SITE = os.path.abspath(os.path.join(util.HERE, "..", "site"))
KIT_FILES = ["util.py", "skycalc.py", "render.py", "backgrounds.py", "build.py", "gen_placeholders.py",
             "webgen.py", "brand.json", "data/image_manifest.json"]
FONT_NAMES = ["Geist-Light", "Geist-Regular", "Geist-Medium", "Geist-SemiBold", "Geist-Bold", "GeistMono-Regular",
              "GeistMono-Medium", "Fraunces-Display", "Fraunces-DisplayLight", "Fraunces-Title"]
MONTHS = ["Cover", "January", "February", "March", "April", "May", "June", "July", "August", "September",
          "October", "November", "December"]


def compact(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))


def editions():
    import localize
    doc = util.read_json("data/events_utc.json")
    sel = util.selection()
    targets = {int(k): (v["ra"], v["dec"]) for k, v in sel.items() if k != "cover" and v.get("ra")}
    cities = []
    for i, (code, c) in enumerate(sorted(localize.CITIES.items(), key=lambda kv: (kv[1]["region"], kv[1]["label"]))):
        loc = localize.localize(doc, code, targets)
        compact(os.path.join(SITE, "data", "editions", f"{code}.json"), loc)
        import holidays_data as HD
        cc, sub = HD.CITY_COUNTRY.get(code, (None, None))
        cities.append(dict(code=code, region=c["region"], label=c["label"], tzname=c["tzname"], tz=c["tz"],
                           city=c["city"][0], lat=c["city"][1], lon=c["city"][2], paper=c["paper"],
                           week_start=c["week_start"], print_edition=code in localize.EDITIONS,
                           country=cc, holiday_key=f"{cc}-{sub}" if sub else cc,
                           festivals=HD.CITY_FESTIVALS.get(code)))
        print(f"\r  editions {i + 1}/{len(localize.CITIES)} {code:7}", end="", flush=True)
    print()
    compact(os.path.join(SITE, "data", "cities.json"), cities)


# Every picture is served from this site in three sizes, so nothing depends on the
# observatories' servers when someone builds a calendar:
#   site/library/<id>.jpg   print copy: enough pixels for 300 dpi on the biggest page it can go
#                           on (an A3 or Tabloid cover, with bleed), at most 24 MB (Cloudflare
#                           serves files up to 25 MiB)
#   site/previews/<id>.jpg  1600 px, for the live page in "Make your own" and the picker
#   site/thumbs/<id>.jpg    640 px, for the picker grid and the filmstrip
COVER_FRAMES_300 = [(3579, 5031), (3375, 5175)]  # A3 and Tabloid with bleed, in pixels at 300 dpi
PRINT_DPI = 300  # --print-dpi: 240 roughly halves the repo with little visible loss
PRINT_MAX_BYTES = 24e6
PRINT_MAX_SIDE = 12000


def print_size(w, h, zoom=1.0):
    """The smallest size (keeping the aspect) that still fills either cover at 300 dpi."""
    a = w / h
    need_h = max(max(fh, fw / a) for fw, fh in COVER_FRAMES_300) * PRINT_DPI / 300 * max(1.0, zoom or 1.0)
    scale = min(1.0, need_h / h, PRINT_MAX_SIDE / max(w, h))
    return max(1, round(w * scale)), max(1, round(h * scale))


def save_under(im, out, limit, qualities=(92, 90, 88, 86, 84, 82, 80, 78)):
    """Save as JPEG at the best quality that fits under `limit` bytes; shrink 8% a step if needed."""
    from PIL import Image
    while True:
        for q in qualities:
            im.save(out, quality=q, optimize=True, progressive=True, subsampling=0 if q >= 90 else 2)
            if os.path.getsize(out) <= limit:
                return q
        im = im.resize((round(im.width * 0.92), round(im.height * 0.92)), Image.LANCZOS)


def fresh(dst, src):
    return os.path.exists(dst) and os.path.getmtime(dst) >= os.path.getmtime(src)


def site_copies(iid, src, zoom=1.0, quiet=False):
    """Write the print copy, preview and thumbnail for one picture from `src` (the full-size
    download, or the print copy itself when that's all there is). Skips files already newer."""
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    out, prv, tmb = (os.path.join(SITE, d, f"{iid}.jpg") for d in ("library", "previews", "thumbs"))
    for d in (out, prv, tmb):
        os.makedirs(os.path.dirname(d), exist_ok=True)
    same = os.path.abspath(src) == os.path.abspath(out)
    if (same or fresh(out, src)) and fresh(prv, src) and fresh(tmb, src):
        return out
    with Image.open(src) as im:
        size = print_size(im.width, im.height, zoom)
        if im.format == "JPEG" and not same:
            im.draft("RGB", size)  # decode at about the size needed: much faster and lighter
        im = im.convert("RGB")
        if not same and not fresh(out, src):
            big = im if size == im.size else im.resize(size, Image.LANCZOS)
            q = save_under(big, out + ".tmp.jpg", PRINT_MAX_BYTES)
            os.replace(out + ".tmp.jpg", out)
            if not quiet:
                print(f"  site   {iid:16} print {big.width}x{big.height} q{q} {os.path.getsize(out) / 1e6:5.1f} MB")
        if not fresh(prv, src):
            p_ = im.copy(); p_.thumbnail((1600, 1600), Image.LANCZOS)
            p_.save(prv, quality=82, optimize=True, progressive=True)
        if not fresh(tmb, src):
            t_ = im.copy(); t_.thumbnail((640, 640), Image.LANCZOS)
            t_.save(tmb, quality=80, optimize=True, progressive=True)
    return out


def library():
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    man = util.manifest()
    lib = util.library(man)
    for d in ("thumbs", "previews", "library"):
        os.makedirs(os.path.join(SITE, d), exist_ok=True)
    images, have, printed, total = {}, 0, 0, 0
    no_print = []
    for iid, o in lib.items():
        if o.get("source") == "own":
            continue  # your private photos stay out of the public site
        e = {k: o.get(k) for k in ("id", "source", "title", "credit", "license", "page", "pixels", "object", "catalog",
                                   "kind", "constellation", "distance", "ra", "dec", "fit", "focus", "zoom", "note",
                                   "rotate", "file_url", "thumb_url", "commons_title")}
        e = {k: v for k, v in e.items() if v is not None}
        e["renditions"] = list(o.get("downloads", {}))
        src = util.option_path(o)
        if os.path.exists(src):
            site_copies(iid, src, o.get("zoom") or 1.0)
            out, prv, tmb = (os.path.join(SITE, d, f"{iid}.jpg") for d in ("library", "previews", "thumbs"))
            with Image.open(out) as pim:
                e["orig_pixels"] = e.get("pixels")
                e["pixels"] = list(pim.size)  # what actually prints
            e["file"], e["preview"], e["thumb"] = f"library/{iid}.jpg", f"previews/{iid}.jpg", f"thumbs/{iid}.jpg"
            e.pop("pending", None)
            printed += 1
            have += 1
            total += os.path.getsize(out) + os.path.getsize(prv) + os.path.getsize(tmb)
        else:
            no_print.append(iid)
            alt = os.path.join(os.path.dirname(util.OPTIONS_DIR), "thumbs", f"{iid}.jpg")  # the sheet's thumbnail
            dst = os.path.join(SITE, "thumbs", f"{iid}.jpg")
            if os.path.exists(alt):
                if not fresh(dst, alt):
                    with Image.open(alt) as im:
                        im = im.convert("RGB"); im.thumbnail((640, 640))
                        im.save(dst, quality=80, optimize=True, progressive=True)
                e["thumb"] = f"thumbs/{iid}.jpg"
                have += 1
        images[iid] = e
    lic = util.GFDL_TEXT  # the GNU FDL text fetch_images.py saved, served for the licence page
    if os.path.exists(lic):
        os.makedirs(os.path.join(SITE, "data", "licences"), exist_ok=True)
        shutil.copyfile(lic, os.path.join(SITE, "data", "licences", os.path.basename(lic)))
    # drop files of pictures that left the library
    for d in ("library", "previews", "thumbs"):
        for f in glob.glob(os.path.join(SITE, d, "*.jpg")):
            if os.path.basename(f)[:-4] not in images:
                os.remove(f)
    # Commons photos whose licence fetch_images.py hasn't checked yet: the site checks them
    # itself in the visitor's browser (Commons answers cross-site requests) and drops any
    # whose licence or size doesn't pass.
    pend = 0
    for s in man:
        for o in s["options"]:
            if o.get("commons_title") and o["id"] not in images:
                images[o["id"]] = dict({k: o.get(k) for k in ("id", "source", "title", "credit", "page", "object",
                                                              "catalog", "kind", "constellation", "distance", "ra",
                                                              "dec", "fit", "focus", "zoom", "note", "rotate")},
                                       commons_title=o["commons_title"], pending=True, pixels=[0, 0], license="",
                                       renditions=[])
                pend += 1
    if pend:
        print(f"  library: {pend} Commons photos not checked here; the site checks their licence in the browser")

    def first(d):  # a list of defaults: the site takes the first one whose licence check passes
        ds = [x for x in (d if isinstance(d, list) else [d]) if x in images]
        return ds if len(ds) > 1 else (ds[0] if ds else (d[-1] if isinstance(d, list) else d))
    slots = [dict(slot=s["slot"], name=MONTHS[i], default=first(s["default"]),
                  options=[o["id"] for o in s["options"] if o["id"] in images]) for i, s in enumerate(man)]
    compact(os.path.join(SITE, "data", "library.json"), dict(slots=slots, images=images))
    print(f"  library: {len(images)} images; {printed} with print copies in site/ ({total / 1e6:.0f} MB), "
          f"{have} with thumbnails")
    if no_print:
        print(f"  !! {len(no_print)} pictures are not stored in site/library yet, so the site would have to fetch them "
              f"from the observatory (ESO refuses that: HTTP 525). Run fetch_images.py, or GitHub Actions -> "
              f"Pictures: {', '.join(no_print)}")


def fonts():
    os.makedirs(os.path.join(SITE, "fonts"), exist_ok=True)
    for f in FONT_NAMES:
        shutil.copyfile(os.path.join("fonts", f + ".ttf"), os.path.join(SITE, "fonts", f + ".ttf"))


def kit_zip():
    os.makedirs(os.path.join(SITE, "py"), exist_ok=True)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in KIT_FILES:
            z.write(f, f)
        lic = os.path.relpath(util.GFDL_TEXT, util.HERE)
        if os.path.exists(lic):  # printed as the last page when a GNU FDL photo is used
            z.write(lic, lic)
            os.makedirs(os.path.join(SITE, "data", "licences"), exist_ok=True)
            shutil.copyfile(lic, os.path.join(SITE, "data", "licences", os.path.basename(lic)))
        elif any(util.is_gfdl(o) for o in util.library().values()):
            print(f"  !! a GNU FDL photo is in the library but {lic} is missing; run fetch_images.py")
    with open(os.path.join(SITE, "py", "kit.zip"), "wb") as f:
        f.write(buf.getvalue())
    import hashlib
    kit_version = hashlib.sha256(buf.getvalue()).hexdigest()[:12]
    import reportlab
    ver = reportlab.Version
    whl = glob.glob(os.path.join(SITE, "py", f"reportlab-{ver}-*.whl"))
    if not whl:
        for old in glob.glob(os.path.join(SITE, "py", "reportlab-*.whl")):
            os.remove(old)
        r = subprocess.run([sys.executable, "-m", "pip", "download", f"reportlab=={ver}", "--no-deps",
                            "--only-binary=:all:", "--python-version", "3.12", "-d", os.path.join(SITE, "py")],
                           capture_output=True, text=True)
        whl = glob.glob(os.path.join(SITE, "py", f"reportlab-{ver}-*.whl"))
        if not whl:
            print("  !! could not download the ReportLab wheel; the site will install it from PyPI instead\n"
                  + r.stderr[-400:])
    return dict(reportlab=os.path.basename(whl[0]) if whl else f"reportlab=={ver}", kit=kit_version)


def holidays_files():
    """One JSON per country (and per subdivision a website city uses)."""
    import holidays_data as HD
    names = HD.country_names()
    out = os.path.join(SITE, "data", "holidays")
    os.makedirs(out, exist_ok=True)
    index = []
    keys = {(cc, None) for cc in names} | {v for v in HD.CITY_COUNTRY.values() if v[1]}
    for cc, sub in sorted(keys, key=lambda k: (names.get(k[0], k[0]), k[1] or "")):
        days = HD.holidays_for(cc, sub)
        if not days:
            continue
        key = f"{cc}-{sub}" if sub else cc
        name = names.get(cc, cc) + (f" ({sub})" if sub else "")
        compact(os.path.join(out, f"{key}.json"), dict(key=key, country=names.get(cc, cc), name=name, days=days))
        if not sub:
            index.append(dict(key=key, name=name))
    compact(os.path.join(SITE, "data", "holidays.json"), index)
    os.makedirs(os.path.join(SITE, "data", "festivals"), exist_ok=True)
    for key, f in HD.FESTIVALS.items():
        compact(os.path.join(SITE, "data", "festivals", f"{key}.json"), dict(key=key, **f))
    compact(os.path.join(SITE, "data", "festivals.json"),
            [dict(key=k, name=f["name"], country=f["country"], list=", ".join(sorted(set(
                n.split(" · ")[0] for n in f["days"].values())))) for k, f in HD.FESTIVALS.items()])
    print(f"  holidays: {len(index)} countries")


READY_HOLIDAYS = {"CET": "none"}  # a multi-country edition: no single country's holidays


def ready_made(codes, dpi, quality):
    """Build the downloadable calendars and their cover thumbnails."""
    import build
    import localize
    import render as R
    localize.run(codes)
    R.register_fonts()
    build.JPEG_QUALITY = quality
    cfg = util.read_json("brand.json")
    sel = util.selection()
    missing = [o["id"] for o in sel.values() if build.photo_for(o)[1]]
    if missing:
        print(f"  !! ready-made calendars use placeholder art for {missing}; run fetch_images.py first")
    out = os.path.join(SITE, "downloads")
    os.makedirs(out, exist_ok=True)
    for old in glob.glob(os.path.join(out, "*")):
        os.remove(old)
    items = []
    for code in codes:
        c = localize.CITIES[code]
        hol = build.holiday_set(code, READY_HOLIDAYS.get(code, "auto"))
        fest = build.festival_set(code, "auto")
        files = {}
        for fmt in ("wall", "desk"):
            name, tw, th, b = build.PAPERS[(c["paper"], fmt)]
            fn = f"DeepSpaceExplorer2027_{code}_{fmt.capitalize()}_{name.split()[0].replace('-', '')}.pdf"
            path = build.build_pdf(code, fmt, sel, dpi, cfg, out, fn=os.path.join(out, fn), holidays=hol,
                                   festivals=fest)
            mb = os.path.getsize(path) / 1e6
            if mb > 25:
                print(f"  !! {fn} is {mb:.1f} MB — over Cloudflare Pages' 25 MB file limit; use a lower --ready-dpi")
            files[fmt] = dict(file=f"downloads/{fn}", mb=round(mb, 1), paper=name)
            print(f"  ready {fn}  {mb:.1f} MB")
        thumb = os.path.join(out, f"{code}-cover.jpg")
        render_pages(os.path.join(SITE, files["wall"]["file"]), [0], 520, lambda i: thumb)
        items.append(dict(code=code, label=c["label"], city=c["city"][0], tzname=c["tzname"], region=c["region"],
                          holidays=hol[0] if hol else None, festivals=fest[0] if fest else None, cover=f"downloads/{code}-cover.jpg", files=files))
    compact(os.path.join(SITE, "data", "downloads.json"), dict(dpi=dpi, items=items))
    return items


def render_pages(pdf, pages, longest, name_for):
    try:
        import pypdfium2 as pdfium
    except ImportError:
        print("  (pip install pypdfium2 to make page previews)")
        return []
    doc = pdfium.PdfDocument(pdf)
    out = []
    for i in pages if pages is not None else range(len(doc)):
        pg = doc[i]
        w, h = pg.get_size()
        img = pg.render(scale=longest / max(w, h)).to_pil().convert("RGB")
        path = name_for(i)
        img.save(path, quality=80, optimize=True, progressive=True)
        out.append(os.path.basename(path))
    return out


def samples(items):
    """Page previews for the gallery, from the first ready-made edition."""
    if not items:
        return
    out = os.path.join(SITE, "sample")
    os.makedirs(out, exist_ok=True)
    for old in glob.glob(os.path.join(out, "*")):
        os.remove(old)
    first = items[0]
    pages = {}
    for fmt, longest in (("wall", 1100), ("desk", 1000)):
        pdf = os.path.join(SITE, first["files"][fmt]["file"])
        pages[fmt] = render_pages(pdf, None, longest, lambda i, f=fmt: os.path.join(out, f"{f}-{i + 1:02d}.jpg"))
    compact(os.path.join(out, "pages.json"), dict(edition=first["code"], pages=pages))
    print(f"  samples: {sum(len(v) for v in pages.values())} page images from {first['code']}")


def main(argv=None):
    util.utf8_stdio()
    util.require_tzdata()
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-ready", action="store_true", help="skip ready-made PDFs and page previews")
    ap.add_argument("--ready", nargs="*", default=["IN", "US-ET", "US-PT", "UK", "CET", "JP"],
                    help="editions to publish as ready-made downloads (first one feeds the page previews)")
    ap.add_argument("--ready-dpi", type=int, default=200)
    ap.add_argument("--print-dpi", type=int, default=300,
                    help="resolution of the print copies kept in site/library/ (300 = sharp on an A3 cover)")
    ap.add_argument("--ready-quality", type=int, default=84, help="JPEG quality of the photographs in those PDFs")
    a = ap.parse_args(argv)
    if not util.events_current():
        import astro_engine
        astro_engine.main()
    if not os.path.exists("fonts/Fraunces-Title.ttf"):
        import setup_fonts
        setup_fonts.main()
    global PRINT_DPI
    PRINT_DPI = a.print_dpi
    print(f"== building site data in {SITE}")
    fonts()
    info = kit_zip()
    library()
    editions()
    holidays_files()
    if not a.no_ready:
        samples(ready_made(a.ready, a.ready_dpi, a.ready_quality))
    info.update(fonts=FONT_NAMES, built=datetime.now(timezone.utc).isoformat(timespec="seconds"), year=2027)
    compact(os.path.join(SITE, "data", "build.json"), info)
    print("Done. Commit and push; Cloudflare deploys the site folder.")


if __name__ == "__main__":
    main()
