"""
Read an image's details (title, credit, size, object, coordinates, download sizes)
from its ESO or ESA/Hubble page, so any of their images can go in the calendar.

The website's Cloudflare function (functions/api/meta.js) uses the same rules, so the
two stay in step. Pages are parsed as plain text with labels ("Credit:",
"Position (RA):" ...), which is robust to small layout changes. Always read the credit
back before printing: it must be reproduced in full.
"""
import html as _html
import re

SOURCES = {
    "eso": dict(page="https://www.eso.org/public/images/{id}/", cdn="https://cdn.eso.org/images/{r}/{id}.jpg",
                name="ESO"),
    "esahubble": dict(page="https://esahubble.org/images/{id}/",
                      cdn="https://cdn.esahubble.org/archives/images/{r}/{id}.jpg", name="ESA/Hubble"),
    "esawebb": dict(page="https://esawebb.org/images/{id}/",
                    cdn="https://cdn.esawebb.org/archives/images/{r}/{id}.jpg", name="ESA/Webb"),
}
RENDITIONS = ["publicationjpg", "large", "screen", "wallpaper5", "wallpaper4"]
ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{2,40}$")


def guess_source(iid):
    """ESA/Hubble IDs: heic, opo, potw (ESO uses potw too — pass --source to be sure);
    ESA/Webb IDs: weic, potm."""
    if re.match(r"^(weic|potm)\d", iid):
        return "esawebb"
    return "esahubble" if re.match(r"^(heic|opo|potw|ann|sci)\d", iid) else "eso"


def parse_id(text):
    """Accept an ID or a page / CDN URL; return (source or None, id)."""
    t = text.strip().rstrip("/")
    m = re.search(r"(eso\.org|esahubble\.org|spacetelescope\.org|esawebb\.org)/(?:public/)?(?:archives/)?images/"
                  r"(?:[a-z0-9_]+/)?([a-z0-9_-]+?)(?:\.(?:jpg|tif|png))?$", t, re.I)
    if m:
        host = m.group(1).lower()
        src = "esawebb" if "esawebb" in host else ("eso" if host == "eso.org" else "esahubble")
        return src, m.group(2).lower()
    return None, t.lower()


def html_to_lines(page):
    page = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", page)
    page = re.sub(r"(?i)<br\s*/?>", "\n", page)
    page = re.sub(r"(?i)</?(p|div|tr|td|th|li|ul|h[1-6]|table|section|dt|dd|span class=\"title\")[^>]*>", "\n", page)
    page = re.sub(r"<[^>]+>", "", page)  # inline tags (links, emphasis) join their text
    lines = [re.sub(r"\s+", " ", _html.unescape(x)).strip() for x in page.split("\n")]
    return [x for x in lines if x]


def label_value(lines, label, nth=0):
    """Value after a 'Label:' line (same line or the next line)."""
    found = 0
    lab = label.lower().rstrip(":")
    for i, ln in enumerate(lines):
        low = ln.lower()
        if low == lab + ":" or low == lab or low.startswith(lab + ": ") or low.startswith(lab + ":"):
            if found < nth:
                found += 1
                continue
            rest = ln[len(lab) + 1:].strip(" :") if len(ln) > len(lab) + 1 else ""
            if rest:
                return rest
            return lines[i + 1] if i + 1 < len(lines) else ""
    return ""


STOP = ("about the image", "about the object", "image formats", "id:", "related", "usage of", "coordinates",
        "release date", "wallpapers", "colours & filters", "mounted image", "zoomable")


def credit_from(lines):
    for i, ln in enumerate(lines):
        if ln.lower().startswith("credit"):
            rest = re.sub(r"(?i)^credits?\s*:?\s*", "", ln).strip()
            parts = [rest] if rest else []
            for nxt in lines[i + 1:i + 6]:
                if any(nxt.lower().startswith(s) for s in STOP):
                    break
                parts.append(nxt)
                if len(" ".join(parts)) > 30 and not nxt.endswith((",", "/", "and", "&")):
                    break
            return re.sub(r"\s+", " ", " ".join(parts)).strip()[:400]
    return ""


def _kind(t):
    skip = {"milky way", "local universe", "early universe", "type", "appearance", "solar system", "unspecified",
            "illustration", "x - illustrations"}
    toks = [x.strip() for x in t.split(":") if x.strip() and x.strip().lower() not in skip]
    if not toks:
        return ""
    if len(toks) >= 2:
        adj = ("spiral", "elliptical", "irregular", "barred", "lenticular", "planetary", "emission", "reflection",
               "dark", "globular", "open", "interacting", "dwarf")
        if toks[-1].lower() in adj:
            return f"{toks[-1]} {toks[0].lower()}"
        return f"{toks[0]} ({toks[-1].lower()})"
    return toks[0]


