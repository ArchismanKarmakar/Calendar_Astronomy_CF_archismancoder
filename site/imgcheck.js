/* Checks a picture against the calendar page it is meant for: file type, size, pixel
   count, print resolution for the page and paper, how much is cropped away, whether
   the light text printed over it stays readable, blown highlights, softness and
   compression. Pure functions (no DOM) so they can be tested in Node. */
"use strict";
(function (root) {
  // trim sizes in points (1/72 in) — the same numbers as kit/build.py PAPERS and LAYOUT
  const PAPERS = { ISO: { wall: [841.89, 1190.55], desk: [595.28, 419.53] }, US: { wall: [792, 1224], desk: [612, 396] } };
  const WALL_PHOTO = 0.5, DESK_PANEL = 0.46;

  /** Photo area of a page in inches, and where the page's light text sits over it
      (fractions of that area). */
  function zone(format, paper, slot) {
    const [tw, th] = PAPERS[paper][format];
    if (slot === "cover") return { w: tw / 72, h: th / 72, text: [0.05, 0.25, 0.95, 0.85], label: "cover" };
    if (format === "wall") return { w: tw / 72, h: (th * WALL_PHOTO) / 72, text: [0, 0, 0.8, 0.55], label: "photo half of the page" };
    return { w: (tw * DESK_PANEL) / 72, h: th / 72, text: [0, 0, 1, 1], label: "photo panel" };
  }

  /** Pixels per inch the picture prints at when it fills the area (cover) or sits in
      a full-width band (panorama). */
  function ppi(w, h, z, fit) {
    if (!w || !h) return 0;
    if (fit === "band") return Math.min(w / z.w, h / (z.h * 0.74));
    return Math.min(w / z.w, h / z.h);
  }
  /** Share of the picture still visible after it is cropped to fill the area. */
  function keep(w, h, z) {
    const a = w / h, b = z.w / z.h;
    return Math.min(a / b, b / a);
  }

  /* ---------------------------------------------------------------- file headers */
  function sniff(b) {
    const s = (o, str) => [...str].every((c, i) => b[o + i] === c.charCodeAt(0));
    if (b[0] === 0xff && b[1] === 0xd8 && b[2] === 0xff) return "jpeg";
    if (b[0] === 0x89 && s(1, "PNG")) return "png";
    if (s(0, "RIFF") && s(8, "WEBP")) return "webp";
    if ((s(0, "II") && b[2] === 42) || (s(0, "MM") && b[3] === 42)) return "tiff";
    if (s(4, "ftyp")) {
      const brand = String.fromCharCode(...b.slice(8, 12));
      if (/avif|avis/.test(brand)) return "avif";
      if (/hei|mif1|msf1|heix|hevc/.test(brand)) return "heic";
    }
    if (s(0, "GIF8")) return "gif";
    if (s(0, "BM")) return "bmp";
    return "unknown";
  }
  /** {w, h, depth, alpha} from the header, already turned upright for JPEG EXIF orientation. */
  function header(b, type) {
    const u16 = (o, le) => (le ? b[o] | (b[o + 1] << 8) : (b[o] << 8) | b[o + 1]);
    const u32 = (o) => ((b[o] << 24) | (b[o + 1] << 16) | (b[o + 2] << 8) | b[o + 3]) >>> 0;
    if (type === "png") {
      const ct = b[25];
      let alpha = ct === 4 || ct === 6;
      // a tRNS chunk also makes some pixels transparent
      for (let o = 8; o + 8 < Math.min(b.length, 1 << 20);) {
        const len = u32(o), typ = String.fromCharCode(b[o + 4], b[o + 5], b[o + 6], b[o + 7]);
        if (typ === "tRNS") alpha = true;
        if (typ === "IDAT") break;
        o += 12 + len;
      }
      return { w: u32(16), h: u32(20), depth: b[24], alpha };
    }
    if (type === "jpeg") {
      let o = 2, orient = 1, w = 0, h = 0, cmyk = false;
      while (o + 9 < b.length) {
        if (b[o] !== 0xff) { o++; continue; }
        const m = b[o + 1];
        if (m === 0xd8 || (m >= 0xd0 && m <= 0xd7) || m === 0x01) { o += 2; continue; }
        const len = u16(o + 2);
        if (m === 0xe1 && String.fromCharCode(...b.slice(o + 4, o + 8)) === "Exif") {
          const t = o + 10, le = b[t] === 0x49;
          const ifd = t + ((le ? (b[t + 4] | (b[t + 5] << 8) | (b[t + 6] << 16) | (b[t + 7] << 24)) : u32(t + 4)) >>> 0);
          const n = u16(ifd, le);
          for (let i = 0; i < n && ifd + 2 + i * 12 + 10 < b.length; i++) {
            const e = ifd + 2 + i * 12;
            if (u16(e, le) === 0x0112) orient = u16(e + 8, le);
          }
        }
        if ((m >= 0xc0 && m <= 0xc3) || (m >= 0xc5 && m <= 0xc7) || (m >= 0xc9 && m <= 0xcb) || (m >= 0xcd && m <= 0xcf)) {
          h = u16(o + 5); w = u16(o + 7); cmyk = b[o + 9] === 4;
          break;
        }
        o += 2 + len;
      }
      if (orient >= 5 && orient <= 8) [w, h] = [h, w];
      return { w, h, depth: 8, alpha: false, orient, cmyk };
    }
    if (type === "webp") {
      const kind = String.fromCharCode(b[12], b[13], b[14], b[15]);
      if (kind === "VP8 ") return { w: u16(26, true) & 0x3fff, h: u16(28, true) & 0x3fff, depth: 8, alpha: false };
      if (kind === "VP8L") {
        const v = b[21] | (b[22] << 8) | (b[23] << 16) | (b[24] << 24);
        return { w: (v & 0x3fff) + 1, h: ((v >> 14) & 0x3fff) + 1, depth: 8, alpha: !!((v >> 28) & 1) };
      }
      if (kind === "VP8X") {
        return { w: 1 + (b[24] | (b[25] << 8) | (b[26] << 16)), h: 1 + (b[27] | (b[28] << 8) | (b[29] << 16)), depth: 8, alpha: !!(b[20] & 0x10) };
      }
    }
    return { w: 0, h: 0, depth: 8, alpha: false };
  }

  /* ---------------------------------------------------------------- pixel measures */
  const luma = (r, g, b) => (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
  /** Brightness of an RGBA image (any size; a ~1500 px copy is plenty), overall and in
      the text area (fractions x0,y0,x1,y1 of the cropped photo area). */
  function tones(rgba, w, h, textBox, cropFrac) {
    // the part of the picture that ends up on the page, centred
    const [cw, ch] = cropFrac;
    const ox = Math.round((w * (1 - cw)) / 2), oy = Math.round((h * (1 - ch)) / 2);
    const vw = Math.max(1, Math.round(w * cw)), vh = Math.max(1, Math.round(h * ch));
    const [x0, y0, x1, y1] = textBox;
    const hist = new Uint32Array(256), histT = new Uint32Array(256);
    let n = 0, nT = 0, clip = 0, gray = 0;
    const step = Math.max(1, Math.floor(Math.sqrt((vw * vh) / 400000)));
    for (let y = oy; y < oy + vh; y += step) {
      const ty = (y - oy) / vh, inY = ty >= y0 && ty <= y1;
      for (let x = ox; x < ox + vw; x += step) {
        const i = (y * w + x) * 4, r = rgba[i], g = rgba[i + 1], b = rgba[i + 2];
        const l = Math.round(luma(r, g, b) * 255);
        hist[l]++; n++;
        if (r >= 254 || g >= 254 || b >= 254) clip++;
        if (Math.abs(r - g) < 6 && Math.abs(g - b) < 6) gray++;
        const tx = (x - ox) / vw;
        if (inY && tx >= x0 && tx <= x1) { histT[l]++; nT++; }
      }
    }
    const q = (hs, tot, p) => { let c = 0; for (let i = 0; i < 256; i++) { c += hs[i]; if (c >= tot * p) return i / 255; } return 1; };
    const over = (hs, tot, t) => { let c = 0; for (let i = Math.ceil(t * 255); i < 256; i++) c += hs[i]; return tot ? c / tot : 0; };
    return {
      median: q(hist, n, 0.5), p99: q(hist, n, 0.99), bright: over(hist, n, 0.5),
      textMedian: q(histT, nT || 1, 0.5), textBright: over(histT, nT, 0.5),
      clip: n ? clip / n : 0, gray: n ? gray / n : 0,
    };
  }
  /** Fine detail at full resolution compared with half resolution, on a square crop
      (grey values). Sharp photos and noisy ones: 0.25–1; enlarged or blurred: below ~0.16. */
  function detail(g, c) {
    const lapVar = (a, s) => {
      let sum = 0, sq = 0, n = 0;
      for (let y = 1; y < s - 1; y++) for (let x = 1; x < s - 1; x++) {
        const i = y * s + x;
        const v = 4 * a[i] - a[i - 1] - a[i + 1] - a[i - s] - a[i + s];
        sum += v; sq += v * v; n++;
      }
      return n ? sq / n - (sum / n) ** 2 : 0;
    };
    const half = c >> 1, B = new Float32Array(half * half);
    for (let y = 0; y < half; y++) for (let x = 0; x < half; x++) {
      const i = 2 * y * c + 2 * x;
      B[y * half + x] = (g[i] + g[i + 1] + g[i + c] + g[i + c + 1]) / 4;
    }
    const vb = lapVar(B, half);
    return vb < 1e-3 ? 1 : lapVar(g, c) / vb;
  }

  /* ---------------------------------------------------------------- verdicts */
  const MB = 1e6;
  const fmtPpi = (v) => `${Math.round(v)} ppi`;
  /** info: {type, bytes, w, h, depth, alpha, cmyk, tones, detail, fit, format, paper, slot, dpi, paperName}
      Returns [{id, level: pass|warn|fail, title, detail}]. */
  function evaluate(info) {
    const out = [];
    const add = (id, level, title, d) => out.push({ id, level, title, detail: d });
    const okType = ["jpeg", "png", "webp"].includes(info.type);
    if (!okType) {
      const name = { tiff: "TIFF", heic: "HEIC (iPhone)", avif: "AVIF", gif: "GIF", bmp: "BMP" }[info.type] || "this kind of file";
      add("type", "fail", `File type: ${name}`, "Only JPEG, PNG and WebP can be used. Export or save the photo as a high-quality JPEG first.");
      return out;
    }
    add("type", "pass", `File type: ${info.type.toUpperCase()}`, info.type === "webp" ? "Converted to JPEG on your device before use." : "");
    if (info.bytes > 120 * MB) add("size", "fail", `File size: ${(info.bytes / MB).toFixed(0)} MB`, "Over the 120 MB limit. Save a smaller JPEG (quality 90–95 is plenty).");
    else add("size", "pass", `File size: ${(info.bytes / MB).toFixed(1)} MB`, "");
    const mp = (info.w * info.h) / 1e6;
    if (!info.w || !info.h) { add("decode", "fail", "Couldn't read the picture", "The file may be damaged. Save it again as a JPEG and retry."); return out; }
    const limit = info.type === "jpeg" ? 150 : 60;
    if (mp > limit) add("pixels", "fail", `${info.w.toLocaleString()} × ${info.h.toLocaleString()} px (${mp.toFixed(0)} MP)`,
      `Too large for a browser to process (limit ${limit} MP${info.type === "jpeg" ? "" : " for PNG and WebP; JPEGs can be larger"}). Resize it to about 8000 px on the long side.`);
    else if (mp > 80) add("pixels", "warn", `${info.w.toLocaleString()} × ${info.h.toLocaleString()} px (${mp.toFixed(0)} MP)`, "Very large: building the calendar will be slow and needs a desktop browser.");
    else add("pixels", "pass", `${info.w.toLocaleString()} × ${info.h.toLocaleString()} px`, "");

    const z = zone(info.format, info.paper, info.slot);
    const p = ppi(info.w, info.h, z, info.fit);
    const where = `the ${info.paperName} ${z.label} (${z.w.toFixed(1)} × ${z.h.toFixed(1)} in)`;
    if (p < 120) add("ppi", "fail", `Print resolution: ${fmtPpi(p)}`, `Too small for ${where}: it would print visibly blurry and pixelated. It needs at least ${Math.ceil(120 * z.w).toLocaleString()} × ${Math.ceil(120 * z.h * (info.fit === "band" ? 0.74 : 1)).toLocaleString()} px.`);
    else if (p < 180) add("ppi", "warn", `Print resolution: ${fmtPpi(p)}`, `Usable on ${where}, but soft up close. 200 ppi or more looks sharp.`);
    else add("ppi", "pass", `Print resolution: ${fmtPpi(p)}`, `Sharp on ${where}.` + (info.dpi > p ? ` Pages are drawn at ${info.dpi} dpi, so the photo is enlarged a little.` : ""));

    if (info.fit === "band") {
      add("crop", "pass", "Shape: panorama band", "Shown whole as a full-width band across the photo area.");
    } else {
      const k = keep(info.w, info.h, z);
      const ar = info.w / info.h;
      if (k < 0.45) add("crop", "warn", `Shape: ${Math.round(k * 100)}% of the picture stays visible`,
        ar > 2.2 ? "This is a wide panorama; most of it would be cut off. Switch on “Panorama band” below to show it whole."
          : "Much of the picture is cut away to fill the area. Check the preview, or choose a picture closer to the page's shape.");
      else add("crop", "pass", `Shape: ${Math.round(k * 100)}% of the picture stays visible`, k < 0.7 ? "The edges are trimmed to fill the area; the centre is kept." : "");
    }

    const t = info.tones;
    if (t) {
      const tm = t.textMedian, tb = t.textBright;
      if ((tm > 0.5 && tb > 0.5) || t.median > 0.55) add("light", "fail", "Too bright for the calendar's text",
        "The month name, dates and events are printed in light colours over the photo. On a picture this bright they can't be read. Use a night-sky photo with a dark background.");
      else if (tm > 0.38 || tb > 0.4) add("light", "warn", "Bright behind the text",
        "The area where the month name sits is bright, so the text will be harder to read. Check the preview.");
      else if (t.p99 < 0.04) add("light", "warn", "Almost entirely black",
        "Very little is visible. Check the exposure, or brighten the photo before using it.");
      else add("light", "pass", "Dark enough for light text", "");
      if (t.clip > 0.08) add("clip", "warn", `${Math.round(t.clip * 100)}% of the picture is pure white`,
        "Large blown-out areas print as flat white patches.");
    }
    if (info.detail != null && p < 2 * Math.max(info.dpi, 200)) {
      if (info.detail < 0.16) add("detail", "warn", "Looks soft or enlarged",
        "The finest detail is missing at full size, as happens with blurred or upscaled pictures. At this print size that softness will show.");
      else add("detail", "pass", "Fine detail looks real", "");
    }
    if (info.type === "jpeg" && mp > 4 && info.bytes / (info.w * info.h) < 0.06) {
      add("jpeg", "warn", "Heavily compressed JPEG", "It may show blocky areas in smooth gradients. A higher-quality export would print better.");
    }
    if (info.alpha) add("alpha", "warn", "Has transparent areas", "Transparent parts print as black.");
    if (info.depth === 16) add("depth", "pass", "16-bit image", "Converted to 8 bits per channel for printing.");
    if (info.cmyk) add("cmyk", "pass", "CMYK colours", "Converted to RGB; colours may shift slightly.");
    return out;
  }
  /** Print check for a picture whose pixel size is known (no file needed). */
  function quickPpi(w, h, fit, format, paper, slot) {
    return ppi(w, h, zone(format, paper, slot), fit);
  }

  const api = { PAPERS, zone, ppi, keep, sniff, header, tones, detail, evaluate, quickPpi };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.ImgCheck = api;
})(typeof self !== "undefined" ? self : this);
