#!/usr/bin/env python3
"""
Download the calendar's pictures (ESO, ESA/Hubble, ESA/Webb, NOIRLab, Wikimedia Commons)
and keep them with the website:

  photos/options/<id>.jpg   the full-size download (not in git: some are over 100 MB)
  ../site/library/<id>.jpg  print copy, 300 dpi on an A3/Tabloid cover, at most 24 MB  -> commit
  ../site/previews/<id>.jpg 1600 px                                                   -> commit
  ../site/thumbs/<id>.jpg   640 px                                                    -> commit
  ../site/data/library.json the site's picture list                                   -> commit

A picture whose print copy is already in the repo is never downloaded again, and the
kit prints from that copy when the full-size file isn't here.

    python fetch_images.py                    # every picture in the library
    python fetch_images.py --selected-only    # just the ones currently selected
    python fetch_images.py --only 05 08       # every option for some slots
    python fetch_images.py --force            # download again even if a copy exists
    python fetch_images.py --drop-originals   # delete full-size files after copying (saves disk)

GitHub can do all of this for you: Actions -> "Pictures" -> Run workflow (see README).
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
    dest = util.original_path(opt)
    if not force and (os.path.exists(dest) or os.path.exists(util.site_copy_path(opt))):
        return opt, "present", None  # already downloaded, or its print copy is already in the repo
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
            if not t or (res.get(o["id"]) or {}).get("ok"):
                continue  # accepted before; refused ones are checked again (rules or licences change)
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
    if any("GFDL" in (r.get("license") or "").upper() for r in res.values() if r.get("ok")):
        gfdl_text()


GFDL_URL = "https://www.gnu.org/licenses/fdl-1.3.txt"


def gfdl_text():
    """The GNU FDL 1.3 text, printed as the calendar's last page when a GFDL photo is used."""
    dest = util.GFDL_TEXT
    if os.path.exists(dest) and os.path.getsize(dest) > 15000:
        return
    import urllib.request
    try:
        req = urllib.request.Request(GFDL_URL, headers={"User-Agent": "DeepSpaceExplorer2027-calendar/1.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            txt = r.read().decode("utf-8")
        if "GNU Free Documentation License" not in txt:
            raise ValueError("unexpected content")
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "w", encoding="utf-8") as f:
            f.write(txt)
        print(f"  ok   GNU FDL 1.3 text saved to {os.path.relpath(dest, util.HERE)}")
    except Exception as e:
        print(f"  !! could not download the GNU FDL text ({e}). Save {GFDL_URL} as "
              f"{os.path.relpath(dest, util.HERE)} before building with a GFDL photo.")


def main(argv=None):
    util.utf8_stdio()
    ap = argparse.ArgumentParser()
    ap.add_argument("--selected-only", action="store_true")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--prefer", choices=["publication", "large"], default="publication")
    ap.add_argument("--max-mb", type=float, default=250)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--no-site", action="store_true",
                    help="don't write the website copies (site/library, previews, thumbs)")
    ap.add_argument("--drop-originals", action="store_true",
                    help="delete each full-size download once its website copies exist (saves disk; used on GitHub)")
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
    site = None
    if not a.no_site:
        import make_site as site  # the website copies are made here, one picture at a time
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = [ex.submit(fetch_option, o, a.prefer, a.max_mb, a.force) for o in todo]
        for f in as_completed(futs):
            opt, status, errs = f.result()
            if status is None:
                failed.append((opt, errs))
                say(f"  FAIL {opt['id']:9} " + "; ".join(errs))
                continue
            if status != "present":
                say(f"  done {opt['id']:9} {status}" + (f"  (note: {'; '.join(errs)})" if errs else ""))
            orig = util.original_path(opt)
            if site and os.path.exists(orig):
                try:
                    site.site_copies(opt["id"], orig, opt.get("zoom") or 1.0)
                except Exception as e:
                    say(f"  !!   {opt['id']:9} website copy failed: {e}")
                    continue
                if a.drop_originals:
                    os.remove(orig)
    if site:
        print("\n== website copies (site/library, site/previews, site/thumbs) and site/data/library.json")
        site.library()
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
