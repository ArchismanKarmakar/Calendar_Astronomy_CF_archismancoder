#!/usr/bin/env python3
"""
Download the calendar's image options (ESO, ESA/Hubble, ESA/Webb, NOIRLab) into
photos/options/<id>.jpg. Every option is CC BY 4.0; credits are printed on the pages
from data/image_manifest.json.

    python fetch_images.py                    # every option for every slot (28 images)
    python fetch_images.py --selected-only    # just the ones currently selected
    python fetch_images.py --only 05 08       # every option for some slots
    python fetch_images.py --prefer large     # biggest JPEG instead of the ~4K publication JPEG
    python fetch_images.py --max-mb 400       # allow very large downloads (default 250 MB)

Each image is tried rendition by rendition (only those its page offers), streamed
to a .part file, checked to decode as an image, then moved into place.
"""
import argparse
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

import util

UA = "DeepSpaceExplorer2027-calendar/1.0 (calendar build; https://archismancoder.com)"
lock = threading.Lock()


def say(msg):
    with lock:
        print(msg, flush=True)


def head_size(url):
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            if "image" not in r.headers.get("Content-Type", "image"):
                return None
            return int(r.headers.get("Content-Length") or 0)
    except urllib.error.HTTPError as e:
        if e.code in (403, 405):  # some CDNs refuse HEAD; let GET decide
            return 0
        return None
    except Exception:
        return None


def download(url, dest, label, total):
    tmp = dest + ".part"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    t0, got, next_report = time.time(), 0, 0.25
    with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:
        if "image" not in r.headers.get("Content-Type", ""):
            raise IOError(f"not an image ({r.headers.get('Content-Type')})")
        total = total or int(r.headers.get("Content-Length") or 0)
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            got += len(chunk)
            if total and got / total >= next_report and total > 20e6:
                say(f"   ..  {label:9} {got / 1e6:6.0f}/{total / 1e6:.0f} MB")
                next_report += 0.25
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    try:
        with Image.open(tmp) as im:
            im.verify()
            size = im.size
    except Exception as e:
        os.remove(tmp)
        raise IOError(f"downloaded file is not a valid image: {e}")
    os.replace(tmp, dest)
    return got, size, time.time() - t0


def fetch_option(opt, prefer, max_mb, force):
    dest = util.option_path(opt)
    if os.path.exists(dest) and not force:
        return opt, "present", None
    order = ["large", "publicationjpg", "screen"] if prefer == "large" else ["publicationjpg", "large", "screen"]
    errors = []
    tries = []
    for rend in order:  # a rendition may list mirror URLs (NOIRLab serves from two hosts)
        urls = opt["downloads"].get(rend) or []
        tries += [(rend, u) for u in ([urls] if isinstance(urls, str) else urls)]
    for rend, url in tries:
        size = head_size(url)
        if size is None:
            errors.append(f"{rend}: unavailable")
            continue
        if size and size > max_mb * 1e6:
            errors.append(f"{rend}: {size / 1e6:.0f} MB > --max-mb {max_mb}")
            continue
        try:
            say(f"  get  {opt['id']:9} {rend:14} {size / 1e6:6.1f} MB" if size else f"  get  {opt['id']:9} {rend}")
            got, px, dt = download(url, dest, opt["id"], size)
            if rend == "screen":
                errors.append("only the screen-size JPEG was available — too small for print")
            return opt, f"{rend} {px[0]}x{px[1]} {got / 1e6:.1f} MB in {dt:.0f}s", errors
        except Exception as e:
            errors.append(f"{rend}: {type(e).__name__}: {e}")
    return opt, None, errors


