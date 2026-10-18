// LiLi Roofing Shorts: auto-playing clips (23 seconds each) built from each lead's GAF facts.

import { api, donut, esc, ico, openLead, parts, scrim, stars, state } from './app.js';

const durations = [4000, 4000, 4000, 4000, 7000];
const calm = window.matchMedia('(prefers-reduced-motion: reduce)');
const roomy = window.matchMedia('(min-width: 1280px)');
const details = new Map();
let leads = [];
let dock = null;
let pop = null;

// Fetch a lead's details once (the last scene shows its first talking point).
function prefetch(id) {
  if (details.has(id)) return;
  details.set(id, null);
  api(`/v1/leads/${encodeURIComponent(id)}`).then(d => details.set(id, d)).catch(() => details.delete(id));
}

// A drawn roofline for leads without a GAF photo, tinted from the name so each lead looks different.
function roofArt(name) {
  let seed = 7;
  for (const ch of name) seed = (seed * 31 + ch.charCodeAt(0)) % 9973;
  const hue = 95 + (seed % 60);
  let roofs = '';
  for (let row = 0; row < 3; row++) {
    const base = 430 + row * 70;
    for (let i = -1; i < 4; i++) {
      const w = 130 + ((seed >> (i + 2 + row)) % 50);
      const h = 55 + ((seed >> (row + 1)) % 40) + row * 8;
      const x = i * 115 + ((seed + row * 37) % 60) - 30;
      const tone = 9 + row * 5;
      roofs += `<polygon points="${x},${base} ${x + w / 2},${base - h} ${x + w},${base}" fill="hsl(${hue} 20% ${tone + 4}%)" stroke="hsl(${hue} 35% 60% / 0.45)" stroke-width="1"/>`;
      roofs += `<rect x="${x + 14}" y="${base}" width="${w - 28}" height="${720 - base}" fill="hsl(${hue} 12% ${tone}%)"/>`;
    }
  }
  return `<svg class="roof" viewBox="0 0 360 640" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
    <defs>
      <linearGradient id="sky${seed}" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stop-color="hsl(${hue} 25% 22%)"/><stop offset="1" stop-color="hsl(${hue} 15% 6%)"/>
      </linearGradient>
      <pattern id="grid${seed}" width="24" height="24" patternUnits="userSpaceOnUse">
        <path d="M24 0H0V24" fill="none" stroke="hsl(${hue} 30% 70% / 0.08)"/>
      </pattern>
    </defs>
    <rect width="360" height="640" fill="url(#sky${seed})"/>
    <rect width="360" height="640" fill="url(#grid${seed})"/>
    <circle cx="${70 + (seed % 220)}" cy="170" r="44" fill="hsl(${hue} 30% 70% / 0.18)"/>
    ${roofs}
  </svg>`;
}

// The five scenes of one lead's clip: intro, score, credentials, reviews, first call tip.
function scenesHtml(lead) {
  let pic = roofArt(lead.name);
  if (lead.logo_url) pic = `<img class="photo" src="${esc(lead.logo_url.replace('width=120', 'width=600'))}" alt="" loading="lazy">`;
  const where = lead.distance_miles == null ? '' : `${lead.distance_miles.toFixed(1)} mi from centre`;

  let legend = '';
  for (const [key, label, color] of parts) {
    legend += `<span><i style="background:${color}"></i>${label} ${(lead.score[key] || 0).toFixed(1)}</span>`;
  }

  const creds = [];
  if (lead.certification) creds.push(lead.certification);
  if (lead.president_club_stars) creds.push(`President's Club ${'★'.repeat(lead.president_club_stars)}`);
  if (lead.commercial_certification) creds.push(lead.commercial_certification);
  for (const line of lead.services) creds.push(line);
  if (!creds.length) creds.push('GAF listed');
  let chips = '';
  for (let i = 0; i < creds.length; i++) {
    chips += `<span class="chip" style="animation-delay:${0.15 + i * 0.12}s">${esc(creds[i])}</span>`;
  }

  let reviews = '<div class="huge">New</div><div class="small">No reviews yet</div>';
  if (lead.rating) reviews = `<div class="huge">${lead.rating.toFixed(1)}</div>${stars(lead.rating)}<div class="small">${lead.review_count} reviews</div>`;

  return `
    <div class="scene">${pic}<div class="shade-b"></div>
      <div class="front-text"><div class="small">${esc(lead.certification || 'GAF contractor')}</div>
      <div class="big">${esc(lead.name)}</div><div class="small">${where}</div></div></div>
    <div class="scene"><div class="small">Priority score</div>${donut(lead.score, 170)}<div class="legend">${legend}</div></div>
    <div class="scene"><div class="small">Credentials</div><div class="chips">${chips}</div></div>
    <div class="scene"><div class="small">Homeowner reviews</div>${reviews}</div>
    <div class="scene"><div class="small">First call tip</div><div class="type"></div></div>`;
}