def _coord(v):
    v = v.replace("°", " ").replace("'", " ").replace('"', " ").replace("h", " ").replace("m", " ").replace("s", " ")
    p = v.split()
    if len(p) < 2:
        return ""
    try:
        a, b, c = p[0], float(p[1]), float(p[2]) if len(p) > 2 else 0.0
    except ValueError:
        return ""
    if not re.match(r"^[+-]?\d+$", a):
        return ""
    return f"{a}:{int(b):02d}:{min(59, int(round(c))):02d}"


def parse_page(page, iid, source):
    lines = html_to_lines(page)
    title = ""
    m = re.search(r'(?is)<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)', page)
    if m:
        title = _html.unescape(m.group(1)).strip()
    if not title:
        m = re.search(r"(?is)<h1[^>]*>(.*?)</h1>", page) or re.search(r"(?is)<title>(.*?)</title>", page)
        title = re.sub(r"<[^>]+>|\s*\|.*$", "", _html.unescape(m.group(1))).strip() if m else iid
    size = label_value(lines, "Size")
    px = [int(x) for x in re.findall(r"\d+", size.replace(",", ""))[:2]] if size else []
    name = label_value(lines, "Name")
    names = [x.strip() for x in re.split(r",", name) if x.strip()] if name else []
    cat = [x for x in names if re.match(r"(?i)^(NGC|IC|M|Messier|Sh2|RCW|LBN|LDN|Abell|Arp|ESO|Barnard|B|Cederblad|vdB|"
                                        r"Gum|Collinder|Melotte|Hen|PGC|UGC|HD|HR)[\s-]?\d", x)]
    obj = next((x for x in names if x not in cat), names[0] if names else title)
    rends = sorted(set(re.findall(r"/images/([a-z0-9_]+)/" + re.escape(iid) + r"\.jpg", page)),
                   key=lambda r: RENDITIONS.index(r) if r in RENDITIONS else 99)
    src = SOURCES[source]
    downloads = {r: src["cdn"].format(r=r, id=iid) for r in rends if r in RENDITIONS}
    if not downloads:  # page layout changed: try the usual sizes anyway
        downloads = {r: src["cdn"].format(r=r, id=iid) for r in ("publicationjpg", "large", "screen")}
    dist = label_value(lines, "Distance")
    dist = re.sub(r"(?i)light years?", "ly", dist).strip()
    return dict(
        id=iid, source=source, title=title, credit=credit_from(lines), license="CC BY 4.0",
        page=src["page"].format(id=iid), pixels=px or [0, 0], downloads=downloads,
        object=obj[:60], catalog=" / ".join(cat)[:40], kind=_kind(label_value(lines, "Type", nth=1)),
        constellation=label_value(lines, "Constellation")[:30], distance=dist[:30],
        ra=_coord(label_value(lines, "Position (RA)")), dec=_coord(label_value(lines, "Position (Dec)")),
        fit="band" if len(px) == 2 and px[1] and px[0] / px[1] > 2.6 else "cover", focus=None, zoom=1.0, note="",
    )


def fetch(text, source=None):
    import urllib.request
    s2, iid = parse_id(text)
    source = source or s2 or guess_source(iid)
    if not ID_RE.match(iid):
        raise ValueError(f"not an image ID: {text!r}")
    url = SOURCES[source]["page"].format(id=iid)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (2027 calendar kit)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        page = r.read().decode("utf-8", "replace")
    meta = parse_page(page, iid, source)
    if not meta["credit"]:
        raise ValueError(f"could not find the credit on {url} — add it with --custom and --credit instead")
    return meta


# ------------------------------------------------------------------ Wikimedia Commons
# Photos by amateur and professional astrophotographers that their authors have put
# under a free licence. Accepted: public domain / CC0, CC BY, CC BY-SA (ShareAlike: the
# adapted page must carry the same licence) and the GNU FDL (the calendar then reproduces
# the full licence text on its last page). Refused: ND (no derivatives, and a calendar page
# is an adaptation) and NC (the site takes donations, so non-commercial terms are unclear).
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
UA = "DeepSpaceExplorer2027-calendar/1.0 (https://archismancoder.com; calendar image import)"
MIN_PIXELS = 4000  # long side; smaller files print soft on A3


def commons_title(text):
    """'File:X.jpg' from a title, a Commons/Wikipedia page URL or a media-viewer link."""
    import urllib.parse
    t = urllib.parse.unquote(text.strip())
    m = re.search(r"(?:File|Image|Datei|Fichier):([^#?&|]+)$", t) or re.search(r"(?:File|Image):([^#?&|/]+)", t)
    if not m:
        raise ValueError(f"not a Commons file name or link: {text!r}")
    return "File:" + m.group(1).replace("_", " ").strip()


