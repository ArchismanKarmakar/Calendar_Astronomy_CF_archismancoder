"""
2027 astronomy event engine — every event as an exact UTC instant.

Sources
- Computed (pyephem, VSOP87/ELP): Moon phases, equinoxes/solstices,
  oppositions, greatest elongations, Moon–planet / planet–planet /
  Moon–star close approaches, supermoon/micromoon, perihelion/aphelion,
  meteor peaks not timed by IMO (from solar longitude), local eclipse
  circumstances, nightly Moon illumination, target transit times.
- NASA GSFC "Eclipses During 2027" (Espenak): eclipse times/magnitudes.
- IMO Meteor Shower Calendar 2027 (cal2027.pdf): peak times, λ⊙, ZHR.
- BAA Comet Section, "Comet Prospects for 2027" (Shanklin) and
  Seiichi Yoshida's comet catalog: comet perihelia and forecasts.

Run:  python3 astro_engine.py   ->  data/events_utc.json
"""
import json
import math
from datetime import datetime, timedelta, timezone

import ephem

import util

YEAR = 2027
UTC = timezone.utc
DEG = 180.0 / math.pi


def e2dt(d):
    """ephem.Date -> aware UTC datetime (to the second)."""
    return ephem.Date(d).datetime().replace(tzinfo=UTC, microsecond=0)


def dt2e(dt):
    return ephem.Date(dt.astimezone(UTC).replace(tzinfo=None))


def iso(dt):
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def golden_min(f, a, b, tol=1 / 1440):
    """Minimise f on [a,b] (ephem day numbers) to ~1 minute."""
    g = (math.sqrt(5) - 1) / 2
    c, d = b - g * (b - a), a + g * (b - a)
    fc, fd = f(c), f(d)
    while b - a > tol:
        if fc < fd:
            b, d, fd = d, c, fc
            c = b - g * (b - a)
            fc = f(c)
        else:
            a, c, fc = c, d, fd
            d = a + g * (b - a)
            fd = f(d)
    x = (a + b) / 2
    return x, f(x)


def bisect_root(f, a, b, tol=1 / 1440):
    fa = f(a)
    while b - a > tol:
        m = (a + b) / 2
        fm = f(m)
        if (fm > 0) == (fa > 0):
            a, fa = m, fm
        else:
            b = m
    return (a + b) / 2


def scan_minima(sep_fn, start, end, step=0.25, thresh=None):
    """Local minima of sep_fn sampled every `step` days, refined to a minute."""
    out = []
    t = start
    prev2, prev1 = None, None
    while t <= end:
        v = sep_fn(t)
        if prev2 is not None and prev1[1] < prev2[1] and prev1[1] <= v:
            x, fx = golden_min(sep_fn, prev1[0] - step, prev1[0] + step)
            if thresh is None or fx < thresh:
                out.append((x, fx))
        prev2, prev1 = prev1, (t, v)
        t += step
    return out


def scan_maxima(fn, start, end, step=0.5):
    res = scan_minima(lambda t: -fn(t), start, end, step)
    return [(x, -v) for x, v in res]


Y0 = ephem.Date(f"{YEAR}/1/1")
Y1 = ephem.Date(f"{YEAR + 1}/1/1")

PLANETS = {"Mercury": ephem.Mercury, "Venus": ephem.Venus, "Mars": ephem.Mars,
           "Jupiter": ephem.Jupiter, "Saturn": ephem.Saturn,
           "Uranus": ephem.Uranus, "Neptune": ephem.Neptune}


def body_at(cls, t):
    b = cls()
    b.compute(ephem.Date(t))
    return b


def sep_deg(a, b):
    return float(ephem.separation(a, b)) * DEG


def elong_deg(cls, t):
    return sep_deg(body_at(cls, t), body_at(ephem.Sun, t))


def evening_or_morning(cls, t):
    """East of the Sun = evening sky."""
    p, s = body_at(cls, t), body_at(ephem.Sun, t)
    lp = float(ephem.Ecliptic(p).lon)
    ls = float(ephem.Ecliptic(s).lon)
    d = (lp - ls + math.pi) % (2 * math.pi) - math.pi
    return "evening" if d > 0 else "morning"


