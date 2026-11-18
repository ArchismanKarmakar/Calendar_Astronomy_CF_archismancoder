"""
Vector page renderer (ReportLab). Layout is done top-down in points within
the trim box; the canvas adds bleed on every side and records Trim/Bleed boxes.
"""
import calendar
import math
from datetime import date, datetime

from reportlab.lib.colors import Color
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.pdfgen.canvas import FILL_EVEN_ODD

FONTS = {
    "light": "Geist-Light", "reg": "Geist-Regular", "med": "Geist-Medium", "semi": "Geist-SemiBold",
    "bold": "Geist-Bold", "disp": "Fraunces-Display", "dispb": "Fraunces-Title", "dispm": "Fraunces-DisplayLight",
    "mono": "GeistMono-Regular", "monom": "GeistMono-Medium",
}
# Greek-letter meteor shower names, spelled out (and readable at small sizes)
_SPELL = {"η-": "Eta ", "α-": "Alpha ", "δ-": "Delta ", "γ-": "Gamma ", "κ-": "Kappa ", "σ-": "Sigma ",
          "ε-": "Epsilon ", "ζ-": "Zeta ", "θ-": "Theta ", "λ-": "Lambda ", "μ-": "Mu ", "π-": "Pi ", "ρ-": "Rho ",
          "τ-": "Tau ", "φ-": "Phi ", "χ-": "Chi ", "ω-": "Omega "}
_CMAP = None


def clean(s):
    """Spell Greek shower letters; fold any character the fonts lack to its plain
    Latin form (holiday names from many countries pass through here)."""
    global _CMAP
    s = str(s)
    for k, v in _SPELL.items():
        if k in s:
            s = s.replace(k, v)
    if _CMAP is None:
        try:
            from reportlab.pdfbase import pdfmetrics as _pm
            _CMAP = set(_pm.getFont("Geist-Regular").face.charToGlyph.keys())
        except Exception:
            return s
    if all(ord(ch) in _CMAP or ord(ch) < 128 for ch in s):
        return s
    import unicodedata
    out = []
    for ch in s:
        if ord(ch) < 128 or ord(ch) in _CMAP:
            out.append(ch)
        else:
            base = unicodedata.normalize("NFKD", ch)
            out.append("".join(c for c in base if ord(c) < 128 or ord(c) in _CMAP))
    return "".join(out)
_registered = False


def register_fonts(font_dir="fonts"):
    global _registered
    if _registered:
        return
    for f in set(FONTS.values()):
        pdfmetrics.registerFont(TTFont(f, f"{font_dir}/{f}.ttf"))
    _registered = True


def hexc(h, a=1.0):
    h = h.lstrip("#")
    return Color(int(h[0:2], 16) / 255, int(h[2:4], 16) / 255, int(h[4:6], 16) / 255, alpha=a)


T = dict(
    ink="#07090F", text="#F4F1EA", text2="#DADDE5", muted="#A9AEC0", gold="#E9BC70", cool="#8FC7FF",
    rule="#FFFFFF",
)
CAT = {
    "eclipse": "#FF6B5E", "meteor": "#FFB347", "planet": "#7CC9FF", "conj_planet": "#FFD27A",
    "conj_moon": "#8BF0B0", "conj_star": "#DDEBFF", "comet": "#FF8CC8", "interstellar": "#B79CFF",
    "season": "#8CDCFF", "orbit": "#A9C2FF", "history": "#C9CBD8", "moon_extreme": "#FFD27A",
    "moon_phase": "#F4F1EA", "note": "#C9CCD6",
}
HOLIDAY = "#FF9E9E"  # public holidays: the traditional calendar red, softened for a dark page
FESTIVAL = "#FFC46B"  # regional festivals (e.g. Bengali pujas): marigold
PHASE_ABBR = {"new": "New", "fq": "1st Q", "full": "Full", "lq": "Last Q"}
PHASE_FULL = {"new": "New Moon", "fq": "First Quarter", "full": "Full Moon", "lq": "Last Quarter"}
MONTHS = list(calendar.month_name)[1:]
MON3 = [m[:3] for m in MONTHS]


def priority(e):
    c = e["cat"]
    if c == "eclipse":
        return 100 if e.get("local_visible") else 88
    if c == "meteor":
        try:
            z = int("".join(ch for ch in e.get("zhr", "0").split(",")[0] if ch.isdigit()) or 0)
        except ValueError:
            z = 0
        return 84 if z >= 50 else (60 if "outburst" in e["name"] else 66)
    if c == "planet":
        return 78 if "opposition" in e["name"] else 52
    if c == "conj_planet":
        return 74
    if c == "comet":
        return 76 if e.get("highlight") else 46
    if c == "moon_extreme":
        return 70
    if c == "conj_star":
        return 68 if e.get("occultation") else 38
    if c == "conj_moon":
        return 56 if e.get("sep", 9) < 2 else 42
    return {"season": 58, "orbit": 30, "history": 28, "interstellar": 34}.get(c, 20)


