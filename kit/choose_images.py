#!/usr/bin/env python3
"""
Pick which image each page uses. Any image can go on any page.

    python choose_images.py                    # show current selection + write the contact sheet
    python choose_images.py --set 05=heic2506a 08=eso1719a
    python choose_images.py --reset            # back to the defaults
    python build.py --compare 08               # see every option for a slot laid out on its page

Other ESO or ESA/Hubble images (reads title, credit, object and position from its page,
then downloads it):

    python choose_images.py --add eso1733a --slot 05
    python choose_images.py --add https://esahubble.org/images/heic1509a/ --slot 03
    python choose_images.py --add potw1011a --source esahubble     # potw IDs exist on both sites

Photos from Wikimedia Commons (amateur and professional astrophotographers who chose a
free licence). Licence and size are checked; NC, ND and GFDL-only files are refused:

    python choose_images.py --add-commons "https://en.wikipedia.org/wiki/Andromeda_Galaxy#/media/File:M31-Andromede-16-09-2023-Hamois.jpg" --slot 09
    python choose_images.py --check-commons          # test the files in data/commons_candidates.json
    python choose_images.py --scan-commons "Category:Andromeda Galaxy" --slot 09   # find more

Your own photograph (you hold the rights; the credit prints on the page):

    python choose_images.py --custom my_m42.jpg --credit "Jane Doe" --object "Orion Nebula" \
        --catalog M42 --ra 05:35:17 --dec -05:23:28 --slot 01

A photographer's image you are licensed to use (it also appears on the website's
picture list, and in the ready-made calendars if you select it):

    python choose_images.py --custom m31.jpg --share --credit "Photo: A. Photographer" \
        --license "Used with permission" --permission "Email from A. Photographer, 20 Nov 2026" \
        --object "Andromeda Galaxy" --catalog M31 --ra 00:42:44 --dec 41:16:09 --slot 09

The contact sheet (out/image_options.html) shows every downloaded option with its
credit and resolution; the selected one is outlined.
"""
import argparse
import html
import os
import re
import sys

import util

THUMBS = os.path.join(util.HERE, "photos", "thumbs")
SHEET = os.path.join(util.HERE, "out", "image_options.html")
MONTHS = ["Cover", "January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December"]


def thumb(opt):
    src = util.option_path(opt)
    if not os.path.exists(src):
        return None
    dst = os.path.join(THUMBS, f"{opt['id']}.jpg")
    try:
        if not os.path.exists(dst) or os.path.getmtime(dst) < os.path.getmtime(src):
            from PIL import Image
            Image.MAX_IMAGE_PIXELS = None
            os.makedirs(THUMBS, exist_ok=True)
            with Image.open(src) as im:
                if im.format == "JPEG":
                    im.draft("RGB", (900, 900))
                im = im.convert("RGB")
                im.thumbnail((900, 900))
                im.save(dst, quality=85)
    except Exception as e:  # a damaged file must not break the whole sheet
        print(f"  (no thumbnail for {opt['id']}: {e})")
        return None
    return dst


SRC = {"eso": "ESO", "esahubble": "ESA/Hubble", "esawebb": "ESA/Webb", "noirlab": "NOIRLab",
       "commons": "Wikimedia Commons", "licensed": "Photographer (licensed)", "own": "Your photo"}


def card(o, slot, on=False, remote_thumb=None, command=None):
    e = html.escape
    t = thumb(o) if not remote_thumb else None
    if t:
        img = f'<img src="../photos/thumbs/{e(o["id"])}.jpg" alt="" loading="lazy">'
    elif remote_thumb:
        img = f'<img src="{e(remote_thumb)}" alt="" loading="lazy" referrerpolicy="no-referrer">'
    else:
        img = (f'<div class="missing">not downloaded<br><code>python fetch_images.py --only {e(slot)}</code></div>'
               if o.get("downloads") or o.get("commons_title") else '<div class="missing">file missing</div>')
    px = o.get("pixels") or [0, 0]
    lic = o.get("license", "CC BY 4.0") or "—"
    cmd = command or f"python choose_images.py --set {slot}={o['id']}"
    link = f' · <a href="{e(o["page"])}" target="_blank" rel="noopener">page</a>' if o.get("page") else ""
    return f'''<figure class="{'on' if on else ''}">{img}
<figcaption><b>{e(o.get("object") or o.get("title") or o["id"])}</b>{' <span class="sel">selected</span>' if on else ''}
<span>{e(SRC.get(o.get("source"), o.get("source", "")))} · {e(o["id"])} · {px[0]}×{px[1]} px · {e(lic)}{link}</span>
<small>{e(o.get("credit", ""))}</small>
{f'<small class="note">{e(o["note"])}</small>' if o.get("note") else ''}
<code>{e(cmd)}</code></figcaption></figure>'''