events = []


def add(cat, t, name, note="", short=None, timed=True, **extra):
    dt = t if isinstance(t, datetime) else e2dt(t)
    ev = dict(cat=cat, utc=iso(dt), name=name, short=short or name, note=note, timed=timed)
    ev.update(extra)
    events.append(ev)


# ---------------------------------------------------------------- Moon phases
FOLK = {1: "Wolf Moon", 2: "Snow Moon", 3: "Worm Moon", 4: "Pink Moon", 5: "Flower Moon",
        6: "Strawberry Moon", 7: "Buck Moon", 8: "Sturgeon Moon", 9: "Harvest Moon",
        10: "Hunter's Moon", 11: "Beaver Moon", 12: "Cold Moon"}
PHASES = [("new", ephem.next_new_moon, "New Moon"), ("fq", ephem.next_first_quarter_moon, "First Quarter"),
          ("full", ephem.next_full_moon, "Full Moon"), ("lq", ephem.next_last_quarter_moon, "Last Quarter")]
full_moons = []
for key, fn, label in PHASES:
    t = ephem.Date(Y0 - 2)
    while True:
        t = fn(t)
        if t >= Y1:
            break
        if t >= Y0:
            extra = {"phase": key}
            dt = e2dt(t)
            if key == "full":
                full_moons.append(t)
            add("moon_phase", t, label, short=label, **extra)
        t = ephem.Date(t + 1)

# Folk names: attach by the UTC month of the full moon (almanac convention),
# except Harvest Moon = full moon nearest the September equinox.
sep_eq = ephem.next_equinox(ephem.Date(f"{YEAR}/6/1"))
harvest = min(full_moons, key=lambda t: abs(t - sep_eq))
for ev in events:
    if ev.get("phase") == "full":
        t = dt2e(datetime.fromisoformat(ev["utc"].replace("Z", "+00:00")))
        m = e2dt(t).month
        name = "Harvest Moon" if abs(t - harvest) < 0.01 else FOLK[m]
        if name == "Harvest Moon" and m == 10:
            name = "Harvest Moon"
        ev["folk"] = name

# Supermoon / micromoon among full moons
def moon_dist_km(t):
    m = body_at(ephem.Moon, t)
    return m.earth_distance * 149597870.7

fm_d = [(t, moon_dist_km(t)) for t in full_moons]
t_s, d_s = min(fm_d, key=lambda x: x[1])
t_m, d_m = max(fm_d, key=lambda x: x[1])
add("moon_extreme", t_s, "Supermoon — closest Full Moon of 2027", f"Moon {d_s:,.0f} km away, ~14% larger than a micromoon", short="Supermoon", kind="super")
add("moon_extreme", t_m, "Micromoon — farthest Full Moon of 2027", f"Moon {d_m:,.0f} km away", short="Micromoon", kind="micro")

# --------------------------------------------------------------- Seasons
for fn, label in [(ephem.next_equinox, "Equinox"), (ephem.next_solstice, "Solstice")]:
    t = ephem.Date(Y0 - 1)
    while True:
        t = fn(t)
        if t >= Y1:
            break
        m = e2dt(t).month
        nm = {3: "March Equinox", 6: "June Solstice", 9: "September Equinox", 12: "December Solstice"}[m]
        add("season", t, nm, short=nm)
        t = ephem.Date(t + 1)

# -------------------------------------------------- Perihelion / aphelion
def earth_sun_au(t):
    return body_at(ephem.Sun, t).earth_distance

(tp, dp), = [x for x in scan_minima(earth_sun_au, Y0 - 10, Y0 + 60, step=1)][:1]
(ta, da), = [x for x in scan_maxima(earth_sun_au, Y0 + 150, Y0 + 220, step=1)][:1]
add("orbit", tp, "Earth at perihelion", f"Closest to the Sun: {dp * 149.5978707:.2f} million km", short="Perihelion")
add("orbit", ta, "Earth at aphelion", f"Farthest from the Sun: {da * 149.5978707:.2f} million km", short="Aphelion")