class Page:
    def __init__(self, c, trim_w, trim_h, bleed):
        self.c, self.W, self.H, self.b = c, trim_w, trim_h, bleed
        self.PH = trim_h + 2 * bleed

    # coordinate transforms (top-down layout -> PDF)
    def X(self, x):
        return self.b + x

    def Y(self, y):
        return self.PH - (self.b + y)

    def image(self, path, full=True):
        self.c.drawImage(path, 0, 0, width=self.W + 2 * self.b, height=self.PH)

    def fill(self, color, alpha=1.0):
        col = hexc(color, alpha) if isinstance(color, str) else color
        self.c.setFillColor(col)
        self.c.setFillAlpha(alpha)

    def stroke(self, color, alpha=1.0, width=0.5):
        col = hexc(color, alpha) if isinstance(color, str) else color
        self.c.setStrokeColor(col)
        self.c.setStrokeAlpha(alpha)
        self.c.setLineWidth(width)

    def rect(self, x, y, w, h, color, alpha=1.0, r=0, stroke=None, salpha=0.2, sw=0.5):
        self.fill(color, alpha)
        if stroke:
            self.stroke(stroke, salpha, sw)
        if r:
            self.c.roundRect(self.X(x), self.Y(y + h), w, h, r, fill=1, stroke=1 if stroke else 0)
        else:
            self.c.rect(self.X(x), self.Y(y + h), w, h, fill=1, stroke=1 if stroke else 0)

    def hline(self, x0, x1, y, color="#FFFFFF", alpha=0.15, w=0.5):
        self.stroke(color, alpha, w)
        self.c.line(self.X(x0), self.Y(y), self.X(x1), self.Y(y))

    def vline(self, x, y0, y1, color="#FFFFFF", alpha=0.1, w=0.5):
        self.stroke(color, alpha, w)
        self.c.line(self.X(x), self.Y(y0), self.X(x), self.Y(y1))

    @staticmethod
    def width(s, font, size, tracking=0.0):
        s = clean(s)
        return pdfmetrics.stringWidth(s, FONTS.get(font, font), size) + tracking * max(0, len(s) - 1)

    def fit(self, s, font, size, maxw, tracking=0.0):
        if self.width(s, font, size, tracking) <= maxw:
            return s
        while s and self.width(s + "…", font, size, tracking) > maxw:
            s = s[:-1]
        return s.rstrip(" ,·—–-") + "…"

    def text(self, x, y, s, font="reg", size=8, color=None, alpha=1.0, align="left", tracking=0.0, maxw=None,
             halo=0.0):
        """y is the BASELINE, top-down. halo>0 draws a soft dark outline first so
        text stays legible on bright, busy photographs."""
        color = color or T["text"]
        s = clean(s)
        if maxw:
            s = self.fit(s, font, size, maxw, tracking)
        w = self.width(s, font, size, tracking)
        if align == "right":
            x -= w
        elif align == "center":
            x -= w / 2
        if halo:
            c = self.c
            c.saveState()
            c.setLineJoin(1)
            # stroke width is capped so large display type gets a subtle edge,
            # not a heavy outline
            for wf, af, cap in ((0.42, 0.30, 2.6), (0.22, 0.70, 1.3)):
                self.stroke(T["ink"], halo * af, min(cap, max(0.6, size * wf)))
                t = c.beginText()
                t.setTextOrigin(self.X(x), self.Y(y))
                t.setFont(FONTS.get(font, font), size)
                t.setCharSpace(tracking)
                t.setTextRenderMode(1)
                t.textOut(s)
                c.drawText(t)
            c.restoreState()
        self.fill(color, alpha)
        t = self.c.beginText()
        t.setTextOrigin(self.X(x), self.Y(y))
        t.setFont(FONTS.get(font, font), size)
        t.setCharSpace(tracking)
        t.textOut(s)
        self.c.drawText(t)
        return w

    def soft_box(self, x, y, w, h, alpha=0.5, spread=14, r=8):
        """Dark backdrop with feathered edges (stacked translucent rounded rects)."""
        n = 18
        for i in range(n):
            pad = spread * (1 - i / n)
            self.rect(x - pad, y - pad, w + 2 * pad, h + 2 * pad, T["ink"], alpha / n * 1.5, r=r + pad)

    def text_lines(self, x, y_bottom, lines, font, size, color, lead=1.32, align="left", halo=0.0, alpha=1.0):
        """Draw lines so the LAST baseline sits at y_bottom. Returns the first baseline."""
        y0 = y_bottom - (len(lines) - 1) * size * lead
        for i, ln in enumerate(lines):
            self.text(x, y0 + i * size * lead, ln, font, size, color, alpha=alpha, align=align, halo=halo)
        return y0

    def wrap(self, s, font, size, maxw):
        words, lines, cur = clean(s).split(), [], ""
        for w in words:
            t = (cur + " " + w).strip()
            if self.width(t, font, size) > maxw and cur:
                lines.append(cur)
                cur = w
            else:
                cur = t
        if cur:
            lines.append(cur)
        return lines

    def wrap_even(self, s, font, size, maxw):
        """Wrap into the fewest lines that fit maxw, with line lengths balanced
        (no one-word orphan such as a lone '4.0')."""
        n = len(self.wrap(s, font, size, maxw))
        lo, hi = maxw * 0.4, maxw
        for _ in range(18):
            mid = (lo + hi) / 2
            if len(self.wrap(s, font, size, mid)) > n:
                lo = mid
            else:
                hi = mid
        return self.wrap(s, font, size, hi)

    # ------------------------------------------------------------ icons
    def circle(self, cx, cy, r, color, alpha=1.0, fill=True, sw=0.6):
        if fill:
            self.fill(color, alpha)
        self.stroke(color, alpha, sw)
        self.c.circle(self.X(cx), self.Y(cy), r, fill=1 if fill else 0, stroke=0 if fill else 1)

    def crescent(self, cx, cy, r, color, alpha=1.0, phase=0.35):
        c = self.c
        c.saveState()
        p = c.beginPath()
        p.circle(self.X(cx), self.Y(cy), r)
        c.clipPath(p, stroke=0, fill=0)
        q = c.beginPath()
        q.rect(self.X(cx) - 2 * r, self.Y(cy) - 2 * r, 4 * r, 4 * r)
        q.circle(self.X(cx) - r * (1 - phase) * 1.6 + r * 0.55, self.Y(cy) + r * 0.05, r * 0.95)
        self.fill(color, alpha)
        c.drawPath(q, fill=1, stroke=0, fillMode=FILL_EVEN_ODD)
        c.restoreState()

    def star4(self, cx, cy, r, color, alpha=1.0, inner=0.32):
        p = self.c.beginPath()
        for i in range(8):
            a = math.pi / 4 * i - math.pi / 2
            rad = r if i % 2 == 0 else r * inner
            x, y = self.X(cx) + rad * math.cos(a), self.Y(cy) - rad * math.sin(a)
            (p.moveTo if i == 0 else p.lineTo)(x, y)
        p.close()
        self.fill(color, alpha)
        self.c.drawPath(p, fill=1, stroke=0)

    def ringed(self, cx, cy, r, color, alpha=1.0):
        self.circle(cx, cy, r * 0.52, color, alpha)
        self.stroke(color, alpha, max(0.45, r * 0.13))
        self.c.ellipse(self.X(cx) - r, self.Y(cy) - r * 0.30, self.X(cx) + r, self.Y(cy) + r * 0.30, fill=0, stroke=1)

    def moon_phase(self, cx, cy, r, key, color=None, alpha=1.0):
        color = color or T["text"]
        self.circle(cx, cy, r, color, alpha * 0.9, fill=False, sw=max(0.5, r * 0.14))
        self.fill(color, alpha)
        X, Y = self.X(cx), self.Y(cy)
        if key == "full":
            self.c.circle(X, Y, r, fill=1, stroke=0)
        elif key == "fq":
            self.c.wedge(X - r, Y - r, X + r, Y + r, -90, 180, fill=1, stroke=0)
        elif key == "lq":
            self.c.wedge(X - r, Y - r, X + r, Y + r, 90, 180, fill=1, stroke=0)

    def icon(self, e, cx, cy, r):
        cat = e["cat"]
        col = CAT.get(cat, "#FFFFFF")
        if cat in ("holiday", "festival"):
            self.rect(cx - r, cy - r, 2 * r, 2 * r, HOLIDAY if cat == "holiday" else FESTIVAL, 0.9, r=r * 0.3)
            self.rect(cx - r, cy - r, 2 * r, r * 0.6, T["ink"], 0.35, r=r * 0.3)
            return
        if cat == "moon_phase":
            self.moon_phase(cx, cy, r, e["phase"])
        elif cat == "moon_extreme":
            self.circle(cx, cy, r * 0.72, T["text"])
            self.circle(cx, cy, r * 1.05, CAT["moon_extreme"] if e.get("kind") == "super" else T["cool"],
                        fill=False, sw=max(0.5, r * 0.18))
        elif cat == "eclipse":
            if e.get("kind") == "solar":  # corona ring + "diamond ring" bead
                self.circle(cx, cy, r, col, 0.35)
                self.circle(cx, cy, r * 0.74, col)
                self.circle(cx, cy, r * 0.62, T["ink"])
                self.circle(cx + r * 0.50, cy - r * 0.42, r * 0.20, "#FFFFFF")
            else:
                self.circle(cx, cy, r, col, 0.85)
                self.crescent(cx, cy, r, T["ink"], 0.55, 0.15)
        elif cat == "meteor":
            self.stroke(col, 0.75, max(0.5, r * 0.18))
            self.c.line(self.X(cx - r * 1.25), self.Y(cy - r * 1.25), self.X(cx), self.Y(cy))
            self.star4(cx + r * 0.15, cy + r * 0.15, r * 0.95, col)
        elif cat == "planet":
            self.ringed(cx, cy, r, col)
        elif cat == "conj_planet":
            self.ringed(cx - r * 0.42, cy, r * 0.70, col)
            self.ringed(cx + r * 0.48, cy, r * 0.70, col)
        elif cat == "conj_moon":
            self.crescent(cx - r * 0.25, cy, r * 0.95, col)
            self.circle(cx + r * 0.85, cy - r * 0.15, r * 0.30, col)
        elif cat == "conj_star":
            self.crescent(cx - r * 0.25, cy, r * 0.95, col)
            self.star4(cx + r * 0.80, cy - r * 0.25, r * 0.55, col, inner=0.25)
        elif cat == "comet":
            self.stroke(col, 0.85, max(0.4, r * 0.15))
            for k, off in enumerate((-0.38, 0.0, 0.38)):
                self.c.line(self.X(cx + r * 0.25), self.Y(cy - r * 0.25),
                            self.X(cx - r * 1.15 + off * r), self.Y(cy - r * 1.15 - off * r))
            self.circle(cx + r * 0.32, cy + r * 0.32, r * 0.45, col)
        elif cat == "interstellar":
            p = self.c.beginPath()
            pts = [(cx, cy - r), (cx + r * 0.72, cy), (cx, cy + r), (cx - r * 0.72, cy)]
            for i, (x, y) in enumerate(pts):
                (p.moveTo if i == 0 else p.lineTo)(self.X(x), self.Y(y))
            p.close()
            self.fill(col, 0.35)
            self.stroke(col, 1, max(0.5, r * 0.15))
            self.c.drawPath(p, fill=1, stroke=1)
        elif cat == "season":
            self.circle(cx, cy, r, col, fill=False, sw=max(0.5, r * 0.15))
            self.stroke(col, 1, max(0.4, r * 0.12))
            self.c.line(self.X(cx - r), self.Y(cy), self.X(cx + r), self.Y(cy))
            self.c.line(self.X(cx), self.Y(cy - r), self.X(cx), self.Y(cy + r))
        elif cat == "orbit":
            self.stroke(col, 1, max(0.5, r * 0.14))
            self.c.ellipse(self.X(cx) - r, self.Y(cy) - r * 0.55, self.X(cx) + r, self.Y(cy) + r * 0.55, fill=0, stroke=1)
            self.circle(cx - r * 0.25, cy, r * 0.28, CAT["meteor"])
            self.circle(cx + r * 0.95, cy, r * 0.22, col)
        elif cat == "history":
            bw, bh = r * 0.62, r * 0.8
            self.rect(cx - bw / 2, cy - bh / 2, bw, bh, col)
            self.stroke(col, 1, max(0.4, r * 0.12))
            for s in (-1, 1):
                x0 = cx + s * bw / 2
                x1 = cx + s * (bw / 2 + r * 0.62)
                self.c.rect(self.X(min(x0, x1)), self.Y(cy + r * 0.35), abs(x1 - x0), r * 0.7, fill=0, stroke=1)
        else:  # note / info
            self.circle(cx, cy, r, col, fill=False, sw=max(0.5, r * 0.14))
            self.circle(cx, cy - r * 0.42, r * 0.12, col)
            self.stroke(col, 1, max(0.5, r * 0.16))
            self.c.line(self.X(cx), self.Y(cy - r * 0.1), self.X(cx), self.Y(cy + r * 0.5))


