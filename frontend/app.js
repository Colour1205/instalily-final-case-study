// LiLi: lead cards, filters, search, the flip-open detail window and the contact panel.

import { API_BASE } from './config.js';

const $ = sel => document.querySelector(sel);

const svg = paths => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths}</svg>`;
export const ico = {
  menu: svg('<path d="M4 7h16M4 12h16M4 17h16"/>'),
  search: svg('<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/>'),
  close: svg('<path d="M6 6l12 12M18 6L6 18"/>'),
  arrow: svg('<path d="M5 12h14M13 6l6 6-6 6"/>'),
  back: svg('<path d="M19 12H5M11 6l-6 6 6 6"/>'),
  copy: svg('<rect x="8" y="8" width="12" height="12"/><path d="M16 8V4H4v12h4"/>'),
  phone: svg('<path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2"/>'),
  mail: svg('<rect x="3" y="5" width="18" height="14"/><path d="M3 7l9 6 9-6"/>'),
  plus: svg('<path d="M12 5v14M5 12h14"/>'),
  minus: svg('<path d="M5 12h14"/>'),
  target: svg('<circle cx="12" cy="12" r="3"/><path d="M12 2v4M12 18v4M2 12h4M18 12h4"/>'),
  filter: svg('<path d="M4 6h16M7 12h10M10 18h4"/>'),
  expand: svg('<path d="M4 9V4h5M20 15v5h-5M15 4h5v5M9 20H4v-5"/>'),
  up: svg('<path d="M6 15l6-6 6 6"/>'),
  down: svg('<path d="M6 9l6 6 6-6"/>'),
  spin: svg('<path d="M12 3a9 9 0 1 0 9 9"/>'),
};

export const parts = [
  ['review_count_adjust_rating', 'Rating', 'var(--p1)'],
  ['gaf_rank', 'GAF rank', 'var(--p2)'],
  ['specialty', 'Specialty', 'var(--p3)'],
  ['distance', 'Distance', 'var(--p4)'],
];

export const state = { run: 0, page: 0, total: 0, loaded: 0, busy: false, done: false, leads: new Map() };
const open = { flip: null, engage: null, card: null, lead: null, rect: null };
const calm = window.matchMedia('(prefers-reduced-motion: reduce)');
let filterTimer = null;
let scrimTimer = null;

// Fetch JSON from the LiLi API; throws on HTTP errors.
export async function api(path) {
  const res = await fetch(API_BASE + path);
  if (!res.ok) throw new Error(res.status);
  return res.json();
}

// Escape text before putting it into HTML.
export function esc(text) {
  if (text == null) return '';
  const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
  return String(text).replace(/[&<>"']/g, ch => map[ch]);
}

// Star rating that fills to the given rating out of 5.
export function stars(rating) {
  const pct = Math.max(0, Math.min(100, (rating / 5) * 100));
  return `<span class="stars" aria-label="${rating} out of 5">★★★★★<b style="width:${pct}%">★★★★★</b></span>`;
}

// Donut chart of the four score parts, with the total in the middle.
export function donut(score, size) {
  let start = 25;
  let segs = '';
  for (const [key, , color] of parts) {
    const len = Math.max(0, score[key] || 0);
    segs += `<circle class="seg" cx="21" cy="21" r="15.915" fill="none" stroke="${color}" stroke-width="5" stroke-dasharray="${len} ${100 - len}" stroke-dashoffset="${start}"/>`;
    start -= len;
  }
  return `<svg class="donut" width="${size}" height="${size}" viewBox="0 0 42 42" role="img" aria-label="Score ${Math.round(score.total)}">
    <circle cx="21" cy="21" r="15.915" fill="none" stroke="var(--soft)" stroke-width="5"/>${segs}
    <text x="21" y="21" text-anchor="middle" dominant-baseline="central">${Math.round(score.total)}</text></svg>`;
}

// Colour key for the donut.
function legend() {
  let rows = '';
  for (const [, label, color] of parts) rows += `<span><i style="background:${color}"></i>${label}</span>`;
  return `<div class="legend">${rows}</div>`;
}

// Score part bars for the detail window.
function bars(score) {
  let rows = '';
  for (const [key, label, color] of parts) {
    const val = score[key] || 0;
    rows += `<div class="bar"><span>${label}</span><span class="track"><i style="width:${(val / 25) * 100}%;background:${color}"></i></span><span>${val.toFixed(1)}</span></div>`;
  }
  return rows;
}

// Small badges: certification, awards, commercial work and product lines.
function tags(lead, all) {
  let out = '';
  if (lead.certification) out += `<span class="tag ${lead.certification === 'Master Elite' ? 'on' : ''}">${esc(lead.certification)}</span>`;
  if (lead.president_club_stars) out += `<span class="tag on">President's Club ${'★'.repeat(lead.president_club_stars)}</span>`;
  if (lead.commercial_certification) out += `<span class="tag">${esc(lead.commercial_certification)}</span>`;
  const lines = all ? lead.services : lead.services.slice(0, 2);
  for (const line of lines) out += `<span class="tag">${esc(line)}</span>`;
  if (!all && lead.services.length > 2) out += `<span class="tag">+${lead.services.length - 2}</span>`;
  return out;
}