# --------------------------------------------------------------- Eclipses
# NASA GSFC, Eclipses During 2027 (times of greatest eclipse, UT)
ECL = [
    ("2027-02-06T16:00:48Z", "solar", "Annular solar eclipse", "Annular eclipse",
     "Magnitude 0.928, annularity up to 7m51s; path across S. America, the Atlantic and W. Africa", {}),
    ("2027-02-20T23:13:00Z", "lunar", "Penumbral lunar eclipse", "Penumbral eclipse",
     "Penumbral magnitude 0.93 — a subtle shading of the Moon's northern limb", {}),
    ("2027-07-18T16:03:00Z", "lunar", "Penumbral lunar eclipse (marginal)", "Penumbral eclipse",
     "Penumbral magnitude 0.0014 — technically an eclipse, practically undetectable", {}),
    ("2027-08-02T10:07:50Z", "solar", "Total solar eclipse — the eclipse of the century", "TOTAL SOLAR ECLIPSE",
     "Totality up to 6m23s (Luxor, Egypt); path crosses S. Spain, Gibraltar, N. Africa, Egypt, Saudi Arabia, Yemen", {"headline": True}),
    ("2027-08-17T07:14:00Z", "lunar", "Penumbral lunar eclipse", "Penumbral eclipse",
     "Penumbral magnitude 0.55", {}),
]
for u, kind, nm, sh, note, extra in ECL:
    add("eclipse", datetime.fromisoformat(u.replace("Z", "+00:00")), nm, note, short=sh, kind=kind, **extra)

# --------------------------------------------------------- Meteor showers
# IMO 2027 calendar: (code, name, lambda, ZHR, UT peak if published)
IMO = [
    ("QUA", "Quadrantids", 283.15, "80", "2027-01-04T03:25:00Z"),
    ("LYR", "Lyrids", 32.32, "18", "2027-04-23T01:40:00Z"),
    ("ETA", "η-Aquariids", 45.5, "50", "2027-05-06T09:00:00Z"),
    ("SDA", "S. δ-Aquariids", 128.0, "25", None),
    ("CAP", "α-Capricornids", 128.0, "5, bright fireballs", None),
    ("PER", "Perseids", 140.05, "110+", "2027-08-13T09:00:00Z"),
    ("DRA", "Draconids", 195.4, "variable", "2027-10-09T07:00:00Z"),
    ("ORI", "Orionids", 208.0, "20", None),
    ("STA", "Southern Taurids", 223.0, "7, slow fireballs", None),
    ("NTA", "Northern Taurids", 230.0, "5, slow fireballs", None),
    ("LEO", "Leonids", 235.27, "15", "2027-11-18T06:00:00Z"),
    ("GEM", "Geminids", 262.2, "150", "2027-12-14T20:00:00Z"),
    ("URS", "Ursids", 270.7, "10", "2027-12-23T04:00:00Z"),
]


def sun_lon_j2000(t):
    s = body_at(ephem.Sun, t)
    return float(ephem.Ecliptic(s, epoch=ephem.J2000).lon) * DEG


def time_of_solar_longitude(lam):
    # coarse scan then bisect on wrapped difference
    t = Y0 - 5
    while t < Y1 + 5:
        d1 = (sun_lon_j2000(t) - lam + 180) % 360 - 180
        d2 = (sun_lon_j2000(t + 1) - lam + 180) % 360 - 180
        if d1 <= 0 < d2:
            return bisect_root(lambda x: (sun_lon_j2000(x) - lam + 180) % 360 - 180, t, t + 1)
        t += 1
    raise ValueError(lam)