# --------------------------------------------------------------------------
def new_canvas(path, trim_w, trim_h, bleed, title, author):
    c = rl_canvas.Canvas(path, pagesize=(trim_w + 2 * bleed, trim_h + 2 * bleed), initialFontName="Geist-Regular", initialFontSize=8)
    c.setTitle(title)
    c.setAuthor(author)
    c.setSubject("Astronomy calendar 2027")
    c.setCreator("cal27 build.py")
    return c


def set_boxes(c, trim_w, trim_h, bleed):
    c.setTrimBox((bleed, bleed, bleed + trim_w, bleed + trim_h))
    c.setBleedBox((0, 0, trim_w + 2 * bleed, trim_h + 2 * bleed))


def credit_line(img, placeholder):
    if placeholder:
        return f"PLACEHOLDER ART — {img['id']} was not available when this was built ({img['credit']})"
    parts = [f"Image: {img['credit']}"]
    if img.get("source") in ("eso", "esahubble", "esawebb", "noirlab"):
        parts.append(img["id"])
    lic = img.get("license", "CC BY 4.0")
    if lic:
        parts.append(lic)
    if img.get("rotated"):
        parts.append("rotated")  # CC BY asks that changes be indicated
    return " · ".join(parts)


def target_meta(img):
    """'Emission nebula · Orion · 1,344 ly' with blank fields left out (own photos)."""
    return "  ·  ".join(x for x in (img.get("kind"), img.get("constellation"), img.get("distance")) if x)


def target_label(img, long=True):
    cat = (img.get("catalog") or "").upper()
    head = "TARGET OF THE MONTH" if long else "TARGET"
    return f"{head}  ·  {cat}" if cat else head


def target_when(md, ed, long=True):
    """Transit line; handles targets that never rise or have no position given."""
    city = ed["city"][0]
    if md.get("transit") in (None, "", "—"):
        return f"Position not given — no rise times for {city}" if long else "No position given"
    alt = md.get("transit_alt")
    if alt is not None and alt <= 0:
        return f"Never rises from {city} — a target for southern skies" if long and ed["city"][1] > 0 else \
            (f"Never rises from {city} — a target for northern skies" if long else f"Never rises · {city}")
    if long:
        low = " — low, find a clear horizon" if alt is not None and alt < 20 else ""
        return f"Highest {md['transit']} · {alt}° up from {city} (mid-month){low}"
    return f"Highest {md['transit']} · {alt}° · {city}"


def fmt_day(d, ed):
    return f"{MON3[d.month - 1]} {d.day}"


def day_events(loc, y, m):
    by = {}
    for e in loc["events"]:
        d = date.fromisoformat(e["local_date"])
        if d.year == y and d.month == m:
            by.setdefault(d.day, []).append(e)
    return by