// "4.9 (378) · 12.3 mi" line.
function meta(lead) {
  const rate = lead.rating ? `${stars(lead.rating)} ${lead.rating.toFixed(1)} (${lead.review_count})` : 'No reviews';
  const dist = lead.distance_miles == null ? '' : ` · ${lead.distance_miles.toFixed(1)} mi`;
  return `<span class="rate">${rate}${dist}</span>`;
}

// Short message at the bottom of the screen.
export function toast(text) {
  const el = document.createElement('div');
  el.className = 'toast';
  el.textContent = text;
  document.body.append(el);
  setTimeout(() => el.remove(), 1800);
}

// Search-bar words that rank the list by a score part instead of searching names.
const rankWords = {
  rating: 'rating', reviews: 'rating', gaf: 'rank', rank: 'rank',
  specialty: 'specialty', specialties: 'specialty', distance: 'distance', closest: 'distance', nearest: 'distance',
};
const rankNames = { rating: 'Rating', rank: 'GAF rank', specialty: 'Specialty', distance: 'Distance' };

// Split the search text into ranking words and the words to look for in names and addresses.
function readSearch() {
  const sort = [];
  const words = [];
  for (const word of $('#q').value.trim().split(/\s+/)) {
    const part = rankWords[word.toLowerCase()];
    if (part) {
      if (!sort.includes(part)) sort.push(part);
    } else if (word) {
      words.push(word);
    }
  }
  return { sort, q: words.join(' ') };
}

// The current filters, search and ranking as a query string for the API.
export function query() {
  const form = new FormData($('#filters'));
  const params = new URLSearchParams();
  for (const [key, val] of form) if (val) params.append(key, val);
  const search = readSearch();
  if (search.q) params.set('q', search.q);
  for (const part of search.sort) params.append('sort', part);
  return params.toString();
}

// One lead card for the list.
function card(lead) {
  const el = document.createElement('article');
  el.className = 'card';
  el.dataset.id = lead.gaf_id;
  el.innerHTML = `
    <div class="card-top"><h3>${esc(lead.name)}</h3></div>
    ${meta(lead)}
    <div class="tags">${tags(lead, false)}</div>
    <p>${esc(lead.summary || 'Analysis on its way.')}</p>
    <div class="card-foot">${donut(lead.score, 66)}${legend()}
      <button class="icon open-btn" type="button" aria-label="Open ${esc(lead.name)}">${ico.arrow}</button></div>`;
  el.querySelector('.open-btn').addEventListener('click', () => openLead(lead.gaf_id, el));
  return el;
}