for code, nm, lam, zhr, ut in IMO:
    tl = time_of_solar_longitude(lam)
    if ut:
        dt = datetime.fromisoformat(ut.replace("Z", "+00:00"))
        src = "IMO 2027 calendar peak time"
    else:
        dt = e2dt(tl)
        src = f"peak at solar longitude {lam}° (IMO), time computed"
    illum = body_at(ephem.Moon, dt2e(dt)).phase
    moon_note = "dark skies" if illum < 25 else ("Moon interferes" if illum > 60 else "some moonlight")
    add("meteor", dt, f"{nm} peak", f"ZHR {zhr} · Moon {illum:.0f}% lit — {moon_note}",
        short=f"{nm}", code=code, zhr=zhr, solar_longitude=lam, source=src, night=True)

# Leonid trail encounters flagged by IMO for 2027
add("meteor", datetime(2027, 11, 17, 22, 0, tzinfo=UTC), "Leonids — possible outburst (dust trail)",
    "IMO: possible ZHR 40–50 from an old dust trail", short="Leonid outburst?", night=True)
add("meteor", datetime(2027, 11, 20, 4, 0, tzinfo=UTC), "Leonids — possible outburst (1167 trail)",
    "IMO: possible ZHR 40–50 from the 1167 trail", short="Leonid outburst?", night=True)

# ------------------------------------------------------------ Oppositions
def lon_diff(cls, t):
    p, s = body_at(cls, t), body_at(ephem.Sun, t)
    return ((float(ephem.Ecliptic(p).lon) - float(ephem.Ecliptic(s).lon)) * DEG - 180 + 540) % 360 - 180


for nm in ["Mars", "Jupiter", "Saturn", "Uranus", "Neptune"]:
    cls = PLANETS[nm]
    t = Y0
    while t < Y1:
        a, b = lon_diff(cls, t), lon_diff(cls, t + 2)
        # Sun overtakes an outer planet, so (planet - sun - 180) falls through 0
        if (a > 0 >= b or a < 0 <= b) and abs(a) < 20 and abs(b) < 20:
            to = bisect_root(lambda x: lon_diff(cls, x), t, t + 2)
            p = body_at(cls, to)
            const = ephem.constellation(p)[1]
            add("planet", to, f"{nm} at opposition",
                f"Mag {p.mag:+.1f} in {const}, {p.earth_distance:.2f} AU away — up all night, best of the year",
                short=f"{nm} opposition", body=nm)
        t += 2

# ------------------------------------------------- Greatest elongations
for nm in ["Mercury", "Venus"]:
    cls = PLANETS[nm]
    for x, v in scan_maxima(lambda t: elong_deg(cls, t), Y0, Y1, step=1):
        if Y0 <= x < Y1:
            side = evening_or_morning(cls, x)
            d = "E" if side == "evening" else "W"
            add("planet", x, f"{nm} greatest elongation {d} ({v:.1f}°)",
                f"Best {side} view of {nm} — {v:.1f}° from the Sun",
                short=f"{nm} {v:.0f}° {d}", body=nm)

# --------------------------------------------- Moon–planet conjunctions
moon_planets = []
for nm in ["Venus", "Mars", "Jupiter", "Saturn"]:
    cls = PLANETS[nm]
    f = lambda t, cls=cls: sep_deg(body_at(ephem.Moon, t), body_at(cls, t))
    for x, v in scan_minima(f, Y0, Y1, step=0.25, thresh=5.0):
        el = elong_deg(cls, x)
        if el < 15:  # lost in twilight
            continue
        side = evening_or_morning(cls, x)
        moon_planets.append((x, nm, v, side, el))
        add("conj_moon", x, f"Moon–{nm} conjunction ({v:.1f}°)",
            f"{side.capitalize()} sky, {el:.0f}° from the Sun — wide-field / landscape target",
            short=f"Moon–{nm} {v:.1f}°", body=nm, sep=round(v, 2))

# ------------------------------------------- Planet–planet conjunctions
pairs = [("Mercury", "Venus"), ("Mercury", "Mars"), ("Mercury", "Jupiter"), ("Mercury", "Saturn"),
         ("Venus", "Mars"), ("Venus", "Jupiter"), ("Venus", "Saturn"),
         ("Mars", "Jupiter"), ("Mars", "Saturn"), ("Jupiter", "Saturn")]