def dark_text(windows):
    if not windows:
        return "none — bright Moon all month"
    return ", ".join(f"{a}" if a == b else f"{a}–{b}" for a, b in windows)


def month_matrix(y, m, week_start):
    cal = calendar.Calendar(firstweekday=week_start)
    return cal.monthdatescalendar(y, m)


def weekday_names(week_start, n=3):
    names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    order = [(week_start + i) % 7 for i in range(7)]
    return [names[i][:n].upper() for i in order], order


# ============================================================ WALL MONTH
def wall_month(c, P, cfg, loc, m, img, placeholder, bg_path, page_no):
    W, H = P.W, P.H
    y_ = loc["year"]
    ed = loc["edition"]
    mg = W * 0.052
    P.image(bg_path)
    photo_h = H * cfg["photo_frac"]

    # ---- header
    P.text(mg, mg + 9, f"{m:02d}  ·  {y_}", "monom", 8.5, T["gold"], tracking=1.2, halo=1)
    P.text(mg - 2, mg + 9 + 72, MONTHS[m - 1].upper(), "disp", 78, T["text"], tracking=5, halo=0.5)
    by = day_events(loc, y_, m)
    flat = sorted((e for d in by.values() for e in d if e["cat"] != "moon_phase"), key=priority, reverse=True)
    if flat:
        h = flat[0]
        hd = date.fromisoformat(h["local_date"])
        P.text(mg, mg + 9 + 72 + 36, f"{h['name']}  ·  {fmt_day(hd, ed)}", "reg", 12.5, T["text"],
               maxw=W * 0.62, halo=1)
    P.text(W - mg, mg + 9, f"{ed['label'].upper()} EDITION", "semi", 7.4, T["gold"], align="right", tracking=1.6,
           halo=1)
    P.text(W - mg, mg + 21, f"All times {ed['tzname']}", "med", 7.4, T["text"], align="right", halo=1)

    # ---- target card (bottom of photo zone)
    md = loc["months"][str(m)] if str(m) in loc["months"] else loc["months"][m]
    cw, ch = W * 0.50, 92
    cx0, cy0 = mg, photo_h - ch - 26
    P.rect(cx0, cy0, cw, ch, T["ink"], 0.68, r=6, stroke="#FFFFFF", salpha=0.12)
    px = cx0 + 14
    P.text(px, cy0 + 17, target_label(img), "semi", 6.6, T["gold"], tracking=1.3,
           maxw=cw - 28)
    P.text(px, cy0 + 41, img["object"], "dispb", 22, T["text"], maxw=cw - 28)
    P.text(px, cy0 + 55, target_meta(img), "reg", 7.6, T["text2"],
           maxw=cw - 28)
    P.text(px, cy0 + 70, target_when(md, ed), "mono", 6.8, T["text"], maxw=cw - 28)
    P.text(px, cy0 + 82, f"Dark-sky nights (Moon ≤25% at 21:00): {dark_text(md['dark_windows'])}", "mono", 6.8,
           T["cool"], maxw=cw - 28)
    # full credit, never shortened (CC BY 4.0 / ESO & ESA usage terms)
    cl = P.wrap_even(credit_line(img, placeholder), "med", 6.4, W - mg - (cx0 + cw + 18))
    P.text_lines(W - mg, photo_h - 10, cl, "med", 6.4, "#FF9A8A" if placeholder else T["text"], align="right",
                 halo=1)

    # ---- grid
    names, order = weekday_names(ed["week_start"])
    gx0, gx1 = mg, W - mg
    colw = (gx1 - gx0) / 7
    gy0 = photo_h + 8
    P.hline(gx0, gx1, gy0 + 16, alpha=0.30, w=0.6)
    for i, nm in enumerate(names):
        wkend = order[i] in (5, 6)
        P.text(gx0 + colw * i + 6, gy0 + 10, nm, "semi", 7, T["gold"] if wkend else T["text2"], tracking=1.6,
               alpha=1 if wkend else 0.85)
    weeks = month_matrix(y_, m, ed["week_start"])
    rows_top = gy0 + 18
    rows_bot = H * cfg["grid_bottom"]
    rh = (rows_bot - rows_top) / len(weeks)
    for r, wk in enumerate(weeks):
        ry = rows_top + rh * r
        if r:
            P.hline(gx0, gx1, ry, alpha=0.12)
        for k, d in enumerate(wk):
            x = gx0 + colw * k
            if k:
                P.vline(x, ry + 4, ry + rh - 4, alpha=0.07)
            inm = d.month == m
            if not inm:
                P.text(x + 6, ry + 18, str(d.day), "semi", 14.5, T["text"], alpha=0.16)
                continue
            pct = loc["illum"][d.isoformat()]
            dark = pct <= 25
            if dark:
                P.rect(x + 1.5, ry + 1.5, colw - 3, rh - 3, T["cool"], 0.075, r=3)
            evs = by.get(d.day, [])
            accent = max((e for e in evs if e["cat"] != "moon_phase"), key=priority, default=None)
            if accent is not None and priority(accent) >= 66:
                P.hline(x + 1.5, x + colw - 1.5, ry + 1.2, CAT.get(accent["cat"], "#FFFFFF"), 0.9, 1.2)
            hol = (loc.get("holidays") or {}).get(d.isoformat())
            fest = (loc.get("festivals") or {}).get(d.isoformat())
            nw = P.text(x + 6, ry + 18, str(d.day), "semi", 14.5,
                        HOLIDAY if hol else (FESTIVAL if fest else T["text"]))
            P.text(x + 8 + nw, ry + 17.5, f"{pct}%", "mono", 5.6, T["cool"] if dark else T["muted"],
                   alpha=1 if dark else 0.9)
            ph = next((e for e in evs if e["cat"] == "moon_phase"), None)
            ext = next((e for e in evs if e["cat"] == "moon_extreme"), None)
            if ph:
                pcx, pcy = x + colw - 10, ry + 11
                P.moon_phase(pcx, pcy, 4.4, ph["phase"])
                if ext:
                    P.circle(pcx, pcy, 6.4, CAT["moon_extreme"] if ext.get("kind") == "super" else T["cool"],
                             fill=False, sw=0.9)
                P.text(pcx + 4.4, ry + 23, ph["local_time"] or "", "mono", 5.0, T["text2"], align="right")
            lines = sorted((e for e in evs if e["cat"] not in ("moon_phase",) and not (e["cat"] == "moon_extreme" and ph)),
                           key=priority, reverse=True)
            if ph and ph["phase"] == "full" and ph.get("folk"):
                lines.insert(0, dict(cat="moon_phase", phase="full", short=ph["folk"], _folk=True))
            # long names (e.g. "Netaji Subhas Chandra Bose's Birthday") get two lines
            for name, flag in ((fest, "_fest"), (hol, "_hol")):
                if not name:
                    continue
                hl = P.wrap(name, "med", 5.9, colw - 10)
                if len(hl) > 2:
                    hl = [hl[0], P.fit(" ".join(hl[1:]), "med", 5.9, colw - 10)]
                for t in reversed(hl):
                    lines.insert(0, {"cat": "holiday", "short": t, flag: True})
            ly = ry + 32
            lh = 7.6
            maxl = max(0, int((ry + rh - 4 - ly) / lh) + 1)
            shown = lines[:maxl] if len(lines) <= maxl else lines[:max(0, maxl - 1)]
            for e in shown:
                if e.get("_hol") or e.get("_fest"):
                    P.text(x + 6, ly, e["short"], "med", 5.9, HOLIDAY if e.get("_hol") else FESTIVAL, maxw=colw - 10)
                elif e.get("_folk"):
                    P.text(x + 6, ly, e["short"], "med", 5.9, T["text2"], maxw=colw - 10)
                else:
                    P.icon(e, x + 8.5, ly - 2.0, 2.7)
                    P.text(x + 13.5, ly, e["short"], "med", 5.9, T["text"], maxw=colw - 17)
                ly += lh
            if len(lines) > len(shown):
                P.text(x + 6, ly, f"+{len(lines) - len(shown)} more below", "reg", 5.4, T["muted"])

    # ---- highlights panel
    hy = rows_bot + 12
    P.hline(gx0, gx1, hy - 2, alpha=0.30, w=0.6)
    P.text(gx0, hy + 10, "THIS MONTH", "semi", 7.4, T["gold"], tracking=1.6)
    items = sorted((e for d in by.values() for e in d if e["cat"] not in ("moon_phase",)),
                   key=lambda e: (e["local_date"], e.get("local_time") or "99"))
    notes = loc["month_notes"].get(str(m), [])
    ncol, gap = 3, 18
    colw2 = (gx1 - gx0 - gap * (ncol - 1)) / ncol
    top_y, bottom_y = hy + 27, H * cfg["hl_bottom"]
    NF, NS, NL, SS = 7.6, 6.6, 8.4, 6.8   # name, note size, note leading, stamp size

    def entry(kind, e):
        if kind == "n":
            return kind, e, "All month", e, P.wrap(e, "reg", NS, colw2 - 12)[:2]
        d = date.fromisoformat(e["local_date"])
        stamp = f"{MON3[d.month - 1]} {d.day:>2}" + (f" {e['local_time']}" if e.get("local_time") else
                                                    ("–" + str(date.fromordinal(d.toordinal() + 1).day)
                                                     if e.get("night") else ""))
        note = e.get("local_note") or e.get("note", "")
        if e.get("night_label"):
            note = f"{e['night_label']} · {note}"
        return kind, e, stamp, e["name"], P.wrap(note, "reg", NS, colw2 - 12)[:2]

    def layout(entries):
        cols, col, y = [[]], 0, top_y
        for en in entries:
            hgt = 10 + len(en[4]) * NL + 4
            if y + hgt - 4 > bottom_y + 2:
                col += 1
                y = top_y
                cols.append([])
                if col >= ncol:
                    return None
            cols[-1].append((y, en))
            y += hgt
        return cols

    chosen = items
    while True:
        ents = [entry("e", e) for e in chosen] + [entry("n", n) for n in notes]
        cols = layout(ents)
        if cols is not None or not chosen:
            break
        worst = min(chosen, key=priority)  # drop the least important; it is still in its date box
        chosen = [e for e in chosen if e is not worst]
    for ci, col in enumerate(cols or []):
        x = gx0 + ci * (colw2 + gap)
        for yb, (kind, e, stamp, name, notel) in col:
            P.icon(e if kind == "e" else {"cat": "note"}, x + 4, yb - 2.6, 3.4)
            sw = P.text(x + 12, yb, stamp, "monom", SS, T["gold"])
            P.text(x + 16 + sw, yb, name if kind == "e" else "", "semi", NF, T["text"], maxw=colw2 - 16 - sw)
            for j, ln in enumerate(notel):
                last = j == len(notel) - 1 and len(P.wrap(name if kind == "n" else (e.get("note", "")), "reg", NS,
                                                          colw2 - 12)) > 2 and False
                P.text(x + 12, yb + 9.2 + j * NL, ln, "reg", NS, T["text2"])

    footer(P, cfg, loc, page_no, mg)