// Load the next page of leads (infinite scroll). Answers from before a filter change are dropped.
async function loadMore() {
  if (state.busy || state.done) return;
  state.busy = true;
  const run = state.run;
  const list = $('#cards');
  const ghosts = [];
  for (let i = 0; i < 3; i++) {
    const g = document.createElement('div');
    g.className = 'ghost';
    list.append(g);
    ghosts.push(g);
  }
  try {
    const qs = query();
    const data = await api(`/v1/leads?${qs}${qs ? '&' : ''}page=${state.page + 1}&limit=24`);
    if (run !== state.run) return;
    for (const g of ghosts) g.remove();
    state.page = data.page;
    state.total = data.total;
    for (const lead of data.leads) {
      state.leads.set(lead.gaf_id, lead);
      list.append(card(lead));
    }
    state.loaded += data.leads.length;
    state.done = state.loaded >= data.total;
    const sort = readSearch().sort;
    let count = `${data.total} leads`;
    if (sort.length) count += ` · ranked by ${sort.map(part => rankNames[part]).join(' + ')}`;
    $('#count').textContent = count;
    if (data.total === 0) list.innerHTML = '<div class="empty">No leads match these filters.</div>';
    if (data.page === 1) document.dispatchEvent(new CustomEvent('lili:leads', { detail: data.leads.slice(0, 12) }));
  } catch (err) {
    if (run === state.run) toast('Could not load leads');
  } finally {
    for (const g of ghosts) g.remove();
    if (run === state.run) {
      state.busy = false;
      requestAnimationFrame(nearEnd);
    }
  }
}

// Keep loading while the end of the list is still on screen (tall screens).
function nearEnd() {
  if (!state.done && $('#sentinel').getBoundingClientRect().top < window.innerHeight + 800) loadMore();
}

// Start the list again after a filter or search change, and refresh the map.
function reload() {
  state.run += 1;
  state.busy = false;
  state.page = 0;
  state.loaded = 0;
  state.done = false;
  state.leads.clear();
  $('#cards').innerHTML = '';
  loadMore();
  document.dispatchEvent(new CustomEvent('lili:filters'));
}

// Wait a moment so quick clicks or typing only reload once.
function reloadSoon(ms) {
  clearTimeout(filterTimer);
  filterTimer = setTimeout(reload, ms);
}

// Where the detail window ends up: centred, or full screen on phones.
function targetRect() {
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  if (vw < 600) return { left: 0, top: 0, width: vw, height: vh };
  const width = Math.min(760, vw - 32);
  const height = Math.min(vh * 0.86, 820);
  return { left: (vw - width) / 2, top: (vh - height) / 2, width, height };
}

// Place an element at a rectangle on screen.
function place(el, rect) {
  el.style.left = `${rect.left}px`;
  el.style.top = `${rect.top}px`;
  el.style.width = `${rect.width}px`;
  el.style.height = `${rect.height}px`;
}

// Darken or undarken the page behind a window.
export function scrim(show) {
  const el = $('#scrim');
  clearTimeout(scrimTimer);
  if (show) {
    el.hidden = false;
    requestAnimationFrame(() => el.classList.add('show'));
    document.body.classList.add('lock');
  } else {
    el.classList.remove('show');
    scrimTimer = setTimeout(() => { el.hidden = true; }, 350);
    document.body.classList.remove('lock');
  }
}

// Open a lead: its card flips over and grows into the detail window.
export async function openLead(id, cardEl, opts) {
  if (open.flip) return;
  const lead = state.leads.get(id);
  const end = targetRect();
  const start = cardEl ? cardEl.getBoundingClientRect() : {
    left: end.left + end.width / 2 - 140, top: end.top + end.height / 2 - 125, width: 280, height: 250,
  };
  const flip = document.createElement('div');
  flip.className = 'flip';
  flip.setAttribute('role', 'dialog');
  flip.setAttribute('aria-modal', 'true');
  flip.innerHTML = '<div class="flip-inner"><div class="face front"></div><div class="face back"><div class="detail"><span class="label">Loading…</span></div></div></div>';
  if (cardEl) flip.querySelector('.front').append(cardEl.cloneNode(true));
  else if (lead) flip.querySelector('.front').append(card(lead));
  place(flip, start);
  document.body.append(flip);
  if (cardEl) cardEl.classList.add('gone');
  open.flip = flip;
  open.card = cardEl;
  open.rect = end;
  scrim(true);
  requestAnimationFrame(() => requestAnimationFrame(() => {
    place(flip, end);
    flip.classList.add('open');
  }));

  try {
    const detail = await api(`/v1/leads/${encodeURIComponent(id)}`);
    if (open.flip !== flip) return;
    open.lead = detail;
    const back = flip.querySelector('.back');
    back.innerHTML = detailHtml(detail);
    back.querySelector('.x').addEventListener('click', closeLead);
    back.querySelector('.contact-btn').addEventListener('click', openEngage);
    back.querySelector('.x').focus({ preventScroll: true });
    if (opts && opts.contact) setTimeout(openEngage, 600);
  } catch (err) {
    toast('Could not load this lead');
    closeLead();
  }
}

