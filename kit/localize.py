"""
Per-edition localisation: shifts every UTC event into the edition's time zone,
assigns calendar dates, and adds the things that genuinely depend on place:
local eclipse circumstances, which Moon–star occultations are visible from the
reference city, nightly Moon illumination at 21:00 local, dark-sky windows,
and when each month's deep-sky target is highest.
"""
import calendar
import json
import math
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import ephem

import util

DEG = 180 / math.pi
UTC = timezone.utc

EDITIONS = {
    "US-PT": dict(label="US Pacific", tzname="Pacific Time", tz="America/Los_Angeles",
                  city=("Los Angeles", 34.05, -118.24), paper="US", week_start=6),
    "US-ET": dict(label="US Eastern", tzname="Eastern Time", tz="America/New_York",
                  city=("New York", 40.71, -74.01), paper="US", week_start=6),
    "UK": dict(label="UK & Ireland", tzname="UK time (GMT/BST)", tz="Europe/London",
               city=("London", 51.51, -0.13), paper="ISO", week_start=0),
    "CET": dict(label="Central Europe", tzname="Central European Time", tz="Europe/Berlin",
                city=("Berlin", 52.52, 13.40), paper="ISO", week_start=0),
    "IN": dict(label="India", tzname="India Standard Time", tz="Asia/Kolkata",
               city=("New Delhi", 28.61, 77.21), paper="ISO", week_start=6),
    "JP": dict(label="Japan", tzname="Japan Standard Time", tz="Asia/Tokyo",
               city=("Tokyo", 35.68, 139.69), paper="ISO", week_start=6),
}