def resolve_commons(man):
    """Check the licence of each Wikimedia Commons option before it can be used."""
    import imgmeta
    res = util.commons_resolved()
    for s in man:
        for o in s["options"]:
            t = o.get("commons_title")
            if not t or o["id"] in res:
                continue
            try:
                m = imgmeta.commons_fetch(t)
            except Exception as e:
                print(f"  ?? {o['id']}: could not check {t} ({e}); will retry next run")
                continue
            res[o["id"]] = {k: m.get(k) for k in ("ok", "reason", "credit", "license", "page", "pixels", "downloads",
                                                   "file_url", "thumb_url", "note")}
            if m["ok"]:
                print(f"  ok   {o['id']}: {m['license']}, {m['pixels'][0]}x{m['pixels'][1]} px, credit: {m['credit']}")
            else:
                print(f"  skip {o['id']}: {m['reason']} (licence: {m['license'] or 'none'}) — "
                      f"ask the photographer for permission, then add it with choose_images.py --custom --share")
    util.write_json(util.RESOLVED, res)


def main(argv=None):
    util.utf8_stdio()
    ap = argparse.ArgumentParser()
    ap.add_argument("--selected-only", action="store_true")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--prefer", choices=["publication", "large"], default="publication")
    ap.add_argument("--max-mb", type=float, default=250)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args(argv)
    os.makedirs(util.OPTIONS_DIR, exist_ok=True)
    # adopt images saved by the first kit version (photos/<slot>.jpg)
    legacy = {"cover": "eso1208a", "01": "eso1006a", "02": "eso1238a", "03": "eso1126a", "04": "heic0506a",
              "05": "eso0007a", "06": "opo0840a", "07": "eso1403a", "08": "heic1501a", "09": "heic2501a",
              "11": "eso1205a", "12": "heic0515a"}
    for slot, iid in legacy.items():
        old = os.path.join(util.HERE, "photos", f"{slot}.jpg")
        new = os.path.join(util.OPTIONS_DIR, f"{iid}.jpg")
        if os.path.exists(old) and not os.path.exists(new):
            os.replace(old, new)
            print(f"  kept {iid:9} (moved from photos/{slot}.jpg)")
    man = util.manifest()
    resolve_commons(man)
    sel = util.selection(man)
    todo, seen = [], set()
    for s in man:
        if a.only and s["slot"] not in a.only:
            continue
        lib = util.library(man)  # Commons options carry their checked download links here
        opts = [sel[s["slot"]]] if a.selected_only else [lib[o["id"]] for o in s["options"] if o["id"] in lib] + [sel[s["slot"]]]
        for o in opts:
            if o["id"] not in seen and o.get("downloads"):  # your own photos have no download
                seen.add(o["id"])
                todo.append(o)
    if not a.selected_only and not a.only:
        for o in util.custom_images():  # images added with choose_images.py --add
            if o["id"] not in seen and o.get("downloads"):
                seen.add(o["id"])
                todo.append(o)
    print(f"{len(todo)} images to check ({'selected only' if a.selected_only else 'all options'})")
    failed = []
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = [ex.submit(fetch_option, o, a.prefer, a.max_mb, a.force) for o in todo]
        for f in as_completed(futs):
            opt, status, errs = f.result()
            if status is None:
                failed.append((opt, errs))
                say(f"  FAIL {opt['id']:9} " + "; ".join(errs))
            elif status != "present":
                say(f"  done {opt['id']:9} {status}" + (f"  (note: {'; '.join(errs)})" if errs else ""))
    sel_missing = [o for o in sel.values() if not os.path.exists(util.option_path(o))]
    print(f"\n{len(todo) - len(failed)}/{len(todo)} images present.")
    os.makedirs(util.OPTIONS_DIR, exist_ok=True)
    for opt, errs in failed:
        print(f"  {opt['id']}: save the JPEG from {opt['page']} as photos/options/{opt['id']}.jpg")
    try:
        import choose_images
        sheet = choose_images.make_sheet()
        print(f"Contact sheet of all options: {sheet}")
    except Exception as e:
        print(f"(contact sheet skipped: {e})")
    if sel_missing:
        print("Selected images still missing: " + ", ".join(f"{o['slot']}={o['id']}" for o in sel_missing))
        return 1
    print("All selected images present. Next:  python build.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
