"""
Public holidays for 2027 from the open-source `holidays` package (python-holidays),
in English where it has translations. Used by build.py (--holidays) and by
make_site.py, which saves one small file per country for the website.

Dates of holidays that follow a lunar calendar or moon sighting (Eid, etc.) are the
package's estimates and are marked "(est.)" — official dates can differ by a day.
"""
import re

LATIN = re.compile(r"[\x00-ɏ’‘–—]*")

# city code -> (country, subdivision) for the website's 63 cities
CITY_COUNTRY = {
    "US-PT": ("US", None), "US-MT": ("US", None), "US-AZ": ("US", None), "US-CT": ("US", None),
    "US-ET": ("US", None), "US-HI": ("US", None), "US-AK": ("US", None), "CA-PT": ("CA", "BC"),
    "CA-ET": ("CA", "ON"), "MX": ("MX", None), "CO": ("CO", None), "PE": ("PE", None), "BR": ("BR", None),
    "AR": ("AR", None), "CL": ("CL", None), "CL-N": ("CL", None), "UK": ("GB", "ENG"), "IE": ("IE", None),
    "PT": ("PT", None), "ES": ("ES", None), "FR": ("FR", None), "CET": ("DE", None), "NL": ("NL", None),
    "IT": ("IT", None), "CH": ("CH", "ZH"), "PL": ("PL", None), "SE": ("SE", None), "FI": ("FI", None),
    "GR": ("GR", None), "TR": ("TR", None), "RU": ("RU", None), "EG": ("EG", None), "NG": ("NG", None),
    "KE": ("KE", None), "ZA": ("ZA", None), "NA": ("NA", None), "IL": ("IL", None), "SA": ("SA", None),
    "AE": ("AE", None), "IR": ("IR", None), "PK": ("PK", None), "IN": ("IN", None), "IN-MUM": ("IN", None),
    "IN-KOL": ("IN", None), "IN-BLR": ("IN", None), "IN-LEH": ("IN", None), "LK": ("LK", None),
    "NP": ("NP", None), "BD": ("BD", None), "TH": ("TH", None), "SG": ("SG", None), "ID": ("ID", None),
    "PH": ("PH", None), "CN": ("CN", None), "HK": ("HK", None), "TW": ("TW", None), "KR": ("KR", None),
    "JP": ("JP", None), "AU-W": ("AU", "WA"), "AU-SA": ("AU", "SA"), "AU-Q": ("AU", "QLD"), "AU-E": ("AU", "NSW"),
    "NZ": ("NZ", None),
}


# Local corrections on top of the package's data.
OVERRIDES = {
    "IN": {
        "add": {"01-23": "Netaji Subhas Chandra Bose's Birthday"},   # Parakram Diwas
        "rename": {"Mahatma Gandhi's Birthday": "Gandhi's Birthday"},
    },
}


# Regional festival sets, printed in their own colour (not public holidays).
# 2027 dates: Saraswati Puja and Maha Saptami from West Bengal's regional holiday lists
# (officeholidays.com), Ashtami and Kojagari from panchang tithi rules, Navami/Dashami
# following on, Bishwakarma Puja on Kanya Sankranti (computed: 17 Sep 2027, 13:58 IST).
FESTIVALS = {
    "bengali": dict(name="Bengali festivals", country="IN", days={
        "2027-02-11": "Saraswati Puja",
        "2027-09-17": "Bishwakarma Puja",
        "2027-10-06": "Durga Puja · Maha Saptami",
        "2027-10-07": "Durga Puja · Maha Ashtami",
        "2027-10-08": "Durga Puja · Maha Navami",
        "2027-10-09": "Bijoya Dashami",
        "2027-10-14": "Kojagari Lakshmi Puja",
    }),
}
# editions that show a festival set by default
CITY_FESTIVALS = {"IN": "bengali", "IN-KOL": "bengali"}


def festivals_for(code_or_key):
    """(name, {date: name}) for a city code (its default set) or a set key, else None."""
    key = CITY_FESTIVALS.get(code_or_key, code_or_key)
    f = FESTIVALS.get(key)
    return (f["name"], dict(f["days"])) if f else None


def _apply_overrides(country, days, year):
    o = OVERRIDES.get(country)
    if not o:
        return days
    out = {}
    for d, name in days.items():
        out[d] = " / ".join(o.get("rename", {}).get(n, n) for n in name.split(" / "))
    for md, name in o.get("add", {}).items():
        d = f"{year}-{md}"
        out[d] = name if d not in out else (out[d] if name in out[d] else f"{out[d]} / {name}")
    return dict(sorted(out.items()))


def _tidy(name):
    name = re.sub(r"\s*\(estimated\)", " (est.)", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def country_names():
    """{'IN': 'India', ...} for every country the package covers."""
    from holidays import registry
    out = {}
    for _, v in registry.COUNTRIES.items():
        cls, code = v[0], v[1]
        out[code] = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", cls).replace(" And ", " and ").replace(" Of ", " of ")
    return out


def holidays_for(country, subdiv=None, year=2027):
    """{'2027-01-26': 'Republic Day', ...} in English, or None if unavailable."""
    import holidays
    for lang in ("en_US", "en_GB", None):
        try:
            kw = dict(years=year)
            if subdiv:
                kw["subdiv"] = subdiv
            if lang:
                kw["language"] = lang
            h = holidays.country_holidays(country, **kw)
        except (NotImplementedError, KeyError, ValueError):
            if subdiv:
                return holidays_for(country, None, year)
            continue
        days = {d.isoformat(): " / ".join(_tidy(n) for n in name.split("; ")) for d, name in sorted(h.items())}
        if days and all(LATIN.fullmatch(n) for n in days.values()):
            return _apply_overrides(country, days, year)
    return None


def for_city(code, year=2027):
    cc, sub = CITY_COUNTRY.get(code, (None, None))
    if not cc:
        return None, None
    return cc, holidays_for(cc, sub, year)