def footer(P, cfg, loc, page_no, mg):
    W, H = P.W, P.H
    ed = loc["edition"]
    y = H - mg * 0.62
    P.text(mg, y, f"{cfg['brand'].upper()}  ·  {cfg['title'].upper()} {loc['year']}", "semi", 6.4, T["text2"],
           tracking=1.2)
    P.text(W - mg, y, f"{ed['label']} edition · {ed['tzname']}, daylight saving applied · Moon % at 21:00 local · {page_no}",
           "reg", 6.4, T["muted"], align="right", maxw=W * 0.6)


# ============================================================ DESK MONTH
def desk_month(c, P, cfg, loc, m, img, placeholder, bg_path, page_no):
    W, H = P.W, P.H
    y_ = loc["year"]
    ed = loc["edition"]
    mg = H * 0.055
    P.image(bg_path)
    panel = W * cfg["panel_frac"]
    md = loc["months"][str(m)] if str(m) in loc["months"] else loc["months"][m]

    # left panel: edition label, target card, full credit
    pw = panel - 2 * mg
    P.text(mg, mg + 7, f"{ed['label'].upper()} · {ed['tzname']}", "semi", 5.6, T["gold"], tracking=1.0,
           maxw=pw, halo=1)
    cl = P.wrap_even(credit_line(img, placeholder), "med", 5.0, pw)
    cred_top = P.text_lines(mg, H - mg * 0.55, cl, "med", 5.0, "#FF9A8A" if placeholder else T["text"], halo=1)
    ch = 66
    cy = cred_top - 12 - ch
    P.rect(mg - 7, cy, pw + 14, ch, T["ink"], 0.70, r=5, stroke="#FFFFFF", salpha=0.12)
    P.text(mg, cy + 12, target_label(img, False), "semi", 5.6, T["gold"], tracking=1.1, maxw=pw)
    P.text(mg, cy + 30, img["object"], "dispb", 17, T["text"], maxw=pw)
    P.text(mg, cy + 40, target_meta(img).replace("  ·  ", " · "), "reg", 6.0, T["text2"],
           maxw=pw)
    P.text(mg, cy + 50, target_when(md, ed, False), "mono", 5.8, T["text"],
           maxw=pw)
    P.text(mg, cy + 59, f"Dark nights: {dark_text(md['dark_windows'])}", "mono", 5.8, T["cool"], maxw=pw)

    # right: header + grid
    rx0 = panel - 2
    rx1 = W - mg
    P.text(rx0, mg + 6, f"{m:02d} · {y_}", "monom", 6.2, T["gold"], tracking=1.0)
    P.text(rx0 - 1, mg + 6 + 30, MONTHS[m - 1].upper(), "disp", 32, T["text"], tracking=2.5)
    names, order = weekday_names(ed["week_start"], 2)
    colw = (rx1 - rx0) / 7
    gy = mg + 50
    for i, nm in enumerate(names):
        wk = order[i] in (5, 6)
        P.text(rx0 + colw * i + 3, gy, nm, "semi", 5.4, T["gold"] if wk else T["text2"], tracking=1.0)
    P.hline(rx0, rx1, gy + 3.5, alpha=0.3, w=0.5)
    weeks = month_matrix(y_, m, ed["week_start"])
    by = day_events(loc, y_, m)
    top = gy + 5
    bot = H * cfg["grid_bottom"]
    rh = (bot - top) / len(weeks)
    for r, wk in enumerate(weeks):
        ry = top + rh * r
        if r:
            P.hline(rx0, rx1, ry, alpha=0.10, w=0.4)
        for k, d in enumerate(wk):
            x = rx0 + colw * k
            if d.month != m:
                P.text(x + 3, ry + 10, str(d.day), "semi", 8.5, T["text"], alpha=0.16)
                continue
            pct = loc["illum"][d.isoformat()]
            if pct <= 25:
                P.rect(x + 1, ry + 1, colw - 2, rh - 2, T["cool"], 0.08, r=2)
            evs = by.get(d.day, [])
            hol = (loc.get("holidays") or {}).get(d.isoformat())
            fest = (loc.get("festivals") or {}).get(d.isoformat())
            nw = P.text(x + 3, ry + 10, str(d.day), "semi", 8.5,
                        HOLIDAY if hol else (FESTIVAL if fest else T["text"]))
            if hol:
                P.text(x + 3, ry + 16.5, hol, "med", 4.1, HOLIDAY, maxw=colw - 5)
            if fest:
                P.text(x + 3, ry + (21.5 if hol else 16.5), fest.replace("Durga Puja · ", ""), "med", 4.1, FESTIVAL,
                       maxw=colw - 5)
            P.text(x + 4.5 + nw, ry + 9.5, f"{pct}%", "mono", 4.4, T["cool"] if pct <= 25 else T["muted"])
            ph = next((e for e in evs if e["cat"] == "moon_phase"), None)
            if ph:
                P.moon_phase(x + colw - 5, ry + 6.5, 2.6, ph["phase"])
                if any(e["cat"] == "moon_extreme" for e in evs):
                    P.circle(x + colw - 5, ry + 6.5, 3.8, CAT["moon_extreme"], fill=False, sw=0.6)
            icons = sorted((e for e in evs if e["cat"] not in ("moon_phase", "moon_extreme")), key=priority,
                           reverse=True)[:4]
            for i, e in enumerate(icons):
                P.icon(e, x + 5 + i * 7.6, ry + rh - 6, 2.5)

    # highlight strip (top items)
    hy = bot + 9
    P.hline(rx0, rx1, hy - 4, alpha=0.25, w=0.5)
    items = sorted((e for d in by.values() for e in d if e["cat"] not in ("moon_phase",)), key=priority,
                   reverse=True)[:cfg["desk_items"]]
    items.sort(key=lambda e: (e["local_date"], e.get("local_time") or "99"))
    for i, e in enumerate(items):
        yb = hy + 4 + i * 9.0
        d = date.fromisoformat(e["local_date"])
        P.icon(e, rx0 + 3, yb - 1.9, 2.6)
        sw = P.text(rx0 + 8.5, yb, f"{d.day:>2}" + (f" {e['local_time']}" if e.get("local_time") else ""), "monom",
                    5.6, T["gold"])
        P.text(rx0 + 12 + sw, yb, e["name"] + ("  · not visible here" if e.get("local_visible") is False else ""),
               "med", 5.9, T["text"], maxw=rx1 - rx0 - 14 - sw)
    P.text(rx1, H - mg * 0.55, f"{cfg['title']} {y_} · {page_no}", "reg", 5.0, T["muted"], align="right")