for a, b in pairs:
    ca, cb = PLANETS[a], PLANETS[b]
    f = lambda t, ca=ca, cb=cb: sep_deg(body_at(ca, t), body_at(cb, t))
    for x, v in scan_minima(f, Y0, Y1, step=0.5, thresh=5.0):
        el = elong_deg(ca, x)
        if el < 20:
            continue
        side = evening_or_morning(ca, x)
        add("conj_planet", x, f"{a}–{b} conjunction ({v:.2f}°)",
            f"{side.capitalize()} sky, {el:.0f}° from the Sun — both in one telephoto frame",
            short=f"{a}–{b} {v:.1f}°", sep=round(v, 2))

# --------------------------- Moon – bright star / cluster close approaches
FIXED = {
    "Antares": ("16:29:24.4", "-26:25:55", 1.0),
    "Regulus": ("10:08:22.3", "11:58:02", 1.0),
    "Spica": ("13:25:11.6", "-11:09:41", 1.0),
    "Aldebaran": ("04:35:55.2", "16:30:33", 1.0),
    "Pleiades (M45)": ("03:47:24", "24:07:00", 1.5),
    "Beehive Cluster (M44)": ("08:40:24", "19:40:00", 1.5),
}
for nm, (ra, dec, th) in FIXED.items():
    fb = ephem.FixedBody()
    fb._ra, fb._dec, fb._epoch = ephem.hours(ra), ephem.degrees(dec), ephem.J2000

    def f(t, fb=fb):
        fb.compute(ephem.Date(t))
        return sep_deg(body_at(ephem.Moon, t), fb)

    for x, v in scan_minima(f, Y0, Y1, step=0.25, thresh=th):
        el = sep_deg(body_at(ephem.Moon, x), body_at(ephem.Sun, x))
        if el < 25:
            continue
        illum = body_at(ephem.Moon, x).phase
        # Geocentric candidate only: each edition keeps it only if the
        # occultation / close pass is visible from its reference city.
        add("conj_star", x, f"Moon passes {nm}",
            f"Moon {illum:.0f}% lit", short=f"Moon–{nm.split(' (')[0]}",
            sep=round(v, 2), target=nm, ra=ra, dec=dec, local_check=True)

# ------------------------------------------------------------------ Comets
# BAA "Comet Prospects for 2027" (perihelion T, peak mag) + aerith.net
COMETS = [
    ("2027-01-19T17:00:00Z", "332P/Ikeya–Murakami at perihelion", "Comet 332P",
     "Peak ~mag 10.6 at 138° elongation — small-telescope target", False),
    ("2027-01-29T12:00:00Z", "Comet 2P/Encke passes 8° from globular cluster M2", "Comet Encke ~mag 5",
     "Best northern apparition since 2003; may reach mag 5 at month's end, low in the evening sky", True),
    ("2027-02-10T04:48:00Z", "2P/Encke at perihelion", "Encke perihelion",
     "In conjunction with the Sun — visible only in SOHO coronagraph images", False),
    ("2027-03-23T00:00:00Z", "C/2025 V2 (Rankin) at perihelion", "Comet Rankin",
     "Peak ~mag 13 — tracked long-exposure target", False),
    ("2027-05-07T07:12:00Z", "C/2024 T5 (ATLAS) at perihelion", "Comet 2024 T5",
     "Peak ~mag 12, very well placed (135°) all spring", False),
    ("2027-07-18T07:12:00Z", "C/2026 O1 (PANSTARRS) at perihelion", "Comet 2026 O1",
     "Peak ~mag 12.6 — telescope / imaging target", False),
    ("2027-08-26T00:00:00Z", "7P/Pons–Winnecke at perihelion", "Comet 7P",
     "Peak ~mag 11.5 — telescope target", False),
    ("2027-08-31T12:00:00Z", "45P/Honda–Mrkos–Pajdušáková at perihelion", "Comet 45P ~mag 8",
     "Binocular comet (~mag 8.5) low before dawn, a few degrees from M44", True),
    ("2027-09-11T12:00:00Z", "255P/Levy closest to the Beehive Cluster (M44)", "Comet 255P",
     "Could reach mag 9 near its Sep 25 perihelion — morning sky", False),
    ("2027-09-14T00:00:00Z", "300P/Catalina at perihelion", "Comet 300P",
     "Peak ~mag 12 — telescope target", False),
    ("2027-10-13T02:24:00Z", "104P/Kowal 2 at perihelion", "Comet 104P",
     "One of 2027's better prospects (~mag 10); brightest late October, morning sky", False),
    ("2027-10-15T02:24:00Z", "C/2025 Y1 (ATLAS) at perihelion", "Comet 2025 Y1",
     "Peak ~mag 10.3, excellently placed (139°) through autumn", False),
]
for u, nm, sh, note, hl in COMETS:
    add("comet", datetime.fromisoformat(u.replace("Z", "+00:00")), nm, note, short=sh, timed=False,
        highlight=hl)

