"""
Raster backgrounds. Each page's photo is composited once per paper size and
reused by every time-zone edition (text and icons are vector, drawn later).

The "blend": the sharp photo sits in its zone and dissolves into a blurred,
darkened copy of the same image that fills the rest of the page, so the
picture visibly continues behind the date grid.
"""
import io
import math
import os

import numpy as np
from PIL import Image, ImageCms, ImageFilter, ImageOps
from scipy import ndimage as ndi

Image.MAX_IMAGE_PIXELS = None  # Hubble mosaics are legitimately huge
INK = np.array([7, 9, 15], np.float32)


def load_srgb(path, need_px):
    im = Image.open(path)
    if im.format == "JPEG":
        im.draft("RGB", (need_px, need_px))  # fast DCT downscale for giant sources
    im = ImageOps.exif_transpose(im)
    icc = im.info.get("icc_profile")
    if icc:
        try:
            src = ImageCms.ImageCmsProfile(io.BytesIO(icc))
            im = ImageCms.profileToProfile(im, src, ImageCms.createProfile("sRGB"), outputMode="RGB")
        except Exception:
            pass
    return im.convert("RGB")


def cover_fit(im, w, h, focus=(0.5, 0.5)):
    sw, sh = im.size
    s = max(w / sw, h / sh)
    nw, nh = max(w, round(sw * s)), max(h, round(sh * s))
    im = im.resize((nw, nh), Image.LANCZOS)
    x = min(max(0, round(focus[0] * nw - w / 2)), nw - w)
    y = min(max(0, round(focus[1] * nh - h / 2)), nh - h)
    return im.crop((x, y, x + w, y + h)), s