# ============================================================ COVER
def cover(c, P, cfg, loc, img, placeholder, bg_path, desk=False):
    W, H = P.W, P.H
    ed = loc["edition"]
    s = 0.55 if desk else 1.0
    mg = (H if desk else W) * 0.06
    P.image(bg_path)
    P.text(W / 2, mg + 14 * s, cfg["brand"].upper(), "semi", 8 * s + 1.5, T["text"], align="center",
           tracking=3 * s, halo=1)
    ty = H * (0.25 if desk else 0.31)
    P.text(W / 2, ty, cfg["title"].upper(), "semi", 15 * s + 2, T["gold"], align="center", tracking=7 * s, halo=1)
    Y = 200 * s
    year_base = ty + Y * 0.86
    P.text(W / 2, year_base, str(loc["year"]), "dispm", Y, T["text"], align="center", tracking=6 * s, halo=0.6)
    # Cormorant uses old-style figures: the 7 descends ~0.30 em below the baseline
    sub_y = year_base + Y * 0.12 + 22 * s
    P.text(W / 2, sub_y, cfg["subtitle"], "reg", 14 * s + 1.5, T["text"], align="center", halo=1)
    top = sorted((e for e in loc["events"] if e["cat"] != "moon_phase" and e.get("local_visible", True)),
                 key=priority, reverse=True)
    seen, picks = set(), []
    for e in top:
        k = e["name"].split(" (")[0]
        if k in seen:
            continue
        seen.add(k)
        picks.append(e)
        if len(picks) == (4 if desk else 6):
            break
    picks.sort(key=lambda e: e["local_date"])
    fs = 8.5 * s + 2.2
    lh = fs * 2.0
    lines = [f"{MON3[date.fromisoformat(e['local_date']).month - 1].upper()} "
             f"{date.fromisoformat(e['local_date']).day}  —  {e['name']}" for e in picks]
    maxw = max(P.width(l, "med", fs) for l in lines) + 30 * s
    by0 = max(sub_y + 40 * s, H * (0.66 if desk else 0.70))
    P.soft_box(W / 2 - maxw / 2 - 8 * s, by0 - lh * 1.7, maxw + 16 * s, lh * (len(lines) + 1.1), alpha=0.42,
               spread=34 * s, r=18 * s)
    P.text(W / 2, by0 - lh * 0.95, f"{loc['year']} HIGHLIGHTS FROM {ed['city'][0].upper()}", "semi", 6.5 * s + 1.8,
           T["gold"], align="center", tracking=2 * s, halo=1)
    for i, (e, line) in enumerate(zip(picks, lines)):
        w = P.width(line, "med", fs)
        P.icon(e, W / 2 - w / 2 - 9 * s - 2, by0 + i * lh - fs * 0.33, 3.2 * s + 1)
        P.text(W / 2, by0 + i * lh, line, "med", fs, T["text"], align="center", halo=1)
    cl = P.wrap_even(credit_line(img, placeholder), "med", 5 * s + 1.8, W - 2 * mg)
    ctop = P.text_lines(W / 2, H - mg * 0.75, cl, "med", 5 * s + 1.8, "#FF9A8A" if placeholder else T["text2"],
                        align="center", halo=1)
    P.text(W / 2, ctop - (7 * s + 1.5) * 1.8, f"{ed['label']} edition · all dates and times in {ed['tzname']}", "med",
           7 * s + 1.5, T["text"], align="center", halo=1)


