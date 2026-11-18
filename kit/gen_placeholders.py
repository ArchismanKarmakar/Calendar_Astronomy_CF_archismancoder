"""
Procedural stand-in art (domain-warped fBm nebula + PSF stars), used ONLY
until the real ESO / ESA-Hubble images are fetched. Every page that renders
with one of these prints "PLACEHOLDER" in its credit line, so a draft can't
be shipped by accident.
"""
import json
import os

import numpy as np
from scipy.ndimage import gaussian_filter
from PIL import Image, ImageFilter

W, H = 3600, 2400
OUT = "photos/_placeholder"
os.makedirs(OUT, exist_ok=True)

PAL = {  # (shadow, mid, highlight) per slot — loosely echoing the real object
    "cover": [(6, 8, 22), (150, 60, 40), (250, 200, 150)],
    "01": [(8, 6, 20), (180, 50, 90), (255, 190, 140)],
    "02": [(4, 8, 22), (40, 110, 200), (220, 120, 160)],
    "03": [(6, 6, 12), (60, 60, 90), (240, 220, 190)],
    "04": [(5, 6, 16), (60, 90, 170), (255, 200, 160)],
    "05": [(5, 5, 10), (90, 80, 110), (255, 235, 200)],
    "06": [(4, 5, 12), (70, 90, 150), (255, 240, 210)],
    "07": [(10, 5, 14), (200, 60, 80), (255, 170, 190)],
    "08": [(10, 8, 6), (150, 110, 70), (120, 190, 220)],
    "09": [(6, 6, 12), (110, 100, 130), (255, 225, 180)],
    "10": [(5, 6, 16), (80, 100, 180), (240, 200, 230)],
    "11": [(4, 6, 18), (40, 150, 170), (240, 110, 80)],
    "12": [(6, 6, 16), (60, 120, 200), (255, 150, 90)],
}


def fbm(shape, rng, octaves=6, base=4):
    h, w = shape
    acc = np.zeros(shape, np.float32)
    amp, tot = 1.0, 0.0
    for o in range(octaves):
        n = base * 2 ** o
        g = rng.standard_normal((n + 1, int(n * w / h) + 2)).astype(np.float32)
        img = Image.fromarray(g).resize((w, h), Image.BICUBIC)
        acc += amp * np.asarray(img)
        tot += amp
        amp *= 0.55
    acc /= tot
    return (acc - acc.min()) / (acc.max() - acc.min() + 1e-6)


def warp(field, dx, dy, k):
    h, w = field.shape
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    xs = np.clip(xx + (dx - 0.5) * k, 0, w - 1).astype(np.int32)
    ys = np.clip(yy + (dy - 0.5) * k, 0, h - 1).astype(np.int32)
    return field[ys, xs]


def make(slot, seed):
    rng = np.random.default_rng(seed)
    sh = (H // 3, W // 3)
    n = fbm(sh, rng)
    n = warp(n, fbm(sh, rng, 4), fbm(sh, rng, 4), 220)
    # filaments: ridged noise
    r = 1 - np.abs(fbm(sh, rng, 6, 6) * 2 - 1)
    neb = np.clip((n - 0.38) * 1.9, 0, 1) ** 1.4
    fil = np.clip(r - 0.72, 0, 1) * 3.2 * neb
    yy, xx = np.mgrid[0:sh[0], 0:sh[1]]
    cx, cy = rng.uniform(0.35, 0.65) * sh[1], rng.uniform(0.35, 0.6) * sh[0]
    vign = np.exp(-(((xx - cx) / (0.55 * sh[1])) ** 2 + ((yy - cy) / (0.6 * sh[0])) ** 2))
    t = np.clip(neb * 1.15 * vign + fil * 0.6, 0, 1)
    lo, mid, hi = (np.array(c, np.float32) for c in PAL[slot])
    rgb = (lo[None, None] * (1 - t[..., None]) + mid[None, None] * t[..., None])
    rgb += (hi - mid)[None, None] * (np.clip(t - 0.55, 0, 1) / 0.45)[..., None] ** 1.5
    img = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8)).resize((W, H), Image.BICUBIC)
    img = img.filter(ImageFilter.GaussianBlur(1.2))
    # stars with a small Gaussian PSF
    a = np.asarray(img).astype(np.float32)
    stars = np.zeros((H, W), np.float32)
    nstars = 9000
    xs, ys = rng.integers(0, W, nstars), rng.integers(0, H, nstars)
    mags = rng.pareto(2.2, nstars) * 0.18 + 0.05
    stars[ys, xs] = np.clip(mags, 0, 6)
    s1 = gaussian_filter(stars, 1.1)
    s2 = gaussian_filter(stars * (stars > 1.5), 7) * 0.6
    glow = (s1 * 255 * 9.0 + s2 * 255 * 4.0)[..., None]
    tint = np.array([1.0, 0.97, 1.05], np.float32)[None, None]
    a = 255 - (255 - a) * np.exp(-glow * tint / 255)
    Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).save(f"{OUT}/{slot}.jpg", quality=90)


if __name__ == "__main__":
    for i, slot in enumerate(PAL):
        make(slot, 2027 + i * 17)
        print("placeholder", slot)
