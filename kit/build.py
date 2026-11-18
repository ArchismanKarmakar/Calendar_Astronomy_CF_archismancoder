#!/usr/bin/env python3
"""
One command builds everything:

    pip install -r requirements.txt
    python build.py --fetch            # fonts + data + ESO/ESA-Hubble images + all PDFs

Other forms:
    python build.py                     # rebuild PDFs (data/fonts set up automatically if missing)
    python build.py --editions IN UK --formats wall
    python build.py --compare 08        # one page per image option for August -> out/compare_08.pdf
    python build.py --dpi 150           # quick proofs

Pages whose selected image isn't downloaded yet use placeholder art and print
PLACEHOLDER in red in the credit line, so a draft can't be shipped by accident.
"""
import argparse
import os
import sys
import time

import util

os.chdir(util.HERE)

PAPERS = {
    ("ISO", "wall"): ("A3", 841.89, 1190.55, 8.5),
    ("ISO", "desk"): ("A5 landscape", 595.28, 419.53, 8.5),
    ("US", "wall"): ("Tabloid 11x17in", 792.0, 1224.0, 9.0),
    ("US", "desk"): ("Half-letter 8.5x5.5in landscape", 612.0, 396.0, 9.0),
}
JPEG_QUALITY = 90  # backgrounds; make_site.py lowers it a little for the downloadable PDFs
LAYOUT = {
    "wall": dict(photo_frac=0.50, grid_bottom=0.852, hl_bottom=0.955),
    "desk": dict(panel_frac=0.46, grid_bottom=0.735, desk_items=7),
}


def ensure_setup(codes=None):
    if not os.path.exists("fonts/Fraunces-Title.ttf"):
        print("== fonts (first run)")
        import setup_fonts
        setup_fonts.main()
    if not util.events_current():  # missing, corrupt, or made by a different engine version
        print("== computing 2027 events")
        import astro_engine
        astro_engine.main()
    print("== localising editions")
    import localize
    localize.run(codes)


def photo_for(opt):
    p = util.option_path(opt)
    if os.path.exists(p):
        return p, False
    ph = f"photos/_placeholder/{opt['slot']}.jpg"
    if not os.path.exists(ph):
        import gen_placeholders
        gen_placeholders.make(opt["slot"], 2027 + list(gen_placeholders.PAL).index(opt["slot"]) * 17)
    return ph, True


def px(pt, dpi):
    return int(round(pt / 72 * dpi))


def background(paper, fmt, opt, dpi, kind=None):
    import backgrounds as bg
    name, tw, th, b = PAPERS[(paper, fmt)]
    W, H = px(tw + 2 * b, dpi), px(th + 2 * b, dpi)
    src, ph = photo_for(opt)
    kind = kind or ("cover" if opt["slot"] == "cover" else "month")
    os.makedirs("build/bg", exist_ok=True)
    # the key includes a hash of backgrounds.py + the option's layout fields, so
    # changing the code or the manifest never reuses a stale cached background
    import hashlib
    key = hashlib.sha1((util.file_hash(bg.__file__) + repr((opt.get("fit"), opt.get("focus"), opt.get("zoom"), opt.get("rotate"))))
                       .encode()).hexdigest()[:8]
    path = f"build/bg/{paper}_{fmt}_{kind}_{opt['slot']}_{opt['id']}_{dpi}_{key}q{JPEG_QUALITY}{'_ph' if ph else ''}.jpg"
    if os.path.exists(path) and os.path.getmtime(path) >= os.path.getmtime(src):
        return path, ph
    f = opt.get("focus")          # None -> automatic subject detection
    f = tuple(f) if f else None
    z = float(opt.get("zoom") or 1.0)
    if kind == "plate":
        img = bg.dark_plate(src, W, H)
    elif kind == "cover":
        rot = opt.get("rotate")
        img = (bg.full_bleed(src, W, H, f, rotate=rot) if fmt == "wall"
               else bg.full_bleed(src, W, H, f, top=0.35, bottom=0.85, bottom_from=0.45, desk=True, rotate=rot))
    elif fmt == "wall":
        img = bg.wall_month(src, W, H, px(b + th * LAYOUT["wall"]["photo_frac"], dpi), opt["fit"], f, z, opt.get("rotate"))
    else:
        img = bg.desk_month(src, W, H, px(b + tw * LAYOUT["desk"]["panel_frac"], dpi), opt["fit"], f, z, opt.get("rotate"))
    img.save(path, quality=JPEG_QUALITY, subsampling=0, dpi=(dpi, dpi))
    if not ph:  # print-resolution sanity check
        from PIL import Image
        Image.MAX_IMAGE_PIXELS = None
        with Image.open(src) as im:
            sw = im.size[0]
        zone_w_in = (tw if fmt == "wall" else tw * LAYOUT["desk"]["panel_frac"]) / 72
        eff = sw / zone_w_in
        if eff < 200:
            print(f"   note: {opt['id']} prints at ~{eff:.0f} dpi across the {fmt} photo zone")
    return path, ph