# ============================================================ LEGEND
LEGEND = [
    (dict(cat="moon_phase", phase="fq"), "Moon phase", "New, first quarter, full, last quarter — with the local time it happens."),
    (dict(cat="moon_extreme", kind="super"), "Supermoon / micromoon", "Gold ring: the year's closest full Moon. Blue ring: the farthest."),
    (dict(cat="eclipse", kind="solar"), "Eclipse", "Solar or lunar. Each entry says whether it is visible from your edition's city."),
    (dict(cat="meteor"), "Meteor shower peak", "Placed on the night it peaks (evening date), with IMO's ZHR and how much the Moon interferes."),
    (dict(cat="planet"), "Opposition / elongation", "A planet's best night of the year; Mercury and Venus at their greatest distance from the Sun."),
    (dict(cat="conj_planet"), "Planet–planet conjunction", "Two planets within 5°, only listed when far enough from the Sun to see."),
    (dict(cat="conj_moon"), "Moon–planet conjunction", "The Moon within 5° of Venus, Mars, Jupiter or Saturn — a good wide-field shot."),
    (dict(cat="conj_star"), "Occultation / close pass", "The Moon covering or grazing Antares, the Pleiades or the Beehive, computed for your city."),
    (dict(cat="comet"), "Comet", "Perihelion or best-placed date, with the BAA's brightness forecast. Comets often surprise."),
    (dict(cat="interstellar"), "Interstellar object", "A confirmed visitor from outside the Solar System."),
    (dict(cat="season"), "Equinox / solstice", "The exact moment, in local time."),
    (dict(cat="orbit"), "Perihelion / aphelion", "Earth closest to and farthest from the Sun."),
    (dict(cat="history"), "Space history", "Anniversaries of launches and landings."),
    (dict(cat="note"), "All-month note", "Things true for the whole month, such as the Milky Way core season."),
]


def legend(c, P, cfg, loc, manifest, bg_path, desk=False):
    W, H = P.W, P.H
    ed = loc["edition"]
    s = 0.64 if desk else 1.22
    mg = (H if desk else W) * 0.06
    P.image(bg_path)
    P.text(mg, mg + 12 * s, "HOW TO READ THIS CALENDAR", "semi", 6.6 * s + 1, T["gold"], tracking=2 * s)
    P.text(mg, mg + 44 * s, "The sky, day by day", "dispb", 30 * s, T["text"])
    intro = (f"Every date and time is local to {ed['label']} ({ed['tzname']}, daylight saving applied). "
             f"Things that depend on place — eclipse visibility, occultations, when each month's target is highest — "
             f"are computed for {ed['city'][0]}. The percentage beside each date is how much of the Moon is lit "
             f"at 21:00 local; tinted days (25% or less) are the dark nights for faint galaxies and nebulae.")
    yy = mg + 62 * s
    fs = 7.6 * s + 0.6
    for ln in P.wrap(intro, "light", fs, W - 2 * mg):
        P.text(mg, yy, ln, "light", fs, T["text2"])
        yy += fs * 1.45
    yy += 12 * s
    ncol = 3 if desk else 2
    gap = 22 * s
    colw = (W - 2 * mg - gap * (ncol - 1)) / ncol
    entries = list(LEGEND)
    if loc.get("holidays"):
        entries.append((dict(cat="holiday"), f"Public holiday — {loc.get('holiday_country', '')}".rstrip(" —"),
                        "Date in red with the holiday's name. Holidays set by moon sighting are estimates (est.)."))
    if loc.get("festivals"):
        entries.append((dict(cat="festival"), loc.get("festival_name") or "Festivals",
                        "Date in marigold with the festival's name, following the 2027 panjika."))
    per = math.ceil(len(entries) / ncol)
    rowh = 30 * s + 2
    for i, (e, ttl, desc) in enumerate(entries):
        col, row = divmod(i, per)
        x = mg + col * (colw + gap)
        y = yy + row * rowh
        P.icon(e, x + 6 * s, y + 3.5 * s, 4.8 * s + 0.5)
        P.text(x + 17 * s, y + 6.5 * s, ttl, "semi", 7.6 * s + 0.6, T["text"])
        for j, ln in enumerate(P.wrap(desc, "reg", 6.3 * s + 0.5, colw - 18 * s)[:2]):
            P.text(x + 17 * s, y + 15.5 * s + j * 8.2 * s, ln, "reg", 6.3 * s + 0.5, T["text2"])
    yy += per * rowh + 6 * s

    def section(title, y):
        P.hline(mg, W - mg, y, alpha=0.25)
        P.text(mg, y + 13 * s, title, "semi", 5.8 * s + 0.8, T["gold"], tracking=1.5 * s)
        return y + 26 * s

    if not desk:
        yy = section("TIPS FOR ASTROPHOTOGRAPHERS", yy)
        tips = [
            "Shoot nebulae and galaxies on the tinted nights. Moonlight raises the sky background more than any city glow for a few days either side of full.",
            "Each target box gives the time it is highest from your city. Image within two hours of that time to keep it high and above haze.",
            "Moon–planet and planet–planet pairings make the best wide-field and landscape frames. Plan them for twilight, when the foreground still shows.",
            "For meteor showers, the best rates come after midnight. Check the Moon percentage on the peak night: above about 60% only bright meteors survive.",
            "Comet magnitudes are forecasts. Check COBS (cobs.si) or the BAA comet pages a week before, then decide whether to drive to dark skies.",
        ]
        tf = 6.8 * s
        for t_ in tips:
            lines = P.wrap(t_, "light", tf, W - 2 * mg - 14)
            P.star4(mg + 3.5, yy - tf * 0.32, 3.2, T["gold"])
            for j, ln in enumerate(lines):
                P.text(mg + 14, yy + j * tf * 1.38, ln, "light", tf, T["text2"])
            yy += len(lines) * tf * 1.38 + 4 * s
        yy += 6 * s

    all_cc = all(it.get("license", "CC BY 4.0") == "CC BY 4.0" for it in manifest)
    yy = section("IMAGE CREDITS — ALL CC BY 4.0, CREDITS MUST NOT BE SHORTENED" if all_cc
                 else "IMAGE CREDITS — CREDITS MUST NOT BE SHORTENED", yy)
    ncol = 3 if desk else 2
    colw = (W - 2 * mg - gap * (ncol - 1)) / ncol
    per = math.ceil(len(manifest) / ncol)
    cfs = 4.9 * s + 0.6
    rh = max(21 * s, 6.6 * s + max(len(P.wrap(it["credit"] + " · " + (it.get("license") or ""), "reg", cfs,
                                              colw - 24 * s)) for it in manifest) * cfs * 1.25 + 4)
    for i, it in enumerate(manifest):
        col, row = divmod(i, per)
        x = mg + col * (colw + gap)
        y = yy + row * rh
        lab = "Cover" if it["slot"] == "cover" else MON3[int(it["slot"]) - 1]
        P.text(x, y, lab, "monom", 5.6 * s + 0.4, T["gold"])
        name = it.get("object") or it.get("title") or "Photograph"
        if it.get("source") in ("eso", "esahubble", "esawebb", "noirlab"):
            name += f" — {it['id']}"
        P.text(x + 24 * s, y, name, "med", 5.8 * s + 0.4, T["text"], maxw=colw - 24 * s)
        cred = it["credit"] + ("" if it.get("license", "CC BY 4.0") == "CC BY 4.0" else
                               (f" · {it['license']}" if it.get("license") else ""))
        for j, ln in enumerate(P.wrap(cred, "reg", cfs, colw - 24 * s)):  # never truncated
            P.text(x + 24 * s, y + 6.6 * s + j * cfs * 1.25, ln, "reg", cfs, T["text2"])
    yy += per * rh + 8 * s

    yy = section("DATA SOURCES", yy)
    src = ("Moon phases, oppositions, elongations, conjunctions, occultations and Moon illumination computed with PyEphem "
           "(VSOP87/ELP). Eclipses: NASA GSFC, Eclipses During 2027. Meteor showers: IMO Meteor Shower Calendar 2027. "
           "Comets: BAA Comet Section, Comet Prospects for 2027, and Seiichi Yoshida's comet catalogue. Images: ESO, "
           "ESA/Hubble, ESA/Webb and NOIRLab under CC BY 4.0; their use does not imply endorsement by ESO, ESA, NASA, "
           "NSF or NOIRLab."
           + ("" if all_cc else " Other photographs are © their credited authors and used with permission."))
    sf = 6.0 * s + 0.4
    for ln in P.wrap(src, "light", sf, W - 2 * mg):
        P.text(mg, yy, ln, "light", sf, T["text2"])
        yy += sf * 1.4
    if not desk:
        footer(P, cfg, loc, "2", mg)


