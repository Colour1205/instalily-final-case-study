// LiLi map: a still preview under the filters and a full map window with zoom and recentre.

import { api, esc, ico, openLead, query, scrim } from './app.js';

const dark = window.matchMedia('(prefers-color-scheme: dark)');
// OpenStreetMap's own tiles; style.css tints them to match light or dark mode.
const tileUrl = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
const tileOpts = {
  maxZoom: 19,
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
};
const still = { zoomSnap: 0.25, zoomControl: false, dragging: false, scrollWheelZoom: false, doubleClickZoom: false, boxZoom: false, keyboard: false, touchZoom: false };

let data = null;
let mini = null;
let big = null;
let win = null;

// A colour from the page's theme (Leaflet can't read CSS variables itself).
function color(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

// Score bands for the dots (scores today run from about 12 to 68).
const bands = [[40, '--accent', '40+'], [25, '--p3', '25-39'], [0, '--p4', 'Under 25']];

// A Leaflet map with the themed tiles and an empty layer for the markers.
function makeMap(el, opts) {
  const map = L.map(el, opts);
  map.attributionControl.setPrefix(false);
  L.tileLayer(tileUrl, tileOpts).addTo(map);
  map.marks = L.layerGroup().addTo(map);
  return map;
}

// Draw the search centre, the radius and one dot per lead, then fit them all on screen.
function draw(map, popups) {
  map.marks.clearLayers();
  if (!data) return;
  const center = [data.center.lat, data.center.lng];
  const ring = L.circle(center, {
    radius: data.radius_miles * 1609.34,
    color: color('--ink'), weight: 1, dashArray: '4 6', fillColor: color('--accent'), fillOpacity: 0.05,
  }).addTo(map.marks);
  const pin = L.divIcon({ className: '', html: '<div class="pin"></div>', iconSize: [16, 16], iconAnchor: [8, 8] });
  L.marker(center, { icon: pin, keyboard: false, interactive: popups }).addTo(map.marks)
    .bindTooltip(`ZIP ${esc(data.center.zip)} · ${data.radius_miles} mi`);
  const bounds = L.latLng(center).toBounds(ring.getRadius() * 2);
  for (const p of data.points) {
    // Higher scores get the stronger colour (the last band starts at 0, so every score finds one).
    let fill = '';
    for (const [min, name] of bands) {
      if (!fill && p.score >= min) fill = color(name);
    }
    const dot = L.circleMarker([p.lat, p.lng], {
      radius: popups ? 6 : 3.5, weight: popups ? 1.5 : 0, color: color('--card'),
      fillColor: fill, fillOpacity: 0.9, interactive: popups,
    }).addTo(map.marks);
    if (popups) {
      dot.bindPopup(`<strong>${esc(p.name)}</strong><span class="label">Score ${Math.round(p.score)}</span>
        <button class="pill solid" type="button" data-id="${esc(p.gaf_id)}">Open</button>`);
    }
    bounds.extend([p.lat, p.lng]);
  }
  map.home = bounds;
  map.fitBounds(bounds, { padding: [12, 12] });
}

// Fetch the points for the current filters and search, then redraw both maps.
async function refresh() {
  const qs = query();
  try {
    data = await api(`/v1/map${qs ? '?' + qs : ''}`);
  } catch (err) {
    return;
  }
  if (mini) draw(mini, false);
  if (big) draw(big, true);
}

// Open the full map window.
function show() {
  let key = '';
  for (const [, name, label] of bands) key += `<span><i style="background:var(${name})"></i>${label}</span>`;
  win = document.createElement('section');
  win.className = 'map-win';
  win.setAttribute('role', 'dialog');
  win.setAttribute('aria-modal', 'true');
  win.setAttribute('aria-label', 'Map');
  win.innerHTML = `
    <div class="win-head">
      <span class="label">${data ? `${data.points.length} leads · ZIP ${esc(data.center.zip)} · ${data.radius_miles} mi` : 'Map'}</span>
      <span class="key">${key}</span>
      <button class="icon" type="button" data-act="close" aria-label="Close">${ico.close}</button>
    </div>
    <div class="big-map"></div>
    <div class="map-ctl">
      <button class="icon" type="button" data-act="in" aria-label="Zoom in">${ico.plus}</button>
      <button class="icon" type="button" data-act="out" aria-label="Zoom out">${ico.minus}</button>
      <button class="icon" type="button" data-act="home" aria-label="Recentre">${ico.target}</button>
    </div>`;
  document.body.append(win);
  scrim(true);
  big = makeMap(win.querySelector('.big-map'), { zoomSnap: 0.25, zoomControl: false });
  draw(big, true);
  requestAnimationFrame(() => {
    win.classList.add('show');
    big.invalidateSize();
    if (big.home) big.fitBounds(big.home, { padding: [24, 24] });
  });
  win.addEventListener('click', e => {
    const btn = e.target.closest('[data-act], [data-id]');
    if (!btn) return;
    if (btn.dataset.id) {
      const id = btn.dataset.id;
      hide();
      setTimeout(() => openLead(id, null), 200);
    } else if (btn.dataset.act === 'close') hide();
    else if (btn.dataset.act === 'in') big.zoomIn();
    else if (btn.dataset.act === 'out') big.zoomOut();
    else big.fitBounds(big.home, { padding: [24, 24] });
  });
  win.querySelector('[data-act="close"]').focus({ preventScroll: true });
}

// Close the full map window.
function hide() {
  if (!win) return;
  const el = win;
  const map = big;
  win = null;
  big = null;
  el.classList.remove('show');
  scrim(false);
  setTimeout(() => {
    map.remove();
    el.remove();
  }, 350);
}

// Fit the preview again after its box changes size (screen size or layout changes).
function resize() {
  if (!mini) return;
  mini.invalidateSize();
  if (mini.home) mini.fitBounds(mini.home, { padding: [12, 12] });
}

// Redraw the dots in the new colours when the device switches between light and dark.
function retheme() {
  if (mini) draw(mini, false);
  if (big) draw(big, true);
}

mini = makeMap('miniMap', still);
document.getElementById('mapBtn').addEventListener('click', show);
document.getElementById('scrim').addEventListener('click', hide);
document.addEventListener('keydown', e => { if (e.key === 'Escape') hide(); });
document.addEventListener('lili:filters', refresh);
dark.addEventListener('change', retheme);
new ResizeObserver(resize).observe(document.getElementById('miniMap'));
refresh();
