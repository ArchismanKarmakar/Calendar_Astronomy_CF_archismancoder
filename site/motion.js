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