// The text typed out in the last scene: the first talking point, or the summary until it loads.
function tip(lead) {
  const d = details.get(lead.gaf_id);
  if (d && d.analysis) return d.analysis.talking_points[0];
  return lead.summary || 'Analysis on its way.';
}

// Close the window (if open) and open the lead with its email draft.
function contact(id) {
  closeWin();
  openLead(id, null, { contact: true });
}

class Player {
  // A phone-shaped player inside `host`; the window version (`big`) has a close button.
  constructor(host, big) {
    this.big = big;
    this.clip = 0;
    this.scene = 0;
    this.t = 0;
    this.last = 0;
    this.held = false;
    this.downAt = 0;
    this.wheelAt = 0;
    this.touchY = null;
    this.el = document.createElement('div');
    this.el.className = 'phone';
    this.el.innerHTML = `<div class="reel"></div>${big ? `<button class="icon close-x" type="button" aria-label="Close">${ico.close}</button>` : ''}`;
    this.reel = this.el.querySelector('.reel');
    host.append(this.el);
    this.bind();
    this.fill();
    this.frame = requestAnimationFrame(now => this.tick(now));
  }

  // One clip per lead, stacked so the reel can slide up and down between them.
  fill() {
    let html = '';
    for (let i = 0; i < leads.length; i++) {
      const lead = leads[i];
      let bars = '';
      for (let s = 0; s < durations.length; s++) bars += '<i><b></b></i>';
      let meta = lead.certification || 'GAF contractor';
      if (lead.distance_miles != null) meta += ` · ${lead.distance_miles.toFixed(1)} mi`;
      html += `
        <div class="clip" style="transform:translateY(${i * 100}%)" aria-label="${esc(lead.name)}">
          <div class="bars-top">${bars}</div>
          ${scenesHtml(lead)}
          <button class="tap prev" type="button" aria-label="Back"></button>
          <button class="tap next" type="button" aria-label="Next"></button>
          <div class="clip-foot">
            <div><div class="clip-name">${esc(lead.name)}</div><div class="clip-meta">${esc(meta)}</div></div>
            <button class="pill accent" type="button" data-id="${esc(lead.gaf_id)}">Contact</button>
          </div>
        </div>`;
    }
    if (!leads.length) html = '<div class="scene on"><div class="small">No leads match these filters</div></div>';
    this.reel.innerHTML = html;
    for (const img of this.reel.querySelectorAll('img.photo')) {
      const name = img.closest('.clip').getAttribute('aria-label');
      img.addEventListener('error', () => { img.outerHTML = roofArt(name); }, { once: true });
    }
    this.go(0, 0);
  }

  // Show one scene of one clip and restart its animations.
  go(clip, scene) {
    if (!leads.length) return;
    this.clip = (clip + leads.length) % leads.length;
    this.scene = scene;
    this.t = 0;
    this.reel.style.transform = `translateY(${-this.clip * 100}%)`;
    for (const el of this.reel.querySelectorAll('.scene.on')) el.classList.remove('on');
    for (const b of this.reel.querySelectorAll('.bars-top b')) b.style.width = '0';
    const clipEl = this.reel.children[this.clip];
    const sceneEl = clipEl.querySelectorAll('.scene')[scene];
    void sceneEl.offsetWidth; // forces a reflow so the scene's animations start again
    sceneEl.classList.add('on');
    prefetch(leads[this.clip].gaf_id);
    prefetch(leads[(this.clip + 1) % leads.length].gaf_id);
  }

  // Next or previous scene; past the ends it moves to the next or previous lead.
  step(dir) {
    const next = this.scene + dir;
    if (next >= durations.length) this.go(this.clip + 1, 0);
    else if (next < 0) this.go(this.clip - 1, 0);
    else this.go(this.clip, next);
  }

  // Every frame: move time forward (unless paused or hidden), then draw the progress bars and typing.
  tick(now) {
    const dt = this.last ? now - this.last : 0;
    this.last = now;
    const hidden = !this.el.getClientRects().length || document.hidden;
    const covered = !this.big && document.body.classList.contains('lock');
    if (leads.length && !this.held && !hidden && !covered) {
      this.t += dt;
      if (this.t >= durations[this.scene]) this.step(1);
    }
    if (leads.length) this.paint();
    this.frame = requestAnimationFrame(t => this.tick(t));
  }