def with_rotation_flag(opt, fmt, paper, cover=False):
    """Mark images the background actually rotated, so the credit can say so (CC BY)."""
    if not opt.get("rotate"):
        return opt
    import backgrounds as bg
    src, ph = photo_for(opt)
    if ph:
        return opt
    name, tw, th, b = PAPERS[(paper, fmt)]
    if cover:
        zw, zh = tw, th
    elif fmt == "wall":
        zw, zh = tw, th * LAYOUT["wall"]["photo_frac"]
    else:
        zw, zh = tw * LAYOUT["desk"]["panel_frac"], th
    try:
        ang = bg.rotation_for(src, zw, zh, opt["rotate"])
    except Exception:
        ang = 0.0
    return dict(opt, rotated=bool(ang))


def build_pdf(code, fmt, sel, dpi, cfg, outdir, months=range(1, 13), extra_pages=True, fn=None, page_label=None,
              parts=None, progress=None, holidays=None, festivals=None):
    """parts: any of cover, legend, months, year (default: all, or just months when
    extra_pages is False). progress(done, total, label) is called before each page."""
    import render as R
    loc = util.read_json(f"data/edition_{code}.json")
    if holidays:  # (country name, {date: name})
        loc["holiday_country"], loc["holidays"] = holidays
    if festivals:  # (set name, {date: name})
        loc["festival_name"], loc["festivals"] = festivals
    ed = loc["edition"]
    paper = ed["paper"]
    name, tw, th, b = PAPERS[(paper, fmt)]
    lay = dict(LAYOUT[fmt], **cfg)
    parts = set(parts or (("cover", "legend", "months", "year") if extra_pages else ("months",)))
    fn = fn or f"{outdir}/NightSky2027_{code}_{fmt.capitalize()}_{name.split()[0].replace('-', '')}.pdf"
    os.makedirs(os.path.dirname(fn) or ".", exist_ok=True)
    c = R.new_canvas(fn, tw, th, b, f"{cfg['title']} {loc['year']} — {ed['label']} edition ({fmt})", cfg["brand"])
    credits = [sel[k] for k in ["cover"] + [f"{m:02d}" for m in range(1, 13)]]
    month_pages = [(m, opt) for m in (months if "months" in parts else [])
                   for opt in (sel[f"{m:02d}"] if isinstance(sel[f"{m:02d}"], list) else [sel[f"{m:02d}"]])]
    total = len(parts & {"cover", "legend", "year"}) + len(month_pages)
    done = [0]

    def page(label):
        if progress:
            progress(done[0], total, label)
        done[0] += 1
        R.set_boxes(c, tw, th, b)
        return R.Page(c, tw, th, b)

    plate = None
    if "cover" in parts:
        p = page("cover")
        cbg, cph = background(paper, fmt, sel["cover"], dpi)
        R.cover(c, p, lay, loc, with_rotation_flag(sel["cover"], fmt, paper, cover=True), cph, cbg, desk=fmt == "desk")
        c.showPage()
    if "legend" in parts or "year" in parts:
        plate, _ = background(paper, fmt, sel["cover"], dpi, kind="plate")
    if "legend" in parts:
        R.legend(c, page("how to read"), lay, loc, credits, plate, desk=fmt == "desk")
        c.showPage()
    for m, opt in month_pages:
        p = page(f"month {m}")
        mbg, mph = background(paper, fmt, opt, dpi)
        opt = with_rotation_flag(opt, fmt, paper)
        fn_ = R.wall_month if fmt == "wall" else R.desk_month
        fn_(c, p, lay, loc, m, opt, mph, mbg, page_label or str(m + 2))
        c.showPage()
    if "year" in parts:
        R.year_page(c, page("year at a glance"), lay, loc, plate, desk=fmt == "desk")
        c.showPage()
    if progress:
        progress(total, total, "saving PDF")
    c.save()
    return fn


