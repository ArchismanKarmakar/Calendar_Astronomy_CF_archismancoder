#!/usr/bin/env python3
"""
Download the three open-licence (SIL OFL) font families from the Google Fonts
repository and create the static weights the renderer embeds:
  Fraunces (display serif, optical size 144 for headlines, 72 for titles),
  Geist (text, Light..Bold), Geist Mono (times and figures).
Each instance gets a unique internal name so PDF viewers never confuse weights.
Requires: pip install fonttools
"""
import os
import urllib.request

from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "fonts")
BASE = "https://raw.githubusercontent.com/google/fonts/main/ofl"
SRC = {
    "Fraunces-VF.ttf": "fraunces/Fraunces%5BSOFT,WONK,opsz,wght%5D.ttf",
    "Geist-VF.ttf": "geist/Geist%5Bwght%5D.ttf",
    "GeistMono-VF.ttf": "geistmono/GeistMono%5Bwght%5D.ttf",
}
# stem -> (variable font, family name, [(style, axis location)])
INSTANCES = {
    "Geist": ("Geist-VF.ttf", "Geist", [(n, {"wght": w}) for n, w in
                                        [("Light", 300), ("Regular", 400), ("Medium", 500), ("SemiBold", 600), ("Bold", 700)]]),
    "GeistMono": ("GeistMono-VF.ttf", "Geist Mono", [("Regular", {"wght": 400}), ("Medium", {"wght": 500})]),
    "Fraunces": ("Fraunces-VF.ttf", "Fraunces", [
        ("Display", {"opsz": 144, "wght": 420, "SOFT": 0, "WONK": 0}),      # month names
        ("DisplayLight", {"opsz": 144, "wght": 300, "SOFT": 0, "WONK": 0}),  # the cover year
        ("Title", {"opsz": 72, "wght": 560, "SOFT": 0, "WONK": 0}),          # object names, page titles
    ]),
}


def rename(t, family, sub):
    ps = f"{family.replace(' ', '')}-{sub}"
    n = t["name"]
    for nid in (1, 2, 3, 4, 6, 16, 17, 25):
        n.removeNames(nameID=nid)
    for nid, val in {1: f"{family} {sub}", 2: "Regular", 3: f"cal27:{ps}", 4: f"{family} {sub}", 6: ps,
                     16: family, 17: sub}.items():
        n.setName(val, nid, 3, 1, 0x409)
        n.setName(val, nid, 1, 0, 0)


def main():
    os.makedirs(OUT, exist_ok=True)
    for dst, src in SRC.items():
        path = os.path.join(OUT, dst)
        if not os.path.exists(path):
            print("download", dst)
            urllib.request.urlretrieve(f"{BASE}/{src}", path)
    for stem, (vf, family, styles) in INSTANCES.items():
        for sub, loc in styles:
            if os.path.exists(os.path.join(OUT, f"{stem}-{sub}.ttf")):
                continue
            inst = instancer.instantiateVariableFont(TTFont(os.path.join(OUT, vf)), loc)
            rename(inst, family, sub)
            inst.save(os.path.join(OUT, f"{stem}-{sub}.ttf"))
            print("instance", f"{stem}-{sub}.ttf")


if __name__ == "__main__":
    main()