def strip_html(s):
    s = re.sub(r"<[^>]+>", "", s or "")
    return re.sub(r"\s+", " ", _html.unescape(s)).strip()


def licence_verdict(short):
    """(ok, sharealike, reason) for a Commons LicenseShortName."""
    u = (short or "").upper().replace("-", " ")
    if not u:
        return False, False, "no licence stated"
    if re.search(r"\bNC\b|NONCOMMERCIAL|NON COMMERCIAL", u):
        return False, False, "non-commercial only"
    if re.search(r"\bND\b|NO DERIV", u):
        return False, False, "no derivatives allowed"
    if "CC0" in u or "PUBLIC DOMAIN" in u or re.match(r"^PD\b", u):
        return True, False, "public domain"
    if "CC BY" in u or u.startswith("ATTRIBUTION") or "COPYRIGHTED FREE USE" in u:
        return True, "SA" in u.split() or "BY SA" in u, "free licence"
    if "GFDL" in u:  # allowed: the calendar then carries the full GFDL text on its last page
        return True, False, "GFDL (the calendar adds the licence text page)"
    return False, False, f"licence not recognised: {short}"


def _commons_meta(page, slot_hint=""):
    ii = (page.get("imageinfo") or [{}])[0]
    em = ii.get("extmetadata") or {}
    get = lambda k: strip_html((em.get(k) or {}).get("value", ""))
    short = get("LicenseShortName")
    ok, sa, why = licence_verdict(short)
    w, h = ii.get("width", 0), ii.get("height", 0)
    if ok and max(w, h) < MIN_PIXELS:
        ok, why = False, f"too small for print ({w}x{h} px)"
    title = page.get("title", "")
    artist = get("Artist") or get("Credit") or "Unknown author"
    attribution = get("Attribution")
    credit = attribution or f"{artist} / Wikimedia Commons"
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower().replace("file:", ""))
    slug = re.sub(r"-(jpe?g|png|tiff?)$", "", slug).strip("-")[:36]
    big = ii.get("thumburl") if ii.get("thumbwidth", 0) and ii.get("thumbwidth") < w else ii.get("url")
    return dict(
        ok=ok, reason=why, sharealike=sa,
        id=f"wm-{slug}", source="commons", title=strip_html(em.get("ObjectName", {}).get("value", "")) or
        title.replace("File:", "").rsplit(".", 1)[0], credit=credit[:300], license=short,
        license_url=get("LicenseUrl"), page=ii.get("descriptionurl", ""), pixels=[w, h],
        downloads={"large": [u for u in (big, ii.get("url")) if u]}, file_url=big, thumb_url=ii.get("thumburl"),
        object="", catalog="", kind="", constellation="", distance="", ra="", dec="", fit="cover",
        focus=None, zoom=1.0, note=("CC BY-SA: pages using it are shared under the same licence" if sa else
                                    "GNU FDL: the calendar adds the full licence text as its last page"
                                    if "GFDL" in (short or "").upper() else ""),
        artist=artist,
    )


def _commons_query(params):
    import json as _json
    import urllib.parse
    import urllib.request
    q = dict(action="query", format="json", prop="imageinfo", iiprop="url|size|extmetadata|mime",
             iiurlwidth="7000", **params)
    req = urllib.request.Request(COMMONS_API + "?" + urllib.parse.urlencode(q), headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return _json.loads(r.read().decode("utf-8"))


def commons_fetch(text):
    """Metadata for one Commons file, with a licence/size verdict (meta['ok'])."""
    title = commons_title(text)
    data = _commons_query({"titles": title})
    pages = list((data.get("query") or {}).get("pages", {}).values())
    if not pages or "missing" in pages[0]:
        raise ValueError(f"{title} was not found on Wikimedia Commons")
    return _commons_meta(pages[0])


def commons_scan(category, limit=200):
    """Every file in a Commons category, each with a licence/size verdict."""
    if not category.startswith("Category:"):
        category = "Category:" + category
    out, cont = [], {}
    while len(out) < limit:
        data = _commons_query(dict(generator="categorymembers", gcmtitle=category, gcmtype="file",
                                   gcmlimit="50", **cont))
        for p in (data.get("query") or {}).get("pages", {}).values():
            if (p.get("imageinfo") or [{}])[0].get("mime", "").startswith("image/"):
                out.append(_commons_meta(p))
        cont = data.get("continue") or {}
        cont.pop("continue", None)
        if not cont:
            break
    return out
