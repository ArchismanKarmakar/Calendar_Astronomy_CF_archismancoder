/* Motion for the landing page: a live starfield behind the hero, a word-by-word headline,
   calendar pages that fan out as you scroll, scroll reveals, a cursor spotlight on cards
   and a nav that firms up on scroll. Everything is skipped or held still when the
   visitor asks for reduced motion. */
"use strict";
(() => {
  const root = document.documentElement;
  const still = matchMedia("(prefers-reduced-motion: reduce)");
  root.classList.add("js");

  /* ---------------------------------------------------------- headline words */
  const h1 = document.querySelector(".hero h1");
  if (h1 && !still.matches) {
    const words = h1.textContent.split(" ");
    h1.setAttribute("aria-label", h1.textContent);
    h1.innerHTML = "";
    words.forEach((w, i) => {
      const o = document.createElement("span");
      o.className = "w";
      o.setAttribute("aria-hidden", "true");
      const s = document.createElement("span");
      s.textContent = w;
      if (/2027/.test(w)) o.classList.add("g");  // the year shimmers
      s.style.animationDelay = `${0.08 + i * 0.07}s`;
      o.append(s);
      h1.append(o, i < words.length - 1 ? " " : "");
    });
    h1.classList.add("split");
    h1.classList.remove("reveal");
  }

  /* ---------------------------------------------------------- starfield */
  const cv = document.querySelector(".stars");
  if (cv) {
    const cx = cv.getContext("2d");
    let W = 0, H = 0, dpr = 1, stars = [], meteor = null, nextMeteor = 3000, last = 0, running = false, mx = 0, my = 0, tx = 0, ty = 0;
    let figure = null, nextFigure = 1200;
    /* a "constellation": a short chain of bright stars near each other, drawn line by line */
    function makeFigure() {
      const bright = stars.filter((s) => s.z > 0.55 && s.x > W * 0.05 && s.x < W * 0.95 && s.y < H * 0.7);
      if (bright.length < 6) return null;
      let cur = bright[Math.floor(Math.random() * bright.length)];
      const chain = [cur], used = new Set([cur]);
      const reach = Math.max(90, Math.min(W, H) * 0.2);
      for (let k = 0; k < 6; k++) {
        const near = bright.filter((s) => !used.has(s) && Math.hypot(s.x - cur.x, s.y - cur.y) < reach)
          .sort((a, b) => Math.hypot(a.x - cur.x, a.y - cur.y) - Math.hypot(b.x - cur.x, b.y - cur.y));
        if (!near.length) break;
        cur = near[Math.min(near.length - 1, Math.floor(Math.random() * 2))];
        chain.push(cur); used.add(cur);
      }
      return chain.length >= 4 ? { chain, t: 0 } : null;
    }
    const colour = () => (root.dataset.theme === "red" ? [212, 42, 30] : null);
    function size() {
      const r = cv.getBoundingClientRect();
      dpr = Math.min(2, window.devicePixelRatio || 1);
      W = r.width; H = r.height;
      cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr);
      const n = Math.round(Math.min(420, (W * H) / 3800));
      stars = Array.from({ length: n }, () => {
        const z = Math.random();
        const tint = Math.random();
        return { x: Math.random() * W, y: Math.random() * H, z, r: 0.35 + z * z * 1.5,
          a: 0.25 + z * 0.7, tw: 0.5 + Math.random() * 2.2, ph: Math.random() * 6.28,
          c: tint < 0.12 ? [255, 214, 170] : tint < 0.26 ? [170, 200, 255] : [255, 255, 255] };
      });
    }
    function draw(t) {
      const dt = Math.min(64, t - last); last = t;
      tx += (mx - tx) * 0.04; ty += (my - ty) * 0.04;
      cx.setTransform(dpr, 0, 0, dpr, 0, 0);
      cx.clearRect(0, 0, W, H);
      const red = colour();
      for (const s of stars) {
        if (!still.matches) { s.x -= 0.004 * dt * (0.2 + s.z); if (s.x < -2) s.x = W + 2; }
        const px = s.x + tx * s.z * 18, py = s.y + ty * s.z * 12;
        const tw = still.matches ? 1 : 0.65 + 0.35 * Math.sin(t / 1000 * s.tw + s.ph);
        const [r, g, b] = red || s.c;
        cx.fillStyle = `rgba(${r},${g},${b},${s.a * tw})`;
        cx.beginPath(); cx.arc(px, py, s.r, 0, 6.283); cx.fill();
        if (s.r > 1.4) { cx.fillStyle = `rgba(${r},${g},${b},${0.08 * tw})`; cx.beginPath(); cx.arc(px, py, s.r * 3.2, 0, 6.283); cx.fill(); }
      }
      if (!still.matches) {
        nextFigure -= dt;
        if (!figure && nextFigure < 0) { figure = makeFigure(); nextFigure = 9000 + Math.random() * 5000; }
        if (figure) {
          figure.t += dt;
          const segs = figure.chain.length - 1, draw = 2600, hold = 2600, fade = 1400;
          const shown = Math.min(segs, (figure.t / draw) * segs);
          const al = figure.t < draw + hold ? 1 : Math.max(0, 1 - (figure.t - draw - hold) / fade);
          const [r, g, b] = red || [233, 188, 112];
          cx.strokeStyle = `rgba(${r},${g},${b},${0.42 * al})`; cx.lineWidth = 0.9; cx.lineCap = "round";
          cx.beginPath();
          const P = (s) => [s.x + tx * s.z * 18, s.y + ty * s.z * 12];
          let [x0, y0] = P(figure.chain[0]); cx.moveTo(x0, y0);
          for (let i = 0; i < Math.ceil(shown); i++) {
            const [ax, ay] = P(figure.chain[i]), [bx, by] = P(figure.chain[i + 1]);
            const f = Math.min(1, shown - i);
            cx.lineTo(ax + (bx - ax) * f, ay + (by - ay) * f);
          }
          cx.stroke();
          for (let i = 0; i <= Math.floor(shown); i++) {  // the joined stars brighten
            const [px, py] = P(figure.chain[i]);
            cx.fillStyle = `rgba(${r},${g},${b},${0.22 * al})`; cx.beginPath(); cx.arc(px, py, 5, 0, 6.283); cx.fill();
          }
          if (figure.t > draw + hold + fade) figure = null;
        }
        nextMeteor -= dt;
        if (!meteor && nextMeteor < 0) {
          meteor = { x: W * (0.25 + Math.random() * 0.7), y: H * Math.random() * 0.35, v: 0.75 + Math.random() * 0.4, life: 0 };
          nextMeteor = 6000 + Math.random() * 9000;
        }
        if (meteor) {
          meteor.life += dt;
          const k = meteor.life / 900, len = 140;
          const x = meteor.x - meteor.life * meteor.v, y = meteor.y + meteor.life * meteor.v * 0.45;
          const gr = cx.createLinearGradient(x, y, x + len, y - len * 0.45);
          const [r, g, b] = red || [255, 255, 255];
          const al = Math.sin(Math.min(1, k) * Math.PI) * 0.85;
          gr.addColorStop(0, `rgba(${r},${g},${b},${al})`); gr.addColorStop(1, `rgba(${r},${g},${b},0)`);
          cx.strokeStyle = gr; cx.lineWidth = 1.3; cx.lineCap = "round";
          cx.beginPath(); cx.moveTo(x, y); cx.lineTo(x + len, y - len * 0.45); cx.stroke();
          if (k >= 1) meteor = null;
        }
      }
      if (running) requestAnimationFrame(draw);
    }
    const start = () => { if (!running && !still.matches) { running = true; last = performance.now(); requestAnimationFrame(draw); } };
    const stop = () => { running = false; };
    size();
    draw(performance.now());
    new ResizeObserver(() => { size(); if (!running) draw(performance.now()); }).observe(cv);
    new IntersectionObserver(([e]) => (e.isIntersecting && !document.hidden ? start() : stop())).observe(cv);
    document.addEventListener("visibilitychange", () => (document.hidden ? stop() : start()));
    window.addEventListener("pointermove", (e) => { mx = e.clientX / innerWidth - 0.5; my = e.clientY / innerHeight - 0.5; }, { passive: true });
    new MutationObserver(() => { if (!running) draw(performance.now()); }).observe(root, { attributes: true, attributeFilter: ["data-theme"] });
  }

  /* ---------------------------------------------------------- fan of pages */
  const fan = document.querySelector(".fan");
  if (fan) {  // dealt out from one stack, then it follows scroll and pointer briskly
    const deal = () => { fan.classList.add("dealt"); setTimeout(() => fan.classList.add("settled"), 1700); };
    if (still.matches) { fan.classList.add("dealt", "settled"); }
    else setTimeout(() => requestAnimationFrame(deal), 380);
  }
  const heroIn = document.querySelector(".hero");
  const nav = document.querySelector(".nav-wrap");
  let ticking = false;
  function onScroll() {
    ticking = false;
    const y = scrollY;
    nav && nav.classList.toggle("scrolled", y > 24);
    if (fan && !still.matches) {
      const r = fan.getBoundingClientRect();
      const p = Math.max(0, Math.min(1, 1 - r.top / innerHeight));
      fan.style.setProperty("--spread", p.toFixed(3));
      // the headline lifts away as the stage takes over
      if (heroIn) heroIn.style.setProperty("--lift", Math.max(0, Math.min(1, y / (innerHeight * 0.8))).toFixed(3));
    }
  }
  addEventListener("scroll", () => { if (!ticking) { ticking = true; requestAnimationFrame(onScroll); } }, { passive: true });
  onScroll();
  if (fan && !still.matches && matchMedia("(hover: hover)").matches) {
    fan.addEventListener("pointermove", (e) => {
      const r = fan.getBoundingClientRect();
      fan.style.setProperty("--rx", ((e.clientX - r.left) / r.width - 0.5).toFixed(3));
      fan.style.setProperty("--ry", ((e.clientY - r.top) / r.height - 0.5).toFixed(3));
    });
    fan.addEventListener("pointerleave", () => { fan.style.setProperty("--rx", 0); fan.style.setProperty("--ry", 0); });
  }

  /* ---------------------------------------------------------- scroll progress line */
  const prog = document.createElement("div");
  prog.className = "scroll-line";
  prog.setAttribute("aria-hidden", "true");
  document.body.append(prog);
  addEventListener("scroll", () => {
    const max = document.documentElement.scrollHeight - innerHeight;
    prog.style.transform = `scaleX(${max > 0 ? Math.min(1, scrollY / max) : 0})`;
  }, { passive: true });

  /* ---------------------------------------------------------- 3D tilt: the maker's page and calendar cards */
  if (!still.matches && matchMedia("(hover: hover)").matches) {
    const tilt = (host, target, k = 1) => {
      host.addEventListener("pointermove", (e) => {
        const r = host.getBoundingClientRect();
        const t = typeof target === "function" ? target() : target;
        if (!t) return;
        t.style.setProperty("--tx", (((e.clientX - r.left) / r.width - 0.5) * k).toFixed(3));
        t.style.setProperty("--ty", (((e.clientY - r.top) / r.height - 0.5) * k).toFixed(3));
      });
      host.addEventListener("pointerleave", () => {
        const t = typeof target === "function" ? target() : target;
        if (t) { t.style.setProperty("--tx", 0); t.style.setProperty("--ty", 0); }
      });
    };
    const st = document.querySelector("#stage");
    if (st) tilt(st, () => document.querySelector("#stage-page"));
    document.addEventListener("pointerover", (e) => {
      const card = e.target.closest && e.target.closest(".ed");
      if (card && !card.dataset.tilt) { card.dataset.tilt = "1"; tilt(card, card, 0.6); }
    });
  }

  /* ---------------------------------------------------------- sample strip drifts as you scroll past */
  const strip = document.querySelector("#strip");
  if (strip && !still.matches) {
    addEventListener("scroll", () => {
      const r = strip.getBoundingClientRect();
      if (r.bottom < 0 || r.top > innerHeight) return;
      const p = (innerHeight - r.top) / (innerHeight + r.height);
      strip.style.setProperty("--drift", `${(0.5 - p) * 60}px`);
    }, { passive: true });
  }

  /* ---------------------------------------------------------- look inside: arrow buttons */
  const sp = document.querySelector("#strip"), prev = document.querySelector("#strip-prev"), next = document.querySelector("#strip-next");
  if (sp && prev && next) {
    const sync = () => {
      prev.disabled = sp.scrollLeft < 8;
      next.disabled = sp.scrollLeft + sp.clientWidth >= sp.scrollWidth - 8;
    };
    const go = (d) => sp.scrollBy({ left: d * sp.clientWidth * 0.8, behavior: still.matches ? "auto" : "smooth" });
    prev.addEventListener("click", () => go(-1));
    next.addEventListener("click", () => go(1));
    sp.addEventListener("scroll", sync, { passive: true });
    new ResizeObserver(sync).observe(sp);
    new MutationObserver(() => { sp.scrollLeft = 0; sync(); }).observe(sp, { childList: true });
  }

  /* ---------------------------------------------------------- scroll reveals */
  const groups = [".section .head", ".editions", ".strip", ".bento", ".maker", ".donate", ".faq", ".after", ".ticker"];
  const io = new IntersectionObserver((es) => es.forEach((e) => {
    if (!e.isIntersecting) return;
    e.target.classList.add("in");
    io.unobserve(e.target);
  }), { rootMargin: "0px 0px -8% 0px", threshold: 0.08 });
  function watch() {
    document.querySelectorAll(groups.join(",")).forEach((el) => {
      if (el.dataset.rv) return;
      el.dataset.rv = "1";
      el.classList.add("rv");
      [...el.children].forEach((c, i) => c.style.setProperty("--d", `${Math.min(i, 8) * 70}ms`));
      if (still.matches) el.classList.add("in"); else io.observe(el);
    });
  }
  watch();
  // editions, donate cards and the ticker are drawn later by app.js
  new MutationObserver(() => document.querySelectorAll(".rv").forEach((el) =>
    [...el.children].forEach((c, i) => c.style.getPropertyValue("--d") || c.style.setProperty("--d", `${Math.min(i, 8) * 70}ms`))))
    .observe(document.querySelector("main") || document.body, { childList: true, subtree: true });

  /* ---------------------------------------------------------- spotlight on cards */
  document.addEventListener("pointermove", (e) => {
    const card = e.target.closest && e.target.closest(".tile, .ed, .give");
    if (!card) return;
    const r = card.getBoundingClientRect();
    card.style.setProperty("--mx", `${e.clientX - r.left}px`);
    card.style.setProperty("--my", `${e.clientY - r.top}px`);
  }, { passive: true });

  /* ---------------------------------------------------------- nav: current section */
  const links = [...document.querySelectorAll(".nav-links a[href^='#']")];
  const secs = links.map((a) => document.querySelector(a.getAttribute("href"))).filter(Boolean);
  const spy = new IntersectionObserver((es) => es.forEach((e) => {
    if (!e.isIntersecting) return;
    links.forEach((a) => a.classList.toggle("here", a.getAttribute("href") === `#${e.target.id}`));
  }), { rootMargin: "-45% 0px -50% 0px" });
  secs.forEach((s) => spy.observe(s));
})();