  // Fill the progress bars and type out the tip.
  paint() {
    const clipEl = this.reel.children[this.clip];
    const bars = clipEl.querySelectorAll('.bars-top b');
    for (let i = 0; i < bars.length; i++) {
      let pct = 0;
      if (i < this.scene) pct = 100;
      if (i === this.scene) pct = Math.min(100, (this.t / durations[i]) * 100);
      bars[i].style.width = `${pct}%`;
    }
    if (this.scene === durations.length - 1) {
      const text = tip(leads[this.clip]);
      let shown = text.length;
      if (!calm.matches) shown = Math.ceil(text.length * Math.min(1, this.t / (durations[this.scene] * 0.7)));
      const typeEl = clipEl.querySelector('.type');
      if (typeEl.textContent.length !== shown) typeEl.textContent = text.slice(0, shown);
    }
  }

  // Taps step through scenes, press and hold pauses, swipe or scroll changes lead.
  bind() {
    const el = this.el;
    el.addEventListener('pointerdown', () => { this.held = true; this.downAt = performance.now(); });
    for (const type of ['pointerup', 'pointercancel', 'pointerleave']) el.addEventListener(type, () => { this.held = false; });
    el.addEventListener('click', e => {
      const btn = e.target.closest('button');
      const long = this.downAt && performance.now() - this.downAt > 300;
      this.downAt = 0;
      if (!btn) return;
      if (btn.dataset.id) contact(btn.dataset.id);
      else if (btn.classList.contains('close-x')) closeWin();
      else if (long) return;
      else if (btn.classList.contains('prev')) this.step(-1);
      else if (btn.classList.contains('next')) this.step(1);
    });
    el.addEventListener('wheel', e => {
      e.preventDefault();
      const now = performance.now();
      if (Math.abs(e.deltaY) < 20 || now - this.wheelAt < 700) return;
      this.wheelAt = now;
      this.go(this.clip + (e.deltaY > 0 ? 1 : -1), 0);
    }, { passive: false });
    el.addEventListener('touchstart', e => { this.touchY = e.touches[0].clientY; }, { passive: true });
    el.addEventListener('touchend', e => {
      if (this.touchY === null) return;
      const dy = e.changedTouches[0].clientY - this.touchY;
      this.touchY = null;
      if (Math.abs(dy) > 60) this.go(this.clip + (dy < 0 ? 1 : -1), 0);
    });
  }

  // Stop the clock and remove the player.
  destroy() {
    cancelAnimationFrame(this.frame);
    this.el.remove();
  }
}

// Open Shorts full size: a window on big screens, the whole screen on phones.
function openWin() {
  if (pop || !leads.length) return;
  const win = document.createElement('div');
  win.className = 'shorts-win';
  win.setAttribute('role', 'dialog');
  win.setAttribute('aria-modal', 'true');
  win.setAttribute('aria-label', 'Roofing shorts');
  document.body.append(win);
  scrim(true);
  pop = new Player(win, true);
  if (dock) pop.go(dock.clip, 0);
  pop.el.querySelector('.close-x').focus({ preventScroll: true });
}

// Close the Shorts window.
function closeWin() {
  if (!pop) return;
  const win = pop.el.parentElement;
  pop.destroy();
  pop = null;
  win.remove();
  scrim(false);
}

// Show the docked player only on screens wide enough for the third column.
function fitDock() {
  if (roomy.matches && !dock) dock = new Player(document.getElementById('shortsDock'), false);
  if (!roomy.matches && dock) {
    dock.destroy();
    dock = null;
  }
}

// New filters: the clips follow the top leads of the new list.
function load(list) {
  leads = list;
  if (dock) dock.fill();
  if (pop) pop.fill();
}

document.addEventListener('lili:leads', e => load(e.detail));
document.addEventListener('click', e => { if (e.target.closest('[data-open="shorts"]')) openWin(); });
document.getElementById('scrim').addEventListener('click', closeWin);
document.addEventListener('keydown', e => {
  if (!pop) return;
  if (e.key === 'Escape') closeWin();
  else if (e.key === 'ArrowDown') pop.go(pop.clip + 1, 0);
  else if (e.key === 'ArrowUp') pop.go(pop.clip - 1, 0);
  else if (e.key === 'ArrowRight') pop.step(1);
  else if (e.key === 'ArrowLeft') pop.step(-1);
});
roomy.addEventListener('change', fitDock);
if (state.leads.size) load(Array.from(state.leads.values()).slice(0, 12));
fitDock();