// The back of the card: everything a rep needs about one lead.
function detailHtml(d) {
  const a = d.analysis;
  const c = d.contact;
  let analysis = '<p class="note">Analysis on its way.</p>';
  if (a) {
    let points = '';
    for (const p of a.talking_points) points += `<li>${esc(p)}</li>`;
    analysis = `
      ${a.is_current ? '' : '<span class="tag warn">Updating</span>'}
      <div class="sec"><h4 class="label">Summary</h4><p>${esc(a.summary)}</p></div>
      <div class="sec"><h4 class="label">Why call</h4><p>${esc(a.why_good_lead)}</p></div>
      <div class="sec"><h4 class="label">Pitch</h4><p>${esc(a.pitch)}</p></div>
      <div class="sec"><h4 class="label">Talking points</h4><ol>${points}</ol></div>`;
  }
  let contact = '';
  if (c.phone) contact += `<a href="tel:${esc(c.phone.replace(/[^\d+]/g, ''))}">${esc(c.phone)}</a>`;
  if (c.address) contact += `<span>${esc(c.address)}${c.maps_url ? ` · <a href="${esc(c.maps_url)}" target="_blank" rel="noopener">Map</a>` : ''}</span>`;
  if (c.profile_url) contact += `<a href="${esc(c.profile_url)}" target="_blank" rel="noopener">GAF profile</a>`;
  return `
    <button class="icon x" type="button" aria-label="Close">${ico.close}</button>
    <div class="detail">
      <div class="detail-head"><h2>${esc(d.name)}</h2>${meta(d)}</div>
      <div class="tags">${tags(d, true)}</div>
      <div class="score-row">${donut(d.score, 104)}<div class="bars">${bars(d.score)}</div></div>
      ${analysis}
      <div class="sec"><h4 class="label">Contact</h4><div class="contact">${contact}</div></div>
    </div>
    <div class="detail-foot"><button class="pill accent contact-btn" type="button">${ico.mail} Contact</button></div>`;
}

// Close the detail window: it shrinks and flips back into its card.
function closeLead() {
  const flip = open.flip;
  if (!flip) return;
  closeEngage(true);
  const cardEl = open.card;
  const inList = cardEl && document.body.contains(cardEl);
  flip.classList.remove('open');
  if (inList) place(flip, cardEl.getBoundingClientRect());
  else flip.style.opacity = '0';
  scrim(false);
  setTimeout(() => {
    flip.remove();
    if (cardEl) cardEl.classList.remove('gone');
  }, 560);
  open.flip = null;
  open.card = null;
  open.lead = null;
}

// The rep's own name and email, remembered in this browser.
function me() {
  try { return JSON.parse(localStorage.getItem('lili.me')) || {}; } catch (err) { return {}; }
}

// Save the rep's name and email in this browser.
function saveMe(data) {
  try { localStorage.setItem('lili.me', JSON.stringify(data)); } catch (err) { /* private mode: fine without it */ }
}

// The rep's name or email inside the letter, typed in place; while empty it shows a faint placeholder.
function sig(key, hint, saved) {
  return `<span class="sig" contenteditable="plaintext-only" role="textbox" spellcheck="false" aria-label="${hint}" data-k="${key}" data-hint="${hint}">${esc(saved[key] || '')}</span>`;
}

// The draft email as lines that reveal one after another, signed with the rep's details.
function letterHtml(draft, saved) {
  const lines = draft.split('\n');
  let subject = '';
  if (lines[0].startsWith('Subject:')) subject = lines.shift().replace('Subject:', '').trim();
  while (lines.length && !lines[0].trim()) lines.shift();
  lines.push('[Your email]');
  let html = `<div class="ln subject" style="--d:0ms">${esc(subject)}</div>`;
  for (let i = 0; i < lines.length; i++) {
    let text = esc(lines[i]);
    text = text.split('[Your name]').join(sig('name', 'Your name', saved));
    text = text.split('[Your email]').join(sig('email', 'Your email', saved));
    html += `<div class="ln${lines[i].trim() ? '' : ' gap'}" style="--d:${(i + 1) * 120}ms">${text}</div>`;
  }
  return html;
}