def blurred_base(im, w, h, dark=0.40, sat=0.75):
    small, _ = cover_fit(im, max(32, w // 10), max(32, h // 10))
    small = small.filter(ImageFilter.GaussianBlur(radius=max(4, w // 160)))
    a = np.asarray(small).astype(np.float32)
    lum = a.mean(axis=2, keepdims=True)
    a = lum + (a - lum) * sat
    a = a * dark + INK * (1 - dark)
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).resize((w, h), Image.BICUBIC)


def ramp(n, start, end, a0, a1, curve=1.0):
    """1-D alpha ramp over pixel index range [start, end)."""
    v = np.zeros(n, np.float32)
    v[:max(0, start)] = a0
    if end > start:
        t = np.clip((np.arange(n) - start) / (end - start), 0, 1)
        t = 0.5 - 0.5 * np.cos(np.pi * t) if curve == "cos" else t ** curve
        v[start:] = (a0 + (a1 - a0) * t)[start:]
    v[end:] = a1
    return v


def scrim(img, alpha):
    a = np.asarray(img).astype(np.float32)
    al = alpha[..., None] if alpha.ndim == 2 else alpha
    out = a * (1 - al) + INK * al
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))


def _lum(a):
    return a[..., 0] * 0.2126 + a[..., 1] * 0.7152 + a[..., 2] * 0.0722


def auto_focus(im):
    """Where the subject is: centroid of the brightest extended light after
    blurring away stars. Returns (fx, fy) in 0..1."""
    sm = im.copy()
    sm.thumbnail((384, 384))
    L = _lum(np.asarray(sm).astype(np.float32))
    L = ndi.gaussian_filter(L, sigma=max(2.0, 0.04 * min(L.shape)))
    thr = np.percentile(L, 98.5)
    ys, xs = np.nonzero(L >= thr)
    w = L[ys, xs] - thr + 1e-3
    return float((xs * w).sum() / w.sum() / L.shape[1]), float((ys * w).sum() / w.sum() / L.shape[0])


def best_window(im, w, h):
    """Centre (fx, fy) of the w x h output window (after cover scaling) that
    holds the most extended light: a galaxy pair or a nebula is framed as a
    whole instead of averaging two bright spots into empty sky between them."""
    sw, sh = im.size
    sc = max(w / sw, h / sh)
    cw, ch = min(1.0, w / (sw * sc)), min(1.0, h / (sh * sc))
    if cw > 0.97 and ch > 0.97:
        return 0.5, 0.5
    # a wide crop keeps the author's own framing on that axis
    fx0 = 0.5 if cw > 0.6 else None
    fy0 = 0.5 if ch > 0.6 else None
    if fx0 is not None and fy0 is not None:
        return fx0, fy0
    sm = im.copy()
    sm.thumbnail((256, 256))
    L = _lum(np.asarray(sm).astype(np.float32))
    L = ndi.gaussian_filter(L, sigma=max(1.5, 0.02 * min(L.shape)))
    L = np.clip(L - np.percentile(L, 30), 0, None) ** 1.3
    hh, ww = L.shape
    bw, bh = max(1, round(cw * ww)), max(1, round(ch * hh))
    I = np.pad(L.cumsum(0).cumsum(1), ((1, 0), (1, 0)))
    S = I[bh:, bw:] - I[:-bh, bw:] - I[bh:, :-bw] + I[:-bh, :-bw]
    # gentle preference for the middle of the picture (the author's framing)
    yy, xx = np.mgrid[0:S.shape[0], 0:S.shape[1]]
    cx, cy = (xx + bw / 2) / ww - 0.5, (yy + bh / 2) / hh - 0.5
    S = S * (1 - 0.9 * (cx ** 2 + cy ** 2))
    y, x = np.unravel_index(np.argmax(S), S.shape)
    fx, fy = (x + bw / 2) / ww, (y + bh / 2) / hh
    return (fx0 if fx0 is not None else fx), (fy0 if fy0 is not None else fy)


def resolve_focus(im, focus, w=None, h=None):
    if focus and focus[0] is not None:
        return tuple(focus)
    if w and h:
        return best_window(im, w, h)
    return auto_focus(im)


def galaxy_axis(im):
    """Angle (degrees, image coordinates), elongation and centre of the brightest
    extended object, from second moments of the smoothed light."""
    sm = im.copy()
    sm.thumbnail((420, 420))
    L = ndi.gaussian_filter(_lum(np.asarray(sm).astype(np.float32)), max(2.0, 0.015 * min(sm.size)))
    w = np.clip(L - np.percentile(L, 85), 0, None)
    tot = w.sum()
    if tot <= 0:
        return 0.0, 1.0, (0.5, 0.5)
    yy, xx = np.mgrid[0:L.shape[0], 0:L.shape[1]].astype(np.float32)
    cx, cy = (w * xx).sum() / tot, (w * yy).sum() / tot
    mxx = (w * (xx - cx) ** 2).sum() / tot
    myy = (w * (yy - cy) ** 2).sum() / tot
    mxy = (w * (xx - cx) * (yy - cy)).sum() / tot
    theta = 0.5 * np.degrees(np.arctan2(2 * mxy, mxx - myy))
    tr, det = mxx + myy, mxx * myy - mxy ** 2
    l1 = tr / 2 + np.sqrt(max(0.0, tr * tr / 4 - det))
    l2 = max(1e-6, tr / 2 - np.sqrt(max(0.0, tr * tr / 4 - det)))
    return float(theta), float(np.sqrt(l1 / l2)), (cx / L.shape[1], cy / L.shape[0])


def orient(im, zone_w, zone_h, mode):
    """rotate="auto": turn an elongated galaxy so it lies along the longer side of the
    photo area, then keep the largest rectangle of that shape with no empty corners.
    A number rotates by that many degrees (counter-clockwise). Returns (image, degrees)."""
    if not mode:
        return im, 0.0
    if mode == "auto":
        theta, elong, _ = galaxy_axis(im)
        if elong < 1.5:
            return im, 0.0
        ang = theta + (90.0 if zone_h > zone_w else 0.0)
    else:
        ang = float(mode)
    ang = (ang + 90.0) % 180.0 - 90.0
    if abs(ang) < 4:
        return im, 0.0
    rot = im.rotate(ang, resample=Image.BICUBIC, expand=True, fillcolor=(0, 0, 0))
    # largest centred rectangle with the zone's aspect that has no empty corners
    W, H = rot.size
    a = math.radians(abs(ang))
    sw, sh = im.size
    r = zone_w / zone_h
    lo, hi = 0.0, min(W, H * r)
    for _ in range(40):
        w = (lo + hi) / 2
        h = w / r
        # corners of the centred w x h box, mapped back into the source frame
        ok = True
        for dx, dy in ((w / 2, h / 2), (w / 2, -h / 2)):
            x = abs(dx * math.cos(a) - dy * math.sin(a))
            y = abs(dx * math.sin(a) + dy * math.cos(a))
            if x > sw / 2 or y > sh / 2:
                ok = False
        lo, hi = (w, hi) if ok else (lo, w)
    w, h = lo, lo / r
    box = (round(W / 2 - w / 2), round(H / 2 - h / 2), round(W / 2 + w / 2), round(H / 2 + h / 2))
    return rot.crop(box), ang


def rotation_for(src_path, zone_w, zone_h, mode):
    """The angle orient() will apply (0 if none), without rendering anything."""
    if not mode:
        return 0.0
    if mode != "auto":
        a = (float(mode) + 90.0) % 180.0 - 90.0
        return 0.0 if abs(a) < 4 else a
    im = load_srgb(src_path, 900)
    theta, elong, _ = galaxy_axis(im)
    if elong < 1.5:
        return 0.0
    a = (theta + (90.0 if zone_h > zone_w else 0.0) + 90.0) % 180.0 - 90.0
    return 0.0 if abs(a) < 4 else a


def mosaic_mask(im):
    """Boolean thumbnail mask of real picture area for mosaics with pure-black
    gaps reaching the frame edge (e.g. Hubble's Andromeda panoramas), or None
    for normal photographs."""
    sm = im.copy()
    sm.thumbnail((1200, 1200))
    L = _lum(np.asarray(sm).astype(np.float32))
    black = L < 5.0
    border = np.concatenate([black[0], black[-1], black[:, 0], black[:, -1]])
    if black.mean() < 0.03 or border.mean() < 0.12:  # gaps must reach the frame edge
        return None
    k = max(3, int(0.012 * min(L.shape)))
    keep = ndi.binary_opening(~black, iterations=2)
    keep = ndi.binary_closing(keep, structure=np.ones((k, k)))
    # fill only specks: real astrophotos have no large pure-black pockets
    lab, n = ndi.label(~keep)
    if n:
        sizes = ndi.sum(np.ones_like(lab), lab, index=np.arange(1, n + 1))
        small = np.zeros(n + 1, bool)
        small[1:] = sizes < 0.0006 * L.size
        keep = keep | small[lab]
    return keep


def mosaic_alpha(im):
    """Soft alpha that dissolves a mosaic's saw-toothed tile edges into the sky:
    blur the mask at tooth scale, keep what is solidly inside (the line through
    the valleys of the teeth), then feather that smooth envelope."""
    keep = mosaic_mask(im)
    if keep is None:
        return None
    m = min(keep.shape)
    soft = ndi.gaussian_filter(keep.astype(np.float32), max(2.0, 0.035 * m))
    inner = (soft > 0.93).astype(np.float32)
    a = ndi.gaussian_filter(inner, max(2.0, 0.03 * m))
    a = np.clip((a - 0.5) / 0.5, 0, 1)
    a = a * a * (3 - 2 * a)
    return Image.fromarray((a * 255).astype(np.uint8)).resize(im.size, Image.BICUBIC)


def soft_ellipse(W, H, cx, cy, rx, ry, strength):
    yy, xx = np.mgrid[0:H:8, 0:W:8]
    d = ((xx - cx * W) / (rx * W)) ** 2 + ((yy - cy * H) / (ry * H)) ** 2
    e = (np.exp(-d * 1.6) * strength).astype(np.float32)
    return np.asarray(Image.fromarray((e * 255).astype(np.uint8)).resize((W, H), Image.BICUBIC)) / 255.0


def band_window(im, fx, fy, out_w, out_h, zoom=1.0, min_frac=0.62):
    """Source crop for a panorama band: the central 1/zoom of the width around the
    subject, rows centred on the subject (a galaxy's core) so it is never cut through.
    For mosaics with black, saw-toothed edges, the rows stay inside the solid picture
    around the core, zooming in until the band is at least min_frac of out_h tall.
    Returns (box, band height in output pixels)."""
    sw, sh = im.size
    keep = mosaic_mask(im)
    zoom = max(1.0, zoom)
    for _ in range(40):
        cw = sw / zoom
        x0 = min(max(0.0, fx * sw - cw / 2), sw - cw)
        lo, hi = 0.0, float(sh)
        if keep is not None:
            kh, kw = keep.shape
            c0, c1 = int(x0 / sw * kw), max(int(x0 / sw * kw) + 1, int((x0 + cw) / sw * kw))
            ok = (1 - keep[:, c0:c1].mean(1)) < 0.03
            r = min(kh - 1, max(0, int(fy * kh)))
            if ok[r]:
                a = r
                while a > 0 and ok[a - 1]:
                    a -= 1
                b = r
                while b < kh - 1 and ok[b + 1]:
                    b += 1
                lo, hi = a / kh * sh, (b + 1) / kh * sh
        ch = min(hi - lo, cw * out_h / out_w)
        if keep is None or out_w * ch / cw >= min_frac * out_h or zoom > 8:
            break
        zoom *= 1.12
    cy = min(max(fy * sh, lo + ch / 2), hi - ch / 2)
    y0 = min(max(0.0, cy - ch / 2), sh - ch)
    return (round(x0), round(y0), round(x0 + cw), round(y0 + ch)), max(8, round(out_w * ch / cw))


def place_band(base, im, Wpx, max_h, center_y, fx, fy, zoom=1.0, min_frac=0.62):
    """Paste a panorama as a full-width band centred on center_y. Top and bottom fade
    into the (dark) base; a mosaic's black, saw-toothed tile edges dissolve into the
    sky instead of showing."""
    box, h = band_window(im, fx, fy, Wpx, max_h, zoom, min_frac)
    s = Wpx / (box[2] - box[0])
    band = sharpen_if_downscaled(im.crop(box).resize((Wpx, h), Image.LANCZOS), s)
    f = max(8, int(h * 0.24))
    m = ramp(h, 0, f, 0, 1, "cos") * ramp(h, h - f, h, 1, 0, "cos")
    alpha = np.repeat(m[:, None], Wpx, 1)
    mo = mosaic_alpha(band)
    if mo is not None:
        alpha = alpha * (np.asarray(mo, dtype=np.float32) / 255.0)
    top = max(0, round(center_y - h / 2))
    base.paste(band, (0, top), Image.fromarray((alpha * 255).astype(np.uint8)))
    return base


def sharpen_if_downscaled(im, scale):
    if scale < 0.9:
        return im.filter(ImageFilter.UnsharpMask(radius=1.0, percent=55, threshold=2))
    return im


def wall_month(src_path, Wpx, Hpx, photo_px, fit="cover", focus=None, zoom=1.0, rotate=None):
    im = load_srgb(src_path, max(Wpx, photo_px) * (2 if fit == "band" else 1))
    if fit != "band":
        im, _ = orient(im, Wpx, photo_px, rotate)
    fx, fy = resolve_focus(im, focus, *((None, None) if fit == "band" else (Wpx, photo_px)))
    mosaic = fit == "band" or mosaic_mask(im) is not None
    # panoramas and mosaics sit on near-black sky: a blurred copy of a wide, bright
    # galaxy would leave grey haze and soft blobs around the band
    base = blurred_base(im, Wpx, Hpx, dark=0.08 if mosaic else 0.40)
    if fit == "band":
        fx, fy = resolve_focus(im, focus)
        place_band(base, im, Wpx, int(photo_px * 0.74), photo_px * 0.50, fx, fy, zoom)
    else:
        sharp, s = cover_fit(im, Wpx, photo_px, (fx, fy))
        sharp = sharpen_if_downscaled(sharp, s)
        m = ramp(photo_px, int(photo_px * 0.74), photo_px, 1, 0, "cos")
        alpha = np.repeat(m[:, None], Wpx, 1)
        mo = mosaic_alpha(sharp)
        if mo is not None:
            alpha = alpha * (np.asarray(mo) / 255.0)
        base.paste(sharp, (0, 0), Image.fromarray((alpha * 255).astype(np.uint8)))
    # legibility: strong header gradient + a soft pool behind the month title,
    # then the grid zone darkens so text below the photo always reads.
    top = ramp(Hpx, 0, int(Hpx * 0.25), 0.74, 0.0, "cos")
    grid = ramp(Hpx, int(photo_px * 0.84), int(photo_px * 1.05), 0.0, 0.62, "cos")
    bottom = ramp(Hpx, int(Hpx * 0.80), Hpx, 0.0, 0.18, "cos")
    alpha = np.repeat(np.clip(top + grid + bottom, 0, 0.92)[:, None], Wpx, 1)
    alpha = np.clip(alpha + soft_ellipse(Wpx, Hpx, 0.30, 0.085, 0.42, 0.075, 0.30)
                    + soft_ellipse(Wpx, Hpx, 0.80, photo_px / Hpx * 0.985, 0.30, 0.03, 0.45), 0, 0.94)
    return scrim(base, alpha.astype(np.float32))


def desk_month(src_path, Wpx, Hpx, panel_px, fit="cover", focus=None, zoom=1.0, rotate=None):
    im = load_srgb(src_path, max(panel_px, Hpx) * (3 if fit == "band" else 1))
    if fit != "band":
        im, _ = orient(im, panel_px, Hpx, rotate)
    fx, fy = resolve_focus(im, focus, *((None, None) if fit == "band" else (panel_px, Hpx)))
    mosaic = fit == "band" or mosaic_mask(im) is not None
    base = blurred_base(im, Wpx, Hpx, dark=0.08 if mosaic else 0.30)
    panel = Image.new("RGB", (panel_px, Hpx))
    panel.paste(base.crop((0, 0, panel_px, Hpx)))
    if fit == "band":
        fx, fy = resolve_focus(im, focus)
        # a narrow panel: zoom further so the galaxy's core fills it
        place_band(panel, im, panel_px, int(Hpx * 0.70), Hpx * 0.42, fx, fy, max(zoom, 2.4), min_frac=0.9)
        sharp = panel
    else:
        sharp, s = cover_fit(im, panel_px, Hpx, (fx, fy))
        sharp = sharpen_if_downscaled(sharp, s)
        mo = mosaic_alpha(sharp)
        if mo is not None:
            panel.paste(sharp, (0, 0), mo)
            sharp = panel
    m = ramp(panel_px, int(panel_px * 0.70), panel_px, 1, 0, "cos")
    mask = Image.fromarray((np.repeat(m[None, :], Hpx, 0) * 255).astype(np.uint8))
    base.paste(sharp, (0, 0), mask)
    horiz = ramp(Wpx, int(panel_px * 0.82), int(panel_px * 1.05), 0.0, 0.64, "cos")
    vert = ramp(Hpx, int(Hpx * 0.50), Hpx, 0.0, 0.62, "cos")
    head = ramp(Hpx, 0, int(Hpx * 0.14), 0.55, 0.0, "cos")
    left_only = (np.arange(Wpx) < panel_px * 1.02).astype(np.float32)
    alpha = np.clip(horiz[None, :] + (vert + head)[:, None] * left_only[None, :], 0, 0.9)
    return scrim(base, alpha.astype(np.float32))


def full_bleed(src_path, Wpx, Hpx, focus=None, top=0.55, bottom=0.86, bottom_from=0.52, desk=False, rotate=None):
    im = load_srgb(src_path, max(Wpx, Hpx))
    im, _ = orient(im, Wpx, Hpx, rotate)
    img, s = cover_fit(im, Wpx, Hpx, resolve_focus(im, focus, Wpx, Hpx))
    img = sharpen_if_downscaled(img, s)
    a = ramp(Hpx, 0, int(Hpx * 0.30), top, 0, "cos") + ramp(Hpx, int(Hpx * bottom_from), Hpx, 0, bottom, "cos")
    a = np.repeat(np.clip(a, 0, 0.95)[:, None], Wpx, 1)
    # a soft dark pool behind the title block keeps it legible on busy nebulae
    a = np.clip(a + soft_ellipse(Wpx, Hpx, 0.5, 0.33 if desk else 0.39, 0.55, 0.16, 0.42), 0, 0.95)
    return scrim(img, a.astype(np.float32))


def dark_plate(src_path, Wpx, Hpx):
    im = load_srgb(src_path, 1200)
    base = blurred_base(im, Wpx, Hpx, dark=0.22, sat=0.6)
    yy, xx = np.mgrid[0:Hpx:8, 0:Wpx:8]
    v = ((xx / Wpx - 0.5) ** 2 + (yy / Hpx - 0.35) ** 2) ** 0.5
    vig = np.clip((v - 0.25) * 0.9, 0, 0.5).astype(np.float32)
    vig = np.asarray(Image.fromarray((vig * 255).astype(np.uint8)).resize((Wpx, Hpx), Image.BICUBIC)) / 255
    return scrim(base, vig.astype(np.float32))


def effective_dpi(src_path, zone_w_in, zone_h_in):
    with Image.open(src_path) as im:
        w, h = im.size
    return min(w / zone_w_in, h / zone_h_in) if zone_h_in else w / zone_w_in