# Every city the website offers (the six above are the print-shop editions the kit
# builds by default). paper: US = Tabloid / Half-letter, ISO = A3 / A5.
# week_start: 6 = Sunday-first, 0 = Monday-first.
_C = [  # code, region, label, time-zone name, IANA zone, city, lat, lon, paper, week start
    ("US-PT", "Americas", "US Pacific", "Pacific Time", "America/Los_Angeles", "Los Angeles", 34.05, -118.24, "US", 6),
    ("US-MT", "Americas", "US Mountain", "Mountain Time", "America/Denver", "Denver", 39.74, -104.99, "US", 6),
    ("US-AZ", "Americas", "Arizona", "Mountain Standard Time", "America/Phoenix", "Phoenix", 33.45, -112.07, "US", 6),
    ("US-CT", "Americas", "US Central", "Central Time", "America/Chicago", "Chicago", 41.88, -87.63, "US", 6),
    ("US-ET", "Americas", "US Eastern", "Eastern Time", "America/New_York", "New York", 40.71, -74.01, "US", 6),
    ("US-HI", "Americas", "Hawaii", "Hawaii Time", "Pacific/Honolulu", "Honolulu", 21.31, -157.86, "US", 6),
    ("US-AK", "Americas", "Alaska", "Alaska Time", "America/Anchorage", "Anchorage", 61.22, -149.90, "US", 6),
    ("CA-PT", "Americas", "Canada Pacific", "Pacific Time", "America/Vancouver", "Vancouver", 49.28, -123.12, "US", 6),
    ("CA-ET", "Americas", "Canada Eastern", "Eastern Time", "America/Toronto", "Toronto", 43.65, -79.38, "US", 6),
    ("MX", "Americas", "Mexico", "Central Mexico Time", "America/Mexico_City", "Mexico City", 19.43, -99.13, "US", 6),
    ("CO", "Americas", "Colombia", "Colombia Time", "America/Bogota", "Bogotá", 4.71, -74.07, "US", 6),
    ("PE", "Americas", "Peru", "Peru Time", "America/Lima", "Lima", -12.05, -77.04, "ISO", 6),
    ("BR", "Americas", "Brazil (Brasília)", "Brasília Time", "America/Sao_Paulo", "São Paulo", -23.55, -46.63, "ISO", 6),
    ("AR", "Americas", "Argentina", "Argentina Time", "America/Argentina/Buenos_Aires", "Buenos Aires", -34.60, -58.38, "ISO", 6),
    ("CL", "Americas", "Chile", "Chile Time", "America/Santiago", "Santiago", -33.45, -70.67, "US", 0),
    ("CL-N", "Americas", "Chile — observatory country", "Chile Time", "America/Santiago", "La Serena", -29.90, -71.25, "US", 0),
    ("UK", "Europe", "UK & Ireland", "UK time (GMT/BST)", "Europe/London", "London", 51.51, -0.13, "ISO", 0),
    ("IE", "Europe", "Ireland", "Irish time", "Europe/Dublin", "Dublin", 53.35, -6.26, "ISO", 0),
    ("PT", "Europe", "Portugal", "Western European Time", "Europe/Lisbon", "Lisbon", 38.72, -9.14, "ISO", 0),
    ("ES", "Europe", "Spain", "Central European Time", "Europe/Madrid", "Madrid", 40.42, -3.70, "ISO", 0),
    ("FR", "Europe", "France", "Central European Time", "Europe/Paris", "Paris", 48.86, 2.35, "ISO", 0),
    ("CET", "Europe", "Central Europe", "Central European Time", "Europe/Berlin", "Berlin", 52.52, 13.40, "ISO", 0),
    ("NL", "Europe", "Netherlands & Belgium", "Central European Time", "Europe/Amsterdam", "Amsterdam", 52.37, 4.90, "ISO", 0),
    ("IT", "Europe", "Italy", "Central European Time", "Europe/Rome", "Rome", 41.90, 12.50, "ISO", 0),
    ("CH", "Europe", "Switzerland & Austria", "Central European Time", "Europe/Zurich", "Zürich", 47.37, 8.54, "ISO", 0),
    ("PL", "Europe", "Poland", "Central European Time", "Europe/Warsaw", "Warsaw", 52.23, 21.01, "ISO", 0),
    ("SE", "Europe", "Scandinavia", "Central European Time", "Europe/Stockholm", "Stockholm", 59.33, 18.07, "ISO", 0),
    ("FI", "Europe", "Finland & Baltics", "Eastern European Time", "Europe/Helsinki", "Helsinki", 60.17, 24.94, "ISO", 0),
    ("GR", "Europe", "Greece", "Eastern European Time", "Europe/Athens", "Athens", 37.98, 23.73, "ISO", 0),
    ("TR", "Europe", "Türkiye", "Türkiye Time", "Europe/Istanbul", "Istanbul", 41.01, 28.98, "ISO", 0),
    ("RU", "Europe", "Moscow", "Moscow Time", "Europe/Moscow", "Moscow", 55.76, 37.62, "ISO", 0),
    ("EG", "Africa & Middle East", "Egypt", "Egypt Time", "Africa/Cairo", "Cairo", 30.04, 31.24, "ISO", 6),
    ("NG", "Africa & Middle East", "Nigeria", "West Africa Time", "Africa/Lagos", "Lagos", 6.52, 3.38, "ISO", 0),
    ("KE", "Africa & Middle East", "Kenya", "East Africa Time", "Africa/Nairobi", "Nairobi", -1.29, 36.82, "ISO", 0),
    ("ZA", "Africa & Middle East", "South Africa", "South Africa Time", "Africa/Johannesburg", "Johannesburg", -26.20, 28.05, "ISO", 0),
    ("NA", "Africa & Middle East", "Namibia", "Central Africa Time", "Africa/Windhoek", "Windhoek", -22.56, 17.08, "ISO", 0),
    ("IL", "Africa & Middle East", "Israel", "Israel Time", "Asia/Jerusalem", "Jerusalem", 31.77, 35.21, "ISO", 6),
    ("SA", "Africa & Middle East", "Saudi Arabia", "Arabia Time", "Asia/Riyadh", "Riyadh", 24.71, 46.68, "ISO", 6),
    ("AE", "Africa & Middle East", "UAE & Oman", "Gulf Time", "Asia/Dubai", "Dubai", 25.20, 55.27, "ISO", 0),
    ("IR", "Africa & Middle East", "Iran", "Iran Time", "Asia/Tehran", "Tehran", 35.69, 51.39, "ISO", 6),
    ("PK", "Asia", "Pakistan", "Pakistan Time", "Asia/Karachi", "Karachi", 24.86, 67.01, "ISO", 0),
    ("IN", "Asia", "India", "India Standard Time", "Asia/Kolkata", "New Delhi", 28.61, 77.21, "ISO", 6),
    ("IN-MUM", "Asia", "India — Mumbai", "India Standard Time", "Asia/Kolkata", "Mumbai", 19.08, 72.88, "ISO", 6),
    ("IN-KOL", "Asia", "India — Kolkata", "India Standard Time", "Asia/Kolkata", "Kolkata", 22.57, 88.36, "ISO", 6),
    ("IN-BLR", "Asia", "India — Bengaluru", "India Standard Time", "Asia/Kolkata", "Bengaluru", 12.97, 77.59, "ISO", 6),
    ("IN-LEH", "Asia", "India — Ladakh (Hanle dark-sky reserve)", "India Standard Time", "Asia/Kolkata", "Hanle", 32.78, 78.96, "ISO", 6),
    ("LK", "Asia", "Sri Lanka", "Sri Lanka Time", "Asia/Colombo", "Colombo", 6.93, 79.86, "ISO", 0),
    ("NP", "Asia", "Nepal", "Nepal Time", "Asia/Kathmandu", "Kathmandu", 27.72, 85.32, "ISO", 6),
    ("BD", "Asia", "Bangladesh", "Bangladesh Time", "Asia/Dhaka", "Dhaka", 23.81, 90.41, "ISO", 6),
    ("TH", "Asia", "Thailand & Vietnam", "Indochina Time", "Asia/Bangkok", "Bangkok", 13.76, 100.50, "ISO", 6),
    ("SG", "Asia", "Singapore & Malaysia", "Singapore Time", "Asia/Singapore", "Singapore", 1.35, 103.82, "ISO", 0),
    ("ID", "Asia", "Indonesia (West)", "Western Indonesia Time", "Asia/Jakarta", "Jakarta", -6.21, 106.85, "ISO", 0),
    ("PH", "Asia", "Philippines", "Philippine Time", "Asia/Manila", "Manila", 14.60, 120.98, "US", 6),
    ("CN", "Asia", "China", "China Standard Time", "Asia/Shanghai", "Beijing", 39.90, 116.40, "ISO", 0),
    ("HK", "Asia", "Hong Kong", "Hong Kong Time", "Asia/Hong_Kong", "Hong Kong", 22.32, 114.17, "ISO", 6),
    ("TW", "Asia", "Taiwan", "Taiwan Time", "Asia/Taipei", "Taipei", 25.03, 121.57, "ISO", 6),
    ("KR", "Asia", "South Korea", "Korea Standard Time", "Asia/Seoul", "Seoul", 37.57, 126.98, "ISO", 6),
    ("JP", "Asia", "Japan", "Japan Standard Time", "Asia/Tokyo", "Tokyo", 35.68, 139.69, "ISO", 6),
    ("AU-W", "Oceania", "Western Australia", "Australian Western Time", "Australia/Perth", "Perth", -31.95, 115.86, "ISO", 0),
    ("AU-SA", "Oceania", "South Australia", "Australian Central Time", "Australia/Adelaide", "Adelaide", -34.93, 138.60, "ISO", 0),
    ("AU-Q", "Oceania", "Queensland", "Australian Eastern Standard Time", "Australia/Brisbane", "Brisbane", -27.47, 153.03, "ISO", 0),
    ("AU-E", "Oceania", "Australia East (NSW, Vic, ACT, Tas)", "Australian Eastern Time", "Australia/Sydney", "Sydney", -33.87, 151.21, "ISO", 0),
    ("NZ", "Oceania", "New Zealand", "New Zealand Time", "Pacific/Auckland", "Auckland", -36.85, 174.76, "ISO", 0),
]
CITIES = {c[0]: dict(label=c[2], tzname=c[3], tz=c[4], city=(c[5], c[6], c[7]), paper=c[8], week_start=c[9],
                     region=c[1]) for c in _C}