// The finished email as plain text; empty signature parts stay as [Your name] / [Your email].
function letterText(el) {
  const lines = el.querySelectorAll('.ln');
  if (!lines.length) return null;
  let body = '';
  for (let i = 1; i < lines.length; i++) {
    const line = lines[i].cloneNode(true);
    for (const part of line.querySelectorAll('.sig')) part.textContent = part.textContent.trim() || `[${part.dataset.hint}]`;
    body += line.textContent + '\n';
  }
  return { subject: lines[0].textContent, body: body.trim() };
}

// Copy text to the clipboard, with an older fallback.
async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
  } catch (err) {
    const area = document.createElement('textarea');
    area.value = text;
    document.body.append(area);
    area.select();
    document.execCommand('copy');
    area.remove();
  }
  toast('Copied');
}

// Where the detail and the email panel sit together: side by side on wide screens, stacked otherwise.
function pairRects() {
  const vw = window.innerWidth;
  const rect = targetRect();
  if (vw < 900) return { wide: false, flip: rect, panel: rect };
  const width = Math.min(600, (vw - 48) / 2);
  return {
    wide: true,
    flip: { left: vw / 2 - width - 8, top: rect.top, width, height: rect.height },
    panel: { left: vw / 2 + 8, top: rect.top, width, height: rect.height },
  };
}

// Contact: the detail slides left and the email panel slides out from behind it.
function openEngage() {
  const d = open.lead;
  if (!d || open.engage || !d.analysis) {
    if (d && !d.analysis) toast('The email is still being written');
    return;
  }
  const pair = pairRects();
  const panel = document.createElement('section');
  panel.className = 'engage';
  panel.setAttribute('aria-label', 'Email draft');
  panel.innerHTML = `
    <div class="engage-head">
      <button class="icon back-btn" type="button" aria-label="Back">${ico.back}</button>
      <span class="label">Email draft</span>
      <div class="actions">
        <button class="icon" data-act="copy" type="button" aria-label="Copy email">${ico.copy}</button>
        ${d.contact.phone ? `<a class="icon" href="tel:${esc(d.contact.phone.replace(/[^\d+]/g, ''))}" aria-label="Call">${ico.phone}</a>` : ''}
        <button class="icon" data-act="mail" type="button" aria-label="Open in mail app">${ico.mail}</button>
      </div>
    </div>
    <div class="letter"></div>`;
  // Wide: starts hidden behind the detail. Narrow: starts off the right edge and slides over it.
  if (pair.wide) place(panel, pair.flip);
  else place(panel, { left: window.innerWidth, top: pair.panel.top, width: pair.panel.width, height: pair.panel.height });
  panel.classList.toggle('over', !pair.wide);
  document.body.append(panel);
  open.engage = panel;
  if (pair.wide) place(open.flip, pair.flip);
  requestAnimationFrame(() => requestAnimationFrame(() => {
    panel.classList.add('show');
    place(panel, pair.panel);
  }));

  // A short "drafting" moment, then the lines appear (skipped when the device asks for less motion).
  const letterEl = panel.querySelector('.letter');
  const write = () => { letterEl.innerHTML = letterHtml(d.analysis.draft_email, me()); };
  if (calm.matches) write();
  else {
    letterEl.innerHTML = `<div class="drafting"><span class="spin">${ico.spin}</span>Drafting…</div>`;
    setTimeout(() => { if (open.engage === panel) write(); }, 1200);
  }

  // Typing a name or email in the letter remembers it for the next email. Enter finishes the field.
  letterEl.addEventListener('input', e => {
    const part = e.target.closest('.sig');
    if (!part) return;
    if (!part.textContent.trim()) part.textContent = ''; // empty again, so the placeholder shows
    const data = me();
    data[part.dataset.k] = part.textContent.trim();
    saveMe(data);
  });
  letterEl.addEventListener('keydown', e => {
    if (e.key === 'Enter' && e.target.closest('.sig')) {
      e.preventDefault();
      e.target.blur();
    }
  });
  panel.querySelector('.back-btn').addEventListener('click', () => closeEngage(false));
  panel.querySelector('[data-act="copy"]').addEventListener('click', () => {
    const mail = letterText(letterEl);
    if (mail) copyText(`Subject: ${mail.subject}\n\n${mail.body}`);
  });
  panel.querySelector('[data-act="mail"]').addEventListener('click', () => {
    const mail = letterText(letterEl);
    if (mail) window.location.href = `mailto:?subject=${encodeURIComponent(mail.subject)}&body=${encodeURIComponent(mail.body)}`;
  });
}

