/* Decorative work has a budget; scrolling and document interaction take priority. */
(() => {
  if (window.__psFx) return;
  window.__psFx = true;
  const start = () => {
    const canvas = document.createElement('canvas');
    canvas.id = 'ps-fx'; canvas.setAttribute('aria-hidden', 'true');
    document.body.prepend(canvas);
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    const motion = matchMedia('(prefers-reduced-motion: reduce)'), root = document.documentElement;
    const hues = [190, 255, 285, 320], rand = (a, b) => a + Math.random() * (b - a);
    // Cache glow sprites instead of computing a shadow/gradient for every particle.
    function sprite(hue, size, opacity) {
      const image = document.createElement('canvas'); image.width = image.height = size;
      const c = image.getContext('2d'), r = size / 2;
      const g = c.createRadialGradient(r, r, 0, r, r, r);
      g.addColorStop(0, `hsla(${hue},95%,85%,${opacity})`);
      g.addColorStop(.2, `hsla(${hue},90%,72%,${opacity * .3})`);
      g.addColorStop(1, `hsla(${hue},90%,70%,0)`);
      c.fillStyle = g; c.fillRect(0, 0, size, size); return image;
    }
    const stars = hues.map(hue => sprite(hue, 24, .9)), pointerGlow = sprite(255, 96, .12);
    let w = 0, h = 0, nodes = [], sparks = [], meteors = [];
    let timer = 0, frame = 0, resizeTimer = 0, scrollTimer = 0;
    let previous = 0, nextMeteor = 0, scrolling = false, overlay = false, fps = 24, slowFrames = 0;
    const mouse = {x: -1e4, y: -1e4};
    const paused = () => motion.matches || document.hidden || scrolling || overlay;
    const cancel = () => { clearTimeout(timer); cancelAnimationFrame(frame); timer = frame = 0; };
    function schedule() {
      if (paused() || timer || frame) return;
      timer = setTimeout(() => { timer = 0; if (!paused()) frame = requestAnimationFrame(draw); }, 1000 / fps);
    }
    function sync() {
      cancel(); previous = 0;
      root.classList.toggle('ps-effects-paused', paused());
      canvas.dataset.state = document.hidden ? 'hidden' : scrolling ? 'scrolling' : overlay ? 'overlay' : motion.matches ? 'static' : 'animating';
      schedule();
    }
    function resize() {
      // Decorative stars do not need text-resolution rendering. Cap the backing
      // store even on 4K/HiDPI displays; the UI itself retains native resolution.
      w = innerWidth; h = innerHeight;
      const scale = Math.min(devicePixelRatio || 1, 1, Math.sqrt(1200000 / Math.max(1, w * h)));
      canvas.width = Math.max(1, Math.floor(w * scale)); canvas.height = Math.max(1, Math.floor(h * scale));
      ctx.setTransform(scale, 0, 0, scale, 0, 0);
      nodes = Array.from({length: Math.min(48, Math.round(w * h / 24000))}, () => ({
        x: rand(0, w), y: rand(0, h), vx: rand(-.16, .16), vy: rand(-.16, .16),
        r: rand(.6, 2), color: Math.random() * 4 | 0, tw: rand(0, Math.PI * 2),
      }));
      canvas.dataset.particles = nodes.length; canvas.dataset.pixels = canvas.width * canvas.height; canvas.dataset.fpsLimit = fps;
      draw(0, true); sync();
    }
    function draw(t, once = false) {
      frame = 0;
      if (!once && paused()) return;
      const started = performance.now(), dt = once ? 0 : Math.min((t - previous) / 16.667 || 1, 4);
      previous = t;
      ctx.clearRect(0, 0, w, h); ctx.globalCompositeOperation = 'lighter';
      if (!motion.matches && mouse.x > -1e3) ctx.drawImage(pointerGlow, Math.round(mouse.x - 240), Math.round(mouse.y - 240), 480, 480);
      for (const p of nodes) {
        p.x += p.vx * dt; p.y += p.vy * dt;
        if (p.x < -20) p.x = w + 20; else if (p.x > w + 20) p.x = -20;
        if (p.y < -20) p.y = h + 20; else if (p.y > h + 20) p.y = -20;
        const dx = p.x - mouse.x, dy = p.y - mouse.y, d2 = dx * dx + dy * dy;
        if (dt && d2 < 25600) { const d = Math.sqrt(d2) || 1, f = (1 - d / 160) * 1.2 * dt; p.x += dx / d * f; p.y += dy / d * f; }
      }
      ctx.lineWidth = .6;
      for (let i = 0; i < nodes.length; i++) {
        const a = nodes[i], hue = hues[a.color];
        for (let j = i + 1; j < nodes.length; j++) {
          const b = nodes[j], dx = a.x - b.x, dy = a.y - b.y, d2 = dx * dx + dy * dy;
          if (d2 < 24000) { ctx.strokeStyle = `hsla(${hue},90%,70%,${(1 - d2 / 24000) * .18})`; ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke(); }
        }
        const mx = a.x - mouse.x, my = a.y - mouse.y, m2 = mx * mx + my * my;
        if (!motion.matches && m2 < 36000) { ctx.strokeStyle = `hsla(${hue},95%,72%,${(1 - m2 / 36000) * .35})`; ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(mouse.x, mouse.y); ctx.stroke(); }
        ctx.globalAlpha = .5 + .25 * Math.sin(t * .0008 + a.tw);
        ctx.drawImage(stars[a.color], Math.round(a.x - 8), Math.round(a.y - 8), 16, 16);
      }
      ctx.globalAlpha = 1;
      if (!once && t > nextMeteor) { meteors.push({x: rand(w * .2, w), y: rand(-80, h * .4), life: 1}); nextMeteor = t + rand(5000, 10000); }
      for (const p of meteors) {
        p.x -= 5 * dt; p.y += 2.4 * dt; p.life -= .012 * dt;
        if (p.life <= 0) continue;
        const trail = ctx.createLinearGradient(p.x, p.y, p.x + 100, p.y - 48);
        trail.addColorStop(0, `rgba(165,243,252,${p.life * .5})`); trail.addColorStop(1, 'rgba(124,92,255,0)');
        ctx.strokeStyle = trail; ctx.lineWidth = 1.2; ctx.beginPath(); ctx.moveTo(p.x, p.y); ctx.lineTo(p.x + 100, p.y - 48); ctx.stroke();
      }
      meteors = meteors.filter(p => p.life > 0);
      for (const p of sparks) {
        p.x += p.vx * dt; p.y += p.vy * dt; p.life -= .025 * dt;
        if (p.life <= 0) continue;
        ctx.fillStyle = `hsla(${p.hue},95%,75%,${p.life * .7})`; ctx.beginPath(); ctx.arc(p.x, p.y, p.life * 2, 0, Math.PI * 2); ctx.fill();
      }
      sparks = sparks.filter(p => p.life > 0);
      slowFrames = performance.now() - started > 8 ? slowFrames + 1 : Math.max(0, slowFrames - 1);
      if (slowFrames >= 6 && fps > 12) { fps = 12; canvas.dataset.fpsLimit = fps; }
      if (!once) schedule();
    }
    function scrollPriority() {
      if (!scrolling) { scrolling = true; sync(); }
      clearTimeout(scrollTimer); scrollTimer = setTimeout(() => { scrolling = false; sync(); }, 180);
    }
    addEventListener('resize', () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(resize, 160); }, {passive: true});
    document.addEventListener('scroll', scrollPriority, {capture: true, passive: true});
    addEventListener('wheel', scrollPriority, {passive: true});
    addEventListener('pointermove', e => { mouse.x = e.clientX; mouse.y = e.clientY; }, {passive: true});
    document.addEventListener('pointerleave', () => { mouse.x = mouse.y = -1e4; });
    addEventListener('pointerdown', e => {
      if (paused()) return;
      for (let i = 0; i < 12; i++) { const a = rand(0, Math.PI * 2), s = rand(.8, 3.4); sparks.push({x: e.clientX, y: e.clientY, vx: Math.cos(a) * s, vy: Math.sin(a) * s, life: 1, hue: hues[i % 4]}); }
      sparks = sparks.slice(-60);
    }, {passive: true});
    document.addEventListener('toggle', e => { if (e.target.tagName === 'DIALOG') { overlay = !!document.querySelector('dialog[open]'); sync(); } }, true);
    document.addEventListener('ps:overlay', e => { overlay = e.detail; sync(); });
    document.addEventListener('visibilitychange', sync);
    motion.addEventListener('change', () => { sparks = []; meteors = []; resize(); });
    addEventListener('pagehide', () => { cancel(); clearTimeout(resizeTimer); clearTimeout(scrollTimer); });
    addEventListener('pageshow', sync);
    resize();
  };
  if (document.body) start(); else document.addEventListener('DOMContentLoaded', start, {once: true});
})();