def holiday_set(code, choice):
    """(country name, {date: name}) or None."""
    if not choice or choice.lower() == "none":
        return None
    import holidays_data as HD
    try:
        if choice.lower() == "auto":
            cc, days = HD.for_city(code)
        else:
            cc, days = choice.upper(), HD.holidays_for(choice.upper())
    except ImportError:
        print("   (pip install holidays to add public holidays)")
        return None
    if not days:
        if choice.lower() != "auto":
            print(f"   no holiday data for {choice}")
        return None
    return HD.country_names().get(cc, cc), days


def festival_set(code, choice):
    if not choice or choice.lower() == "none":
        return None
    import holidays_data as HD
    return HD.festivals_for(code if choice.lower() == "auto" else choice.lower())


def main(argv=None):
    util.utf8_stdio()
    from localize import EDITIONS, CITIES
    ap = argparse.ArgumentParser(epilog="Cities: " + " ".join(sorted(CITIES)))
    ap.add_argument("--editions", nargs="*", default=list(EDITIONS),
                    help="print editions by default; any city code works (see the list below)")
    ap.add_argument("--formats", nargs="*", default=["wall", "desk"])
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--fetch", action="store_true", help="download the image options first")
    ap.add_argument("--festivals", default="auto", metavar="auto|none|bengali",
                    help="regional festivals in their own colour: the edition's default set (auto), none, or a set name")
    ap.add_argument("--holidays", default="auto", metavar="auto|none|CC",
                    help="public holidays: the edition's country (auto), none, or a country code such as IN or GB")
    ap.add_argument("--compare", metavar="SLOT", help="e.g. 08 — one page per image option")
    a = ap.parse_args(argv)
    util.require_tzdata()
    bad = [c for c in a.editions if c not in CITIES]
    if bad:
        sys.exit(f"unknown edition(s) {bad}; choose from: {' '.join(sorted(CITIES))}")
    ensure_setup(a.editions)
    if a.fetch:
        import fetch_images
        print("== fetching images")
        fetch_images.main([])
    import render as R
    R.register_fonts()
    cfg = util.read_json("brand.json")
    man = util.manifest()
    sel = util.selection(man)

    if a.compare:
        slot = a.compare.zfill(2)
        s = next(x for x in man if x["slot"] == slot)
        if slot == "cover":
            sys.exit("--compare works for month slots 01..12")
        sel2 = dict(sel)
        sel2[slot] = [dict(o, slot=slot) for o in s["options"]]
        code = a.editions[0] if len(a.editions) == 1 else "UK"
        fn = build_pdf(code, a.formats[0], sel2, min(a.dpi, 150), cfg, "out", months=[int(slot)],
                       extra_pages=False, fn=f"out/compare_{slot}.pdf", page_label="option")
        print(f"{fn}: pages are options " + ", ".join(o["id"] for o in s["options"]))
        return

    missing = [f"{k}={o['id']}" for k, o in sel.items() if photo_for(o)[1]]
    if missing:
        print(f"!! {len(missing)} selected images not downloaded ({', '.join(missing)}) — PLACEHOLDER art used. "
              f"Run: python fetch_images.py")
    for code in a.editions:
        os.makedirs(f"out/{code}", exist_ok=True)
        for fmt in a.formats:
            t0 = time.time()
            fn = build_pdf(code, fmt, sel, a.dpi, cfg, f"out/{code}", holidays=holiday_set(code, a.holidays),
                           festivals=festival_set(code, a.festivals))
            print(f"  {fn}  {os.path.getsize(fn) / 1e6:.1f} MB  ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