def make_sheet():
    man = util.manifest()
    sel = util.selection(man)
    found = util.read_json(SCAN) if os.path.exists(SCAN) else {}
    rows = []
    lib = util.library(man)
    res = util.commons_resolved()
    for i, s in enumerate(man):
        cards = []
        for o in s["options"]:
            r = res.get(o["id"])
            if o.get("commons_title") and r and not r.get("ok"):
                o = dict(o, note=f"Not usable: {r.get('reason')} — ask the photographer for permission")
            cards.append(card(lib.get(o["id"], o), s["slot"], sel[s["slot"]]["id"] == o["id"]))
        cur = sel[s["slot"]]
        if cur["id"] not in {o["id"] for o in s["options"]}:
            cards.insert(0, card(cur, s["slot"], True))
        rows.append(f'<section><h2>{MONTHS[i]}</h2><div class="row">{"".join(cards)}</div></section>')
    extra = util.custom_images()
    if extra:
        rows.append('<section><h2>Your added images (any page)</h2><div class="row">'
                    + "".join(card(o, "05") for o in extra) + "</div></section>")
    if found:
        cards = []
        for slot, items in sorted(found.items()):
            for m in sorted(items.values(), key=lambda m: -max(m["pixels"])):
                small = (m.get("thumb_url") or "").replace("/7000px-", "/480px-")
                cmd = f'python choose_images.py --add-commons "{m["page"]}" --slot {slot if slot != "any" else "05"}'
                cards.append(card(m, slot, remote_thumb=small or None, command=cmd))
        rows.append('<section><h2>Wikimedia Commons: free to print (not added yet)</h2>'
                    '<p>Checked for a licence that allows selling prints and at least 4000 px. CC BY-SA photos make '
                    'their page CC BY-SA too.</p><div class="row">' + "".join(cards) + "</div></section>")
    page = f'''<!doctype html><meta charset="utf-8"><title>Image options</title>
<style>
body{{margin:0;padding:32px;background:#07090f;color:#f4f1ea;font:14px/1.45 system-ui,sans-serif}}
h1{{font-weight:600;margin:0 0 4px}} p{{color:#c9ccd6;margin:0 0 20px;max-width:80ch}}
h2{{font-size:13px;letter-spacing:.14em;text-transform:uppercase;color:#e9bc70;margin:28px 0 10px}}
.row{{display:flex;gap:16px;flex-wrap:wrap}}
figure{{margin:0;width:320px;background:#11141d;border:2px solid #222838;border-radius:10px;overflow:hidden}}
figure.on{{border-color:#e9bc70}}
img,.missing{{width:100%;height:210px;object-fit:cover;display:block;background:#1a1f2b}}
.missing{{display:flex;flex-direction:column;gap:8px;align-items:center;justify-content:center;color:#8a8fa3;text-align:center}}
figcaption{{padding:10px 12px;display:flex;flex-direction:column;gap:4px}}
span{{color:#c9ccd6}} small{{color:#9aa0b3}} .note{{color:#ffc46b}} a{{color:#8fc7ff}}
.sel{{color:#07090f;background:#e9bc70;border-radius:4px;padding:0 6px;font-size:11px}}
code{{font-size:11px;color:#8fc7ff;user-select:all;word-break:break-all}}
</style><h1>2027 calendar — image options</h1>
<p>Suggestions per page; any image can go on any page. Click a command to select it, paste it in your terminal,
then run <code>python build.py</code>.</p>
{"".join(rows)}'''
    os.makedirs(os.path.dirname(SHEET), exist_ok=True)
    with open(SHEET, "w", encoding="utf-8") as f:
        f.write(page)
    return SHEET


SCAN = os.path.join(util.HERE, "data", "commons_found.json")


def fill_target(meta, slot, man):
    """Copy object, catalogue and position from the page's usual target when the photo's
    title names the same object (e.g. a Commons 'M31 ...' photo for September)."""
    if not slot or meta.get("ra"):
        return meta
    s = next((x for x in man if x["slot"] == slot), None)
    if not s or slot == "cover":
        return meta
    ref = next(o for o in s["options"] if o["id"] == s["default"])
    norm = lambda t: re.sub(r"[^a-z0-9]", "", t.lower())
    title = norm(meta.get("title", "") + " " + meta.get("page", ""))
    keys = [norm(k) for k in re.split(r"[/,]", ref.get("catalog", "")) + [ref.get("object", "")] if k.strip()]
    keys += [norm(k).replace("messier", "m") for k in keys]
    if any(k and k in title.replace("messier", "m") for k in keys):
        for f in ("object", "catalog", "kind", "constellation", "distance", "ra", "dec", "rotate"):
            if not meta.get(f) and ref.get(f):
                meta[f] = ref[f]
    return meta