# ============================================================ YEAR AT A GLANCE
def year_page(c, P, cfg, loc, bg_path, desk=False):
    W, H = P.W, P.H
    ed = loc["edition"]
    y_ = loc["year"]
    s = 0.6 if desk else 1.0
    mg = (H if desk else W) * 0.06
    P.image(bg_path)
    P.text(mg, mg + 14 * s, f"{y_} AT A GLANCE · {ed['label'].upper()}", "semi", 7.5 * s + 1, T["gold"],
           tracking=2 * s)
    P.text(mg, mg + 46 * s, "Dark nights & key events", "dispb", 30 * s, T["text"])
    kx = W - mg
    kx -= P.text(kx, mg + 44 * s, "Moon ≤25% lit at 21:00 — best nights for deep-sky imaging", "reg", 6.2 * s + 1,
                 T["text2"], align="right") + 6 * s
    P.rect(kx - 9 * s, mg + 44 * s - 7 * s, 9 * s, 9 * s, T["cool"], 0.30, r=1.5)
    cols, rows = (4, 3) if not desk else (6, 2)
    gx0, gy0 = mg, mg + 64 * s
    gw = (W - 2 * mg)
    gh = H * (0.64 if not desk else 0.72) - gy0
    cw, chh = gw / cols, gh / rows
    by_date = {}
    for e in loc["events"]:
        if e["cat"] in ("moon_phase", "history"):
            continue
        if priority(e) >= 52:
            by_date.setdefault(e["local_date"], []).append(e)
    names, order = weekday_names(ed["week_start"], 1)
    for m in range(1, 13):
        col, row = (m - 1) % cols, (m - 1) // cols
        x0 = gx0 + col * cw + 4 * s
        y0 = gy0 + row * chh
        P.text(x0, y0 + 11 * s, MONTHS[m - 1].upper(), "semi", 7.2 * s + 0.6, T["text"], tracking=1.4 * s)
        dw = (cw - 14 * s) / 7
        for i, nm in enumerate(names):
            P.text(x0 + i * dw + dw / 2, y0 + 22 * s, nm, "semi", 5 * s + 0.4, T["muted"], align="center")
        weeks = month_matrix(y_, m, ed["week_start"])
        dh = (chh - 34 * s) / 6
        for r, wk in enumerate(weeks):
            for k, d in enumerate(wk):
                if d.month != m:
                    continue
                cx = x0 + k * dw + dw / 2
                cy = y0 + 30 * s + r * dh
                pct = loc["illum"][d.isoformat()]
                if pct <= 25:
                    P.rect(cx - dw / 2 + 0.6, cy - 1 * s, dw - 1.2, dh - 1.2, T["cool"], 0.22, r=1.5)
                evs = sorted(by_date.get(d.isoformat(), []), key=priority, reverse=True)
                hol = d.isoformat() in (loc.get("holidays") or {})
                fest = d.isoformat() in (loc.get("festivals") or {})
                P.text(cx, cy + dh * 0.48, str(d.day), "semi" if (evs or hol or fest) else "reg", 6.6 * s + 0.6,
                       HOLIDAY if hol else (FESTIVAL if fest else (T["text"] if evs else T["text2"])), align="center",
                       alpha=1 if (evs or hol or fest) else 0.75)
                if evs:
                    P.icon(evs[0], cx + dw * 0.36, cy + dh * 0.10, 1.9 * s + 0.6)
    if desk:
        return
    # top events list
    ty = gy0 + gh + 18
    P.hline(mg, W - mg, ty - 6, alpha=0.25)
    P.text(mg, ty + 8, f"THE BIG ONES — AS SEEN FROM {ed['city'][0].upper()}", "semi", 7, T["gold"], tracking=1.6)
    top = sorted((e for e in loc["events"] if e["cat"] not in ("moon_phase", "history") and e.get("local_visible", True)),
                 key=priority, reverse=True)
    seen, picks = set(), []
    for e in top:
        k = e["name"].split(" (")[0].split(" —")[0]
        if k in seen:
            continue
        seen.add(k)
        picks.append(e)
        if len(picks) == 18:
            break
    picks.sort(key=lambda e: e["local_date"])
    colw = (W - 2 * mg - 24) / 2
    for i, e in enumerate(picks):
        col, row = divmod(i, 9)
        x = mg + col * (colw + 24)
        yb = ty + 28 + row * 23.5
        d = date.fromisoformat(e["local_date"])
        P.icon(e, x + 4, yb - 2.5, 3.4)
        sw = P.text(x + 13, yb, f"{MON3[d.month - 1]} {d.day:>2}" + (f" {e['local_time']}" if e.get('local_time') else ""),
                    "monom", 7.0, T["gold"])
        P.text(x + 17 + sw, yb, e["name"], "semi", 7.8, T["text"], maxw=colw - 17 - sw)
        P.text(x + 13, yb + 9.6, e.get("local_note") or e.get("note", ""), "reg", 6.7, T["text2"], maxw=colw - 13)
    footer(P, cfg, loc, "15", mg)
