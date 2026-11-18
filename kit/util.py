"""Shared helpers: UTF-8 everywhere (Windows defaults to cp1252), atomic JSON
writes (a crash can never leave a half-written file), tzdata check, and the
image selection (which of each slot's ESO / ESA-Hubble options is used)."""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.join(HERE, "data", "image_manifest.json")
SELECTION = os.path.join(HERE, "data", "selection.json")
OPTIONS_DIR = os.path.join(HERE, "photos", "options")


def utf8_stdio():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path, obj, **kw):
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            json.dump(obj, f, ensure_ascii=False, indent=1, **kw)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def file_hash(path):
    import hashlib
    with open(path, "rb") as f:
        return hashlib.sha256(f.read().replace(b"\r\n", b"\n")).hexdigest()[:16]


def events_current():
    """True if data/events_utc.json parses and was produced by this astro_engine.py."""
    path = os.path.join(HERE, "data", "events_utc.json")
    try:
        doc = read_json(path)
    except (OSError, ValueError):
        return False
    return doc.get("engine") == file_hash(os.path.join(HERE, "astro_engine.py"))


def require_tzdata():
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    try:
        ZoneInfo("Asia/Kolkata")
    except ZoneInfoNotFoundError:
        sys.exit("No time-zone database found (normal on Windows). Run:  pip install tzdata")


CUSTOM = os.path.join(HERE, "data", "custom_images.json")


def manifest():
    return read_json(MANIFEST)


def custom_images():
    """Images you added yourself: other ESO / ESA-Hubble IDs (choose_images.py --add)
    or your own photographs (choose_images.py --custom)."""
    return read_json(CUSTOM) if os.path.exists(CUSTOM) else []


RESOLVED = os.path.join(HERE, "data", "commons_resolved.json")


def commons_resolved():
    """Licence-checked details of Commons options (written by fetch_images.py)."""
    return read_json(RESOLVED) if os.path.exists(RESOLVED) else {}


def library(man=None):
    """Every image available to any page: all slots' options plus your own additions.
    Commons options appear only once their licence has been checked and accepted."""
    man = man or manifest()
    res = commons_resolved()
    out = {}
    for s in man:
        for o in s["options"]:
            if o.get("commons_title"):
                r = res.get(o["id"])
                if not r or not r.get("ok"):
                    continue
                o = dict(o, **{k: r[k] for k in ("credit", "license", "page", "pixels", "downloads", "file_url",
                                                  "thumb_url", "note") if r.get(k)})
            out.setdefault(o["id"], o)
    for o in custom_images():
        out[o["id"]] = o
    return out


def selection(man=None):
    """slot -> chosen image dict (with 'slot' added). Any image in the library can go on
    any page; unknown IDs fall back to the slot's default."""
    man = man or manifest()
    lib = library(man)
    chosen = read_json(SELECTION) if os.path.exists(SELECTION) else {}
    out = {}
    for s in man:
        defaults = s["default"] if isinstance(s["default"], list) else [s["default"]]
        # a list of defaults means "the first one that is available" (e.g. a Commons photo
        # whose licence check passed, else an observatory image)
        usable = [d for d in defaults if d in lib]
        fallback = next((d for d in usable if os.path.exists(option_path(lib[d]))), usable[0] if usable else None)
        pick = chosen.get(s["slot"], fallback)
        if pick not in lib:
            if s["slot"] in chosen:
                print(f"!! selection {s['slot']}={pick} is not in the image library; using {fallback}")
            pick = fallback
        out[s["slot"]] = dict(lib[pick], slot=s["slot"])
    return out


def option_path(opt):
    if opt.get("file"):  # your own photo, stored where you put it
        p = opt["file"] if os.path.isabs(opt["file"]) else os.path.join(HERE, opt["file"])
        return p
    return os.path.join(OPTIONS_DIR, f"{opt['id']}.jpg")