# ---------------------------------------------------- Date-level events
DATED = [
    ("2027-01-31", "history", "Explorer 1 launched (1958)", "Explorer 1", "First US satellite; found the Van Allen belts"),
    ("2027-04-12", "history", "Day of Human Space Flight", "Gagarin 1961", "Gagarin's flight (1961) and STS-1 (1981)"),
    ("2027-04-24", "history", "Hubble Space Telescope launched (1990)", "Hubble launch", "STS-31, Space Shuttle Discovery"),
    ("2027-06-18", "history", "Sally Ride flies on STS-7 (1983)", "Sally Ride", "First American woman in space"),
    ("2027-06-30", "history", "International Asteroid Day", "Asteroid Day", "UN-designated; anniversary of the 1908 Tunguska event"),
    ("2027-07-20", "history", "Apollo 11 Moon landing (1969)", "Apollo 11", "Armstrong and Aldrin land in the Sea of Tranquility"),
    ("2027-08-20", "history", "Voyager 2 launched (1977)", "Voyager 2", "Still returning data from interstellar space"),
    ("2027-09-05", "history", "Voyager 1 launched (1977)", "Voyager 1", "The most distant human-made object"),
    ("2027-10-04", "history", "Sputnik 1 launched (1957)", "Sputnik 1", "Start of the Space Age; World Space Week begins"),
    ("2027-11-20", "history", "ISS first module, Zarya (1998)", "ISS Zarya", "Assembly of the International Space Station begins"),
    ("2027-12-25", "history", "James Webb Space Telescope launched (2021)", "JWST launch", "Ariane 5 from Kourou"),
    ("2027-05-15", "interstellar", "3I/ATLAS — interstellar object leaving range", "3I/ATLAS",
     "Third known interstellar visitor; now a large-telescope target only"),
]
for d, cat, nm, sh, note in DATED:
    y, m, dd = map(int, d.split("-"))
    add(cat, datetime(y, m, dd, 12, 0, tzinfo=UTC), nm, note, short=sh, timed=False, fixed_date=d)

# --------------------------------------------- Month-level notes (no date)
MONTH_NOTES = {
    4: ["Comet 29P/Schwassmann–Wachmann at opposition in early April — an outbursting comet worth monitoring (BAA)"],
    3: ["Milky Way core returns to the pre-dawn sky from mid-northern latitudes"],
    9: ["Last good evenings for the Milky Way core before it sinks into twilight"],
}

events.sort(key=lambda e: e["utc"])

def main():
    util.utf8_stdio()
    util.write_json(os_path("data", "events_utc.json"), {"year": YEAR, "engine": util.file_hash(__file__),
                                                         "events": events, "month_notes": MONTH_NOTES})
    from collections import Counter
    c = Counter(e["cat"] for e in events)
    print(len(events), "events:", dict(c))


def os_path(*p):
    import os
    return os.path.join(util.HERE, *p)


if __name__ == "__main__":
    main()
