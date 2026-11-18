"""
Pure-Python sky helpers with no PyEphem dependency, so the website can run them in
the browser (Pyodide): the meridian transit of a month's target, and southern-
hemisphere full-moon names. localize.py uses the same functions.
"""
import math
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

UTC = timezone.utc


# Northern folk names follow the northern seasons; south of the equator the usual
# convention shifts them by six months, and the Harvest Moon is the full moon
# nearest the March equinox.
_FOLK = ["Wolf Moon", "Snow Moon", "Worm Moon", "Pink Moon", "Flower Moon", "Strawberry Moon", "Buck Moon",
         "Sturgeon Moon", "Harvest Moon", "Hunter's Moon", "Beaver Moon", "Cold Moon"]
_MAR_EQ = datetime(2027, 3, 20, 14, 25, tzinfo=UTC)


def southern_folk(t, north_name):
    if abs((t - _MAR_EQ).total_seconds()) < 16 * 86400:
        return "Harvest Moon"
    if north_name == "Harvest Moon":
        return _FOLK[(t.month + 5) % 12] if t.month != 3 else "Worm Moon"
    return _FOLK[(t.month + 5) % 12]


def gmst_deg(t):
    """Greenwich mean sidereal time in degrees (IAU 1982; good to ~0.1 s this century)."""
    jd = t.timestamp() / 86400.0 + 2440587.5
    d = jd - 2451545.0
    T = d / 36525.0
    return (280.46061837 + 360.98564736629 * d + 0.000387933 * T * T - T ** 3 / 38710000.0) % 360.0


def _hms(s):
    s = str(s).strip().replace("h", ":").replace("m", ":").replace("s", "").replace("°", ":").replace("'", ":") \
        .replace('"', "").replace(" ", ":")
    parts = [p for p in s.split(":") if p != ""]
    sign = -1 if parts[0].startswith("-") else 1
    v = [abs(float(p)) for p in parts] + [0, 0]
    return sign * (v[0] + v[1] / 60 + v[2] / 3600)


def transit_simple(lat, lon, tzname, month, ra, dec, year=2027):
    """Pure-Python twin of target_highest (no PyEphem, so it runs in the browser):
    local time when the target crosses the meridian after noon on the 15th, and its
    altitude then. Agrees with PyEphem to about a minute and a degree."""
    tz = ZoneInfo(tzname)
    ra_deg, dec_deg = _hms(ra) * 15.0, _hms(dec)
    t0 = datetime(year, month, 15, 12, 0, tzinfo=tz).astimezone(UTC)
    # precess RA roughly from J2000 to the date (~50.3"/yr in longitude)
    yrs = year - 2000 + (month - 0.5) / 12
    ra_deg += yrs * (3.075 + 1.336 * math.sin(math.radians(ra_deg)) * math.tan(math.radians(dec_deg))) * 15 / 3600
    lst = (gmst_deg(t0) + lon) % 360
    dt_days = ((ra_deg - lst) % 360) / 360.98564736629
    tt = t0 + timedelta(days=dt_days)
    alt = 90 - abs(lat - dec_deg)
    if alt > 0:  # refraction, as PyEphem applies it
        alt += 1.02 / math.tan(math.radians(alt + 10.3 / (alt + 5.11))) / 60
    return tt.astimezone(tz).strftime("%H:%M"), round(alt)