def add_custom(entry):
    lst = [o for o in util.custom_images() if o["id"] != entry["id"]] + [entry]
    util.write_json(util.CUSTOM, lst)


def main(argv=None):
    util.utf8_stdio()
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", nargs="*", default=[], metavar="SLOT=ID")
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--add", metavar="ID_OR_URL", help="another ESO or ESA/Hubble image")
    ap.add_argument("--source", choices=["eso", "esahubble", "esawebb"])
    ap.add_argument("--custom", metavar="FILE", help="your own photograph (JPEG/PNG/TIFF)")
    ap.add_argument("--add-commons", metavar="FILE_OR_URL", help="a Wikimedia Commons photo (licence-checked)")
    ap.add_argument("--check-commons", action="store_true", help="check data/commons_candidates.json")
    ap.add_argument("--scan-commons", metavar="CATEGORY", help="list usable photos in a Commons category")
    ap.add_argument("--slot", help="put the added image on this page (cover, 01..12)")
    for f in ("credit", "object", "catalog", "kind", "constellation", "distance", "ra", "dec", "title"):
        ap.add_argument(f"--{f}", default="")
    ap.add_argument("--license", default=None, help='default "CC BY 4.0" for --add, "" for --custom')
    ap.add_argument("--fit", choices=["cover", "band"])
    ap.add_argument("--rotate", help='"auto" to turn an elongated galaxy along the page, or degrees')
    ap.add_argument("--share", action="store_true",
                    help="licensed photographer image: include it in the website's picture list")
    ap.add_argument("--permission", default="", help="record of the licence or permission (kept in the data)")
    argv = list(sys.argv[1:] if argv is None else argv)
    for i in range(len(argv) - 1):  # allow --dec -05:23:28 (argparse would read it as an option)
        if argv[i] in ("--dec", "--ra") and argv[i + 1].startswith("-"):
            argv[i], argv[i + 1] = f"{argv[i]}={argv[i + 1]}", None
    a = ap.parse_args([x for x in argv if x is not None])
    man = util.manifest()
    chosen = {} if a.reset else (util.read_json(util.SELECTION) if os.path.exists(util.SELECTION) else {})
    slots = [s["slot"] for s in man]
    new_id = None
    if a.add:
        import imgmeta
        print(f"reading {a.add} ...")
        try:
            meta = imgmeta.fetch(a.add, a.source)
        except Exception as e:
            sys.exit(f"could not read that image's page: {e}")
        for f in ("credit", "object", "catalog", "kind", "constellation", "distance", "ra", "dec", "title"):
            if getattr(a, f):
                meta[f] = getattr(a, f)
        if a.fit:
            meta["fit"] = a.fit
        if a.license is not None:
            meta["license"] = a.license
        meta["slot"] = "library"
        add_custom(meta)
        new_id = meta["id"]
        print(f"added {new_id}: {meta['title']}\n  credit: {meta['credit']}\n  object: {meta['object']} "
              f"{meta['catalog']} · {meta['kind']} · RA {meta['ra'] or '?'} Dec {meta['dec'] or '?'}\n"
              f"  Check the credit against {meta['page']} — it must be printed in full.")
        import fetch_images
        _, status, errs = fetch_images.fetch_option(meta, "publication", 400, False)
        print(f"  download: {status or 'FAILED'}" + (f" ({'; '.join(errs)})" if errs else ""))
    if a.add_commons:
        import imgmeta
        try:
            meta = imgmeta.commons_fetch(a.add_commons)
        except Exception as e:
            sys.exit(f"could not read that Commons file: {e}")
        if not meta["ok"]:
            sys.exit(f"{meta['page'] or a.add_commons}: not usable — {meta['reason']} (licence: {meta['license'] or '?'})")
        fill_target(meta, a.slot, man)
        for f in ("credit", "object", "catalog", "kind", "constellation", "distance", "ra", "dec", "title"):
            if getattr(a, f):
                meta[f] = getattr(a, f)
        if a.fit:
            meta["fit"] = a.fit
        meta["rotate"] = a.rotate or meta.get("rotate")
        meta["slot"] = "library"
        for k in ("ok", "reason", "thumb_url"):
            meta.pop(k, None)
        add_custom(meta)
        new_id = meta["id"]
        print(f"added {new_id}: {meta['title']} ({meta['pixels'][0]}x{meta['pixels'][1]} px)\n"
              f"  credit: {meta['credit']} · {meta['license']}\n  object: {meta['object'] or '(set with --object)'} "
              f"RA {meta['ra'] or '?'} Dec {meta['dec'] or '?'}" + (f"\n  note: {meta['note']}" if meta["note"] else ""))
        import fetch_images
        _, status, errs = fetch_images.fetch_option(meta, "large", 400, False)
        print(f"  download: {status or 'FAILED'}" + (f" ({'; '.join(errs)})" if errs else ""))
    if a.check_commons or a.scan_commons:
        import imgmeta
        found = util.read_json(SCAN) if os.path.exists(SCAN) else {}
        jobs = []
        if a.check_commons:
            cand = util.read_json(os.path.join(util.HERE, "data", "commons_candidates.json"))
            jobs += [(slot, "file", t) for slot, ts in cand.get("files", {}).items() for t in ts]
        if a.scan_commons:
            jobs.append(((a.slot or "any").zfill(2) if (a.slot or "").isdigit() else (a.slot or "any"), "cat", a.scan_commons))
        for slot, kind, what in jobs:
            try:
                metas = [imgmeta.commons_fetch(what)] if kind == "file" else imgmeta.commons_scan(what)
            except Exception as e:
                print(f"  ?? {what}: {e}")
                continue
            for m in metas:
                fill_target(m, slot if slot != "any" else None, man)
                mark = "ok " if m["ok"] else "-- "
                if kind == "file" or m["ok"]:
                    print(f"  {mark}{slot:5} {m['pixels'][0]:>6}x{m['pixels'][1]:<6} {m['license'][:14]:14} "
                          f"{m['title'][:48]:48} {'' if m['ok'] else m['reason']}")
                if m["ok"]:
                    found.setdefault(slot, {})[m["page"]] = m
        util.write_json(SCAN, found)
        print(f"\nUsable photos are listed with their add commands in {make_sheet()}")
        return
    if a.custom:
        if not a.credit or not a.object:
            sys.exit("--custom needs at least --credit and --object")
        import re
        import shutil
        from PIL import Image
        Image.MAX_IMAGE_PIXELS = None
        with Image.open(a.custom) as im:
            px = list(im.size)
        slug = re.sub(r"[^a-z0-9]+", "-", a.object.lower()).strip("-")[:30] or "photo"
        new_id = f"{'lic' if a.share else 'own'}-{slug}"
        if a.share and not (a.license or a.permission):
            sys.exit("--share needs --license or --permission: record how you're allowed to use this photo")
        os.makedirs(os.path.join(util.HERE, "photos", "custom"), exist_ok=True)
        dest = os.path.join("photos", "custom", new_id + os.path.splitext(a.custom)[1].lower())
        shutil.copyfile(a.custom, os.path.join(util.HERE, dest))
        add_custom(dict(id=new_id, source="licensed" if a.share else "own", title=a.title or a.object, credit=a.credit,
                        permission=a.permission, rotate=a.rotate or None,
                        license=a.license if a.license is not None else "", page="", pixels=px, downloads={},
                        file=dest.replace(os.sep, "/"), object=a.object, catalog=a.catalog, kind=a.kind,
                        constellation=a.constellation, distance=a.distance, ra=a.ra, dec=a.dec,
                        fit=a.fit or ("band" if px[0] / px[1] > 2.6 else "cover"), focus=None, zoom=1.0, note="",
                        slot="library"))
        print(f"added your photo as {new_id} ({px[0]}x{px[1]} px)")
    if new_id and a.slot:
        slot = a.slot.zfill(2) if a.slot.isdigit() else a.slot
        if slot not in slots:
            sys.exit(f"--slot must be one of {slots}")
        chosen[slot] = new_id
    lib = util.library(man)
    for item in a.set:
        slot, _, iid = item.partition("=")
        slot = slot.zfill(2) if slot.isdigit() else slot
        if slot not in slots:
            sys.exit(f"'{item}': pages are {slots}")
        if iid not in lib:
            sys.exit(f"'{item}': {iid} is not in the library — add it first with --add {iid}")
        chosen[slot] = iid
    if a.set or a.reset or (new_id and a.slot):
        util.write_json(util.SELECTION, chosen)
    sel = util.selection(man)
    for i, s in enumerate(man):
        o = sel[s["slot"]]
        have = "ok " if os.path.exists(util.option_path(o)) else "-- "
        alts = ", ".join(x["id"] for x in s["options"] if x["id"] != o["id"])
        print(f"{have}{MONTHS[i]:10} {o['id']:16} {o['object'][:34]:34} (suggested: {alts})")
    extra = util.custom_images()
    if extra:
        print("Your added images: " + ", ".join(o["id"] for o in extra))
    print("\nContact sheet:", make_sheet())


if __name__ == "__main__":
    main()
