// LiLi Roofing Shorts: one continuous 21-second clip per lead, built from its GAF facts and photo.

import { api, donut, esc, ico, openLead, parts, scrim, state } from './app.js';

const total = 21000;
// The name slides up to become the header at headAt; each later part starts at its mark.
const headAt = 1800;
const marks = [0, 2300, 6500, 10500, 14500];
const calm = window.matchMedia('(prefers-reduced-motion: reduce)');
const roomy = window.matchMedia('(min-width: 1280px)');
const shield = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M12 3l7 3v5c0 4.5-3 8.3-7 10-4-1.7-7-5.5-7-10V6z"/><path d="M8.5 12l2.5 2.5 4.5-5"/></svg>';
const details = new Map();
let leads = [];
let dock = null;
let pop = null;

// Fetch a lead's details once (the last part types out its first talking point).
function prefetch(id) {
  if (details.has(id)) return;
  details.set(id, null);
  api(`/v1/leads/${encodeURIComponent(id)}`).then(d => details.set(id, d)).catch(() => details.delete(id));
}

// A drawn roofline, tinted from the text so each lead looks different.
function roofArt(text) {
  let seed = 7;
  for (const ch of text) seed = (seed * 31 + ch.charCodeAt(0)) % 9973;
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

// The two rows of fact tiles that slide past the photo. Only this lead's own facts, never other companies.
function tiles(lead) {
  let top = '';
  let bottom = '';
  if (lead.rating) top += `<div class="tile"><b>${lead.rating.toFixed(1)}</b><span>★ rating</span></div>`;
  else top += '<div class="tile"><b>New</b><span>no reviews</span></div>';
  if (lead.certification) top += `<div class="tile wide badge">${shield}<span>${esc(lead.certification)}</span></div>`;
  if (lead.distance_miles != null) top += `<div class="tile"><b>${lead.distance_miles.toFixed(1)}</b><span>miles</span></div>`;
  top += `<div class="tile art">${roofArt(lead.name + 'a')}</div>`;
  if (lead.review_count) bottom += `<div class="tile"><b>${lead.review_count}</b><span>reviews</span></div>`;
  if (lead.president_club_stars) bottom += `<div class="tile wide badge"><i>★</i><span>President's Club</span></div>`;
  if (lead.commercial_certification) bottom += `<div class="tile wide badge">${shield}<span>${esc(lead.commercial_certification)}</span></div>`;
  for (const line of lead.services) bottom += `<div class="tile word"><span>${esc(line)}</span></div>`;
  bottom += `<div class="tile wide art">${roofArt(lead.name + 'b')}</div>`;
  // Each row holds its tiles twice, so sliding it by half its width loops without a jump.
  return `<div class="row"><div class="strip">${top}${top}</div></div><div class="row rev"><div class="strip">${bottom}${bottom}</div></div>`;
}

// The name as letters that rise in one after another; words stay whole when the line wraps.
function letters(name) {
  let html = '';
  let n = 0;
  for (const word of name.split(' ')) {
    let chars = '';
    for (const ch of word) {
      chars += `<i style="--d:${n * 22}ms">${esc(ch)}</i>`;
      n++;
    }
    html += `<span class="w">${chars}</span> `;
  }
  return html;
}

// One lead's clip: the photo wall, the name, then score, credentials, reviews and the first call tip.
function clipHtml(lead, i) {
  let pic = roofArt(lead.name);
  if (lead.logo_url) {
    pic = `<img src="${esc(lead.logo_url.replace('width=120', 'width=400'))}" alt="${esc(lead.name)}" loading="lazy" decoding="async">`;
  }
  let meta = lead.certification || 'GAF contractor';
  if (lead.distance_miles != null) meta += ` · ${lead.distance_miles.toFixed(1)} mi`;

  let legend = '';
  for (let p = 0; p < parts.length; p++) {
    const [key, label, color] = parts[p];
    legend += `<span style="--d:${p * 90}ms"><i style="background:${color}"></i>${label} <b>${(lead.score[key] || 0).toFixed(1)}</b></span>`;
  }

  const creds = [];
  if (lead.certification) creds.push(lead.certification);
  if (lead.president_club_stars) creds.push(`President's Club ${'★'.repeat(lead.president_club_stars)}`);
  if (lead.commercial_certification) creds.push(lead.commercial_certification);
  for (const line of lead.services) creds.push(line);
  if (!creds.length) creds.push('GAF listed');
  let chips = '';
  for (let c = 0; c < creds.length; c++) chips += `<span class="chip" style="--d:${c * 110}ms">${esc(creds[c])}</span>`;

  let rating = 'No reviews yet';
  let count = '';
  let pct = 0;
  if (lead.rating) {
    rating = `${lead.rating.toFixed(1)} out of 5`;
    count = `${lead.review_count} homeowner reviews`;
    pct = (lead.rating / 5) * 100;
  }

  return `
    <div class="clip" style="transform:translateY(${i * 100}%)">
      <div class="wall"><div class="pic">${pic}</div><div class="rows">${tiles(lead)}</div></div>
      <div class="stage">
        <div class="intro"><div class="kicker">${esc(meta)}</div><div class="name">${letters(lead.name)}</div></div>
        <div class="part p-score"><div class="kicker">Priority score</div>${donut(lead.score, 150)}<div class="legend">${legend}</div></div>
        <div class="part p-chips"><div class="kicker">Credentials</div><div class="chips">${chips}</div></div>
        <div class="part p-reviews"><div class="kicker">Homeowner reviews</div>
          <span class="big-stars" style="--pct:${pct}%">★★★★★<b>★★★★★</b></span>
          <div class="typed big" data-text="${esc(rating)}"></div><div class="typed" data-text="${esc(count)}"></div></div>
        <div class="part p-tip"><div class="kicker">First call tip</div><div class="typed tip"></div></div>
      </div>
      <button class="tap prev" type="button" aria-label="Back"></button>
      <button class="tap next" type="button" aria-label="Skip ahead"></button>
      <div class="clip-foot"><span class="clip-meta">${esc(meta)}</span>
        <button class="pill accent" type="button" data-id="${esc(lead.gaf_id)}">Contact</button></div>
    </div>`;
}

// How far through an effect we are, from 0 to 1.
function progress(t, start, length) {
  if (calm.matches) return 1;
  return Math.max(0, Math.min(1, (t - start) / length));
}

// Show part of a text, typed up to `share` (0 to 1); the caret shows while it is typing.
function type(el, text, share) {
  const shown = text.slice(0, Math.ceil(text.length * share));
  if (el.textContent !== shown) el.textContent = shown;
  el.classList.toggle('typing', share > 0 && share < 1);
}

class Player {
  // A phone-shaped player inside `host`; the window version (`big`) has a close button.
  constructor(host, big) {
    this.big = big;
    this.clip = 0;
    this.t = 0;
    this.last = 0;
    this.held = false;
    this.paused = false;
    this.downAt = 0;
    this.startY = null;
    this.dy = 0;
    this.dragged = false;
    this.wheelAt = 0;
    this.wrapping = false;
    this.opener = null;
    this.el = document.createElement('div');
    this.el.className = 'phone';
    this.el.innerHTML = `<div class="reel"></div><div class="progress"><i></i></div>
      <div class="rail">
        <button class="icon up" type="button" aria-label="Previous lead">${ico.up}</button>
        <button class="icon down" type="button" aria-label="Next lead">${ico.down}</button>
      </div>
      ${big ? `<button class="icon close-x" type="button" aria-label="Close">${ico.close}</button>` : ''}`;
    this.reel = this.el.querySelector('.reel');
    host.append(this.el);
    this.bind();
    this.fill();
    this.frame = requestAnimationFrame(now => this.tick(now));
  }

  // One clip per lead, stacked so the reel can slide up and down between them.
  fill() {
    let html = '';
    for (let i = 0; i < leads.length; i++) html += clipHtml(leads[i], i);
    if (!leads.length) html = '<div class="empty-note">No leads match these filters</div>';
    this.reel.innerHTML = html;
    for (const img of this.reel.querySelectorAll('.pic img')) {
      // The frame takes the photo's shape (within limits) and never stretches a small logo far past its real size.
      // A broken image falls back to the drawing.
      img.addEventListener('load', () => {
        const ratio = Math.max(0.75, Math.min(1.8, img.naturalWidth / img.naturalHeight));
        img.parentElement.style.aspectRatio = String(ratio);
        img.style.maxWidth = `${img.naturalWidth * 1.5}px`;
        img.style.maxHeight = `${img.naturalHeight * 1.5}px`;
      });
      img.addEventListener('error', () => { img.outerHTML = roofArt(img.alt); }, { once: true });
    }
    this.clip = 0;
    this.go(0, true);
  }

  // Slide to clip i (no wrapping past the ends) and play it from the start. At an end it does nothing,
  // unless `restart` is set (a new list of leads).
  go(i, restart) {
    if (!leads.length) return;
    i = Math.max(0, Math.min(leads.length - 1, i));
    if (i === this.clip && !restart) return;
    const old = this.reel.children[this.clip];
    this.clip = i;
    this.t = 0;
    this.reel.style.transform = `translateY(${-i * 100}%)`;
    // Reset the old clip only after it has slid out of view.
    if (old && old !== this.reel.children[i]) {
      setTimeout(() => { if (this.reel.children[this.clip] !== old) this.reset(old); }, 550);
    }
    const el = this.reel.children[i];
    // Only the playing clip can be reached with Tab or a screen reader.
    for (const clip of this.reel.children) clip.inert = clip !== el;
    this.reset(el);
    void el.offsetWidth; // forces a reflow so the clip's animations start again
    el.classList.add('play');
    this.el.querySelector('.up').disabled = i === 0;
    this.el.querySelector('.down').disabled = i === leads.length - 1;
    prefetch(leads[i].gaf_id);
    if (i + 1 < leads.length) prefetch(leads[i + 1].gaf_id);
  }

  // Put a clip back to its first frame.
  reset(el) {
    el.classList.remove('play', 'headed');
    for (const part of el.querySelectorAll('.part')) part.classList.remove('on', 'past');
    for (const typed of el.querySelectorAll('.typed')) type(typed, '', 0);
  }

  // After the last clip, fade back to the first instead of scrolling through them all.
  next() {
    if (this.clip < leads.length - 1) {
      this.go(this.clip + 1);
      return;
    }
    if (this.wrapping) return;
    this.wrapping = true;
    this.reel.classList.add('fade');
    setTimeout(() => {
      this.reel.classList.add('drag');
      this.go(0, true);
      void this.reel.offsetWidth; // apply the jump before the fade back in
      this.reel.classList.remove('drag');
      this.reel.classList.remove('fade');
      this.wrapping = false;
    }, 260);
  }

  // Jump within the clip: forward to the next part, or back to the start of this part (or the one before).
  seek(dir) {
    let at = 0;
    for (let m = 0; m < marks.length; m++) if (this.t >= marks[m]) at = m;
    if (dir > 0) {
      if (at + 1 < marks.length) this.t = marks[at + 1];
      else this.next();
    } else if (this.t - marks[at] > 1200 || at === 0) {
      this.t = marks[at];
    } else {
      this.t = marks[at - 1];
    }
  }

  // Every frame: move time forward (unless paused, hidden or behind another window), then draw.
  tick(now) {
    // Capped, so coming back to a hidden tab does not jump ahead.
    const dt = this.last ? Math.min(100, now - this.last) : 0;
    this.last = now;
    const hidden = !this.el.getClientRects().length || document.hidden;
    const covered = !this.big && document.body.classList.contains('lock');
    if (leads.length && !this.held && !this.paused && !hidden && !covered && this.startY === null) {
      this.t += dt;
      if (this.t >= total) this.next();
    }
    if (leads.length) this.paint();
    this.frame = requestAnimationFrame(t => this.tick(t));
  }

  // Draw the current moment: the progress bar, which parts show, the count-up and the typing.
  paint() {
    const t = this.t;
    const el = this.reel.children[this.clip];
    this.el.querySelector('.progress i').style.transform = `scaleX(${Math.min(1, t / total)})`;
    el.classList.toggle('headed', t >= headAt);
    let at = 0;
    for (let m = 0; m < marks.length; m++) if (t >= marks[m]) at = m;
    const list = el.querySelectorAll('.part');
    for (let p = 0; p < list.length; p++) {
      list[p].classList.toggle('on', at === p + 1);
      list[p].classList.toggle('past', at > p + 1);
    }

    const score = leads[this.clip].score.total;
    const shown = Math.round(score * (1 - Math.pow(1 - progress(t, marks[1] + 200, 1200), 3)));
    const number = el.querySelector('.p-score text');
    if (number.textContent !== String(shown)) number.textContent = shown;

    const [rating, count] = el.querySelectorAll('.p-reviews .typed');
    const ratingTime = rating.dataset.text.length * 45;
    type(rating, rating.dataset.text, progress(t, marks[3] + 500, ratingTime));
    type(count, count.dataset.text, progress(t, marks[3] + 700 + ratingTime, count.dataset.text.length * 35));

    // The last part types out the first talking point, or the summary until the details load.
    const lead = leads[this.clip];
    const d = details.get(lead.gaf_id);
    let text = lead.summary || 'Analysis on its way.';
    if (d && d.analysis) text = d.analysis.talking_points[0];
    type(el.querySelector('.p-tip .typed'), text, progress(t, marks[4] + 400, Math.min(5200, text.length * 30)));
  }

  // Drag or scroll to change lead, tap the sides to skip within a clip, press and hold to pause.
  bind() {
    const el = this.el;
    el.addEventListener('pointerdown', e => {
      this.dragged = false;
      this.downAt = performance.now();
      if (e.target.closest('.rail, .clip-foot, .close-x')) return;
      this.held = true;
      this.startY = e.clientY;
      this.dy = 0;
    });
    el.addEventListener('pointermove', e => {
      if (this.startY === null) return;
      this.dy = e.clientY - this.startY;
      if (!this.dragged && Math.abs(this.dy) > 8) {
        this.dragged = true;
        // Keep getting moves even if the pointer leaves the phone; capture can fail for an ended pointer.
        try { el.setPointerCapture(e.pointerId); } catch (err) { /* the drag still works without it */ }
        this.reel.classList.add('drag');
      }
      if (!this.dragged) return;
      // Past the first or last clip the reel only gives a little, like a rubber band.
      let dy = this.dy;
      if ((dy > 0 && this.clip === 0) || (dy < 0 && this.clip === leads.length - 1)) dy *= 0.3;
      this.reel.style.transform = `translateY(calc(${-this.clip * 100}% + ${dy}px))`;
    });
    const release = () => {
      this.held = false;
      if (this.startY === null) return;
      this.startY = null;
      if (!this.dragged) return;
      this.reel.classList.remove('drag');
      const fast = Math.abs(this.dy) / (performance.now() - this.downAt) > 0.5;
      const far = Math.abs(this.dy) > el.clientHeight * 0.2;
      let target = this.clip;
      if (far || fast) target = this.clip + (this.dy < 0 ? 1 : -1);
      if (target === this.clip || target < 0 || target >= leads.length) {
        this.reel.style.transform = `translateY(${-this.clip * 100}%)`;
      } else {
        this.go(target);
      }
    };
    el.addEventListener('pointerup', release);
    el.addEventListener('pointercancel', release);
    el.addEventListener('pointerleave', release);

    el.addEventListener('click', e => {
      const btn = e.target.closest('button');
      const long = this.downAt && performance.now() - this.downAt > 300;
      this.downAt = 0;
      if (this.dragged) {
        this.dragged = false;
        return;
      }
      if (!btn) return;
      if (btn.dataset.id) {
        // Contact: close the window (if open) and open the lead with its email draft.
        closeWin();
        openLead(btn.dataset.id, null, { contact: true });
      } else if (btn.classList.contains('close-x')) closeWin();
      else if (btn.classList.contains('up')) this.go(this.clip - 1);
      else if (btn.classList.contains('down')) this.go(this.clip + 1);
      else if (long) return;
      else if (btn.classList.contains('prev')) this.seek(-1);
      else if (btn.classList.contains('next')) this.seek(1);
    });

    el.addEventListener('wheel', e => {
      e.preventDefault();
      const now = performance.now();
      if (Math.abs(e.deltaY) < 20 || now - this.wheelAt < 700) return;
      this.wheelAt = now;
      this.go(this.clip + (e.deltaY > 0 ? 1 : -1));
    }, { passive: false });
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
  const opener = document.activeElement;
  pop = new Player(win, true);
  pop.opener = opener;
  if (dock) pop.go(dock.clip);
  pop.el.querySelector('.close-x').focus({ preventScroll: true });
}

// Close the Shorts window.
function closeWin() {
  if (!pop) return;
  const win = pop.el.parentElement;
  const opener = pop.opener;
  pop.destroy();
  pop = null;
  win.remove();
  scrim(false);
  if (opener && document.body.contains(opener)) opener.focus({ preventScroll: true });
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
  else if (e.key === 'ArrowDown') pop.go(pop.clip + 1);
  else if (e.key === 'ArrowUp') pop.go(pop.clip - 1);
  else if (e.key === 'ArrowRight') pop.seek(1);
  else if (e.key === 'ArrowLeft') pop.seek(-1);
  else if (e.key === ' ') {
    e.preventDefault();
    pop.paused = !pop.paused;
  }
});
roomy.addEventListener('change', fitDock);
if (state.leads.size) load(Array.from(state.leads.values()).slice(0, 12));
fitDock();