for _k, _v in EDITIONS.items():  # the print editions keep their exact settings
    CITIES[_k] = dict(_v, region=CITIES[_k]["region"])

TARGETS = {  # month -> RA, Dec (J2000) of the image / target of the month
    1: ("05:35:17", "-05:23:28"), 2: ("07:18:30", "-13:13:48"), 3: ("11:18:56", "13:05:32"),
    4: ("13:29:53", "47:11:43"), 5: ("12:39:59", "-11:37:23"), 6: ("16:41:41", "36:27:37"),
    7: ("18:03:37", "-24:23:12"), 8: ("18:18:48", "-13:49:00"), 9: ("00:42:44", "41:16:09"),
    10: ("01:33:51", "30:39:37"), 11: ("22:29:39", "-20:50:14"), 12: ("05:34:32", "22:00:52"),
}


def parse_utc(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def observer(city, dt_utc):
    o = ephem.Observer()
    o.lat, o.lon = str(city[1]), str(city[2])
    o.elevation = 0
    o.pressure = 0  # geometric altitudes
    o.date = ephem.Date(dt_utc.astimezone(UTC).replace(tzinfo=None))
    return o


def alt_of(body, o):
    body.compute(o)
    return float(body.alt) * DEG


def solar_eclipse_local(city, t_max, tz):
    best = None
    contact = []
    for k in range(-300, 301, 2):
        t = t_max + timedelta(minutes=k)
        o = observer(city, t)
        s, m = ephem.Sun(), ephem.Moon()
        s.compute(o); m.compute(o)
        if s.alt <= 0:
            continue
        sep = float(ephem.separation(s, m)) * DEG
        rs, rm = float(s.radius) * DEG, float(m.radius) * DEG
        if sep < rs + rm:
            mag = (rs + rm - sep) / (2 * rs)
            contact.append(t)
            if best is None or mag > best[1]:
                best = (t, mag, sep < rm - rs)
    if not best:
        return None
    t, mag, total = best
    lt = t.astimezone(tz)
    kind = "TOTAL" if total else "partial"
    return dict(kind=kind, mag=round(mag, 2), local_max=lt.strftime("%H:%M"),
                start=contact[0].astimezone(tz).strftime("%H:%M"),
                end=contact[-1].astimezone(tz).strftime("%H:%M"))


def lunar_eclipse_local(city, t_max):
    o = observer(city, t_max)
    return alt_of(ephem.Moon(), o)


def star_pass_local(city, ev, tz):
    """Topocentric min separation while Moon >5° up and Sun < -6°."""
    fb = ephem.FixedBody()
    fb._ra, fb._dec, fb._epoch = ephem.hours(ev["ra"]), ephem.degrees(ev["dec"]), ephem.J2000
    t0 = parse_utc(ev["utc"])
    best, inside = None, []
    for k in range(-360, 361, 2):
        t = t0 + timedelta(minutes=k)
        o = observer(city, t)
        m, s = ephem.Moon(), ephem.Sun()
        m.compute(o); s.compute(o); fb.compute(o)
        if m.alt * DEG < 5 or s.alt * DEG > -6:
            continue
        sep = float(ephem.separation(m, fb)) * DEG
        rm = float(m.radius) * DEG
        if sep < rm:
            inside.append(t)
        if best is None or sep < best[1]:
            best = (t, sep, rm)
    if not best:
        return None
    t, sep, rm = best
    if inside:
        return dict(kind="occultation", start=inside[0].astimezone(tz).strftime("%H:%M"),
                    end=inside[-1].astimezone(tz).strftime("%H:%M"), when=inside[0])
    if sep < 1.0:
        return dict(kind="close", sep=round(sep, 1), local=t.astimezone(tz).strftime("%H:%M"), when=t)
    return None


def illum_at(dt_utc):
    m = ephem.Moon()
    m.compute(ephem.Date(dt_utc.astimezone(UTC).replace(tzinfo=None)))
    return m.phase


def target_highest(city, month, tz, year=2027, radec=None):
    """Transit time and altitude of the month's target on the 15th."""
    ra, dec = radec or TARGETS[month]
    fb = ephem.FixedBody()
    fb._ra, fb._dec, fb._epoch = ephem.hours(ra), ephem.degrees(dec), ephem.J2000
    local_noon = datetime(year, month, 15, 12, 0, tzinfo=tz)
    o = observer(city, local_noon)
    tr = o.next_transit(fb)
    t_tr = ephem.Date(tr).datetime().replace(tzinfo=UTC)
    o.date = tr
    fb.compute(o)
    alt = float(fb.alt) * DEG
    return t_tr.astimezone(tz).strftime("%H:%M"), round(alt)


from skycalc import southern_folk, transit_simple, gmst_deg  # noqa: E402,F401  (pure Python, browser-safe)


def localize(events_doc, code, targets=None):
    targets = targets or {}
    ed = dict(CITIES[code])
    tz = ZoneInfo(ed["tz"])
    city = ed["city"]
    out = []
    for ev in events_doc["events"]:
        e = dict(ev)
        t = parse_utc(ev["utc"])
        lt = t.astimezone(tz)
        if ev.get("fixed_date"):
            d = date.fromisoformat(ev["fixed_date"])
        elif ev.get("night"):
            d = (lt - timedelta(hours=12)).date()  # the evening that starts the night
            d2 = d + timedelta(days=1)
            e["night_label"] = f"night of {d.day}–{d2.day}" if d.month == d2.month else \
                f"night of {d.strftime('%b')} {d.day}–{d2.strftime('%b')} {d2.day}"
            o = observer(city, t)
            sun_alt = alt_of(ephem.Sun(), o)
            when = f"peak {lt.strftime('%b')} {lt.day} {lt.strftime('%H:%M')}"
            e["night_label"] += f" · {when}" + (" (daylight here; nights either side are similar)" if sun_alt > -6 else "")
        else:
            d = lt.date()
        e["local_date"] = d.isoformat()
        e["local_time"] = lt.strftime("%H:%M") if ev.get("timed", True) and not ev.get("night") else None

        if ev.get("folk") and city[1] < 0:
            e["folk"] = southern_folk(t, ev["folk"])
        if ev["cat"] == "eclipse":
            if ev.get("kind") == "solar":
                r = solar_eclipse_local(city, t, tz)
                if r:
                    e["local_note"] = (f"From {city[0]}: {r['kind']} — {round(r['mag'] * 100)}% of the Sun's "
                                       f"diameter covered at {r['local_max']} ({r['start']}–{r['end']})")
                    e["local_visible"] = True
                else:
                    e["local_note"] = f"Not visible from {city[0]}"
                    e["local_visible"] = False
            else:
                alt = lunar_eclipse_local(city, t)
                e["local_visible"] = alt > 0
                e["local_note"] = (f"From {city[0]}: Moon {alt:.0f}° up at mid-eclipse" if alt > 0
                                   else f"Moon below the horizon from {city[0]}")
        if ev.get("local_check"):
            r = star_pass_local(city, ev, tz)
            if not r:
                continue
            lt = r["when"].astimezone(tz)
            e["local_date"] = lt.date().isoformat()
            tgt = ev["target"].split(" (")[0]
            if r["kind"] == "occultation":
                e["name"] = f"Moon occults {ev['target']}"
                e["short"] = f"Occults {tgt}"
                e["local_time"] = r["start"]
                e["local_note"] = f"Visible from {city[0]}: {r['start']}–{r['end']} · {ev['note']}"
                e["occultation"] = True
            else:
                e["name"] = f"Moon {r['sep']}° from {ev['target']}"
                e["short"] = f"Moon–{tgt} {r['sep']}°"
                e["local_time"] = r["local"]
                e["local_note"] = f"Seen from {city[0]} at {r['local']} · {ev['note']}"
            for k in ("ra", "dec", "when"):
                e.pop(k, None)
        out.append(e)

    year = events_doc["year"]
    # nightly illumination at 21:00 local
    illum = {}
    d = date(year, 1, 1)
    while d.year == year:
        illum[d.isoformat()] = round(illum_at(datetime(d.year, d.month, d.day, 21, 0, tzinfo=tz)))
        d += timedelta(days=1)

    months = {}
    for m in range(1, 13):
        ndays = calendar.monthrange(year, m)[1]
        dark = [illum[date(year, m, k).isoformat()] <= 25 for k in range(1, ndays + 1)]
        windows, start = [], None
        for k, ok in enumerate(dark + [False], start=1):
            if ok and start is None:
                start = k
            if not ok and start is not None:
                windows.append((start, k - 1))
                start = None
        tr, alt = target_highest(city, m, tz, year, targets.get(m))
        months[m] = dict(dark_windows=windows, transit=tr, transit_alt=alt)

    out.sort(key=lambda e: (e["local_date"], e.get("local_time") or "99"))
    return dict(code=code, edition=ed, tz=ed["tz"], events=out, illum=illum, months=months,
                month_notes=events_doc.get("month_notes", {}), year=year)


def run(codes=None):
    """Localise the print editions (or any CITIES codes); month targets follow data/selection.json."""
    import os
    util.require_tzdata()
    doc = util.read_json(os.path.join(util.HERE, "data", "events_utc.json"))
    sel = util.selection()
    targets = {int(k): (v["ra"], v["dec"]) for k, v in sel.items() if k != "cover"}
    for code in codes or EDITIONS:
        loc = localize(doc, code, targets)
        util.write_json(os.path.join(util.HERE, "data", f"edition_{code}.json"), loc, default=str)
        occ = [e for e in loc["events"] if e.get("occultation")]
        ecl = [e for e in loc["events"] if e["cat"] == "eclipse" and e.get("kind") == "solar"]
        print(f"{code:6} events={len(loc['events']):3} occultations={len(occ):2} | "
              + " | ".join(f"{e['local_date'][5:]} {e['local_note']}" for e in ecl))


if __name__ == "__main__":
    util.utf8_stdio()
    run()