// Slide the email panel back behind the detail window.
function closeEngage(now) {
  const panel = open.engage;
  if (!panel) return;
  open.engage = null;
  if (now) {
    panel.remove();
    return;
  }
  const rect = open.rect;
  if (panel.classList.contains('over')) panel.style.left = `${window.innerWidth}px`;
  else {
    place(panel, rect);
    place(open.flip, rect);
  }
  panel.classList.remove('show');
  setTimeout(() => panel.remove(), 560);
}

// Keep the windows in place when the screen size changes (rotation, folding, phone keyboard).
function onResize() {
  fitNav();
  if (window.innerWidth >= 900) drawer(false);
  if (!open.flip) return;
  open.rect = targetRect();
  if (!open.engage) {
    place(open.flip, open.rect);
    return;
  }
  const pair = pairRects();
  open.engage.classList.toggle('over', !pair.wide);
  place(open.flip, pair.flip);
  place(open.engage, pair.panel);
}

// Show nav links that fit; move the rest into the menu, which only appears when needed.
function fitNav() {
  const nav = $('#nav');
  const links = $('#links');
  const list = $('#menuList');
  const btn = $('#menuBtn');
  while (list.firstElementChild) links.append(list.firstElementChild);
  btn.hidden = true;
  const room = () => nav.clientWidth - $('.brand').offsetWidth - 48 - (btn.hidden ? 0 : 48);
  if (links.scrollWidth <= room()) {
    menu(false);
    return;
  }
  btn.hidden = false;
  while (links.lastElementChild && links.scrollWidth > room()) list.prepend(links.lastElementChild);
}

// Open or close the nav menu (only shown when the links don't fit).
function menu(show) {
  $('#menuList').hidden = !show;
  $('#menuBtn').setAttribute('aria-expanded', String(show));
}

// Open or close the filter drawer on smaller screens.
function drawer(show) {
  $('#side').classList.toggle('open', show);
  $('#drawerScrim').hidden = !show;
}

// Wire up the page.
function init() {
  $('#menuBtn').innerHTML = ico.menu;
  $('.search-ico').innerHTML = ico.search;
  $('#filterBtn').innerHTML = ico.filter;
  $('#mapBtn').innerHTML = ico.expand;

  $('#filters').addEventListener('change', () => reloadSoon(150));
  $('#resetBtn').addEventListener('click', () => { $('#filters').reset(); $('#q').value = ''; reloadSoon(0); });
  $('#search').addEventListener('submit', e => { e.preventDefault(); reloadSoon(0); });
  $('#q').addEventListener('input', () => reloadSoon(350));
  $('#scrim').addEventListener('click', closeLead);
  $('#filterBtn').addEventListener('click', () => drawer(true));
  $('#drawerScrim').addEventListener('click', () => drawer(false));
  $('#menuBtn').addEventListener('click', () => menu($('#menuList').hidden));
  document.addEventListener('click', e => {
    if (!e.target.closest('#menuBtn')) menu(false);
  });
  document.addEventListener('keydown', e => {
    if (e.key !== 'Escape') return;
    if (open.engage) closeEngage(false);
    else if (open.flip) closeLead();
    else drawer(false);
  });
  window.addEventListener('resize', onResize);

  // The cards column is the scrolling area, so it is what the end-of-list marker is watched against.
  new IntersectionObserver(entries => {
    if (entries[0].isIntersecting) loadMore();
  }, { root: $('.feed'), rootMargin: '800px' }).observe($('#sentinel'));

  fitNav();
  if (document.fonts) document.fonts.ready.then(fitNav);
  loadMore();
}

init();
