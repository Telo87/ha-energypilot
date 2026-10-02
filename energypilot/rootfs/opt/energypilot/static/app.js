/* EnergyPilot – single page app (no build step, no external dependencies) */
(() => {
  'use strict';

  // ------------------------------------------------------------------ utils
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const nf = (v, d = 0) => {
    const r = Math.round(Number(v) * 10 ** d) / 10 ** d;
    return (Object.is(r, -0) ? 0 : r).toLocaleString('de-DE', { minimumFractionDigits: d, maximumFractionDigits: d });  // never "-0,00"
  };
  // Re-render without jumping: automatic refreshes replace the page content,
  // which can briefly shorten the document and reset the scroll position.
  function keepScroll(fn) {
    const el = document.scrollingElement || document.documentElement;
    const top = el.scrollTop;
    fn();
    if (el.scrollTop !== top) el.scrollTop = top;
  }
  const reducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // DOM morphing: periodic refreshes only touch what actually changed, so hover
  // states, focus, tooltips and running animations survive. Children are matched
  // by data-key / id, otherwise by position. Elements marked data-keep are left
  // alone (their content is managed elsewhere, e.g. the chart). An element whose
  // data-flash value changes lights up briefly (device goes online …).
  const keyOf = (n) => (n.nodeType === 1 ? n.getAttribute('data-key') || n.id || null : null);
  function flash(el) {
    el.classList.remove('flash');
    void el.offsetWidth; // restart the animation
    el.classList.add('flash');
    clearTimeout(el._flashT);
    el._flashT = setTimeout(() => el.classList.remove('flash'), 1600);
  }
  function morphNode(a, b) {
    if (a.nodeType !== 1) { if (a.nodeValue !== b.nodeValue) a.nodeValue = b.nodeValue; return; }
    if (a.hasAttribute('data-keep') && b.hasAttribute('data-keep')) return;
    const changed = a.hasAttribute('data-flash') && b.hasAttribute('data-flash') && a.getAttribute('data-flash') !== b.getAttribute('data-flash');
    // while the page fades in, keep the stagger delay (style="--i") – removing it
    // would restart the running animation and make the element jump
    const keepI = a.style && a.closest('.page-in') ? a.style.getPropertyValue('--i') : '';
    Array.from(a.attributes).forEach((at) => { if (!b.hasAttribute(at.name) && !(at.name === 'style' && keepI)) a.removeAttribute(at.name); });
    Array.from(b.attributes).forEach((at) => { if (a.getAttribute(at.name) !== at.value && !(at.name === 'style' && keepI)) a.setAttribute(at.name, at.value); });
    if (keepI && b.hasAttribute('style')) { a.setAttribute('style', b.getAttribute('style')); a.style.setProperty('--i', keepI); }
    if (a.tagName === 'INPUT') {
      if (a.type === 'checkbox' || a.type === 'radio') a.checked = b.hasAttribute('checked');
      else if (a !== document.activeElement && a.value !== (b.getAttribute('value') || '')) a.value = b.getAttribute('value') || '';
    }
    if (a.tagName !== 'TEXTAREA') morphChildren(a, b);
    if (changed) flash(a);
  }
  function morphChildren(cur, next) {
    const keyed = new Map();
    Array.from(cur.childNodes).forEach((n) => { const k = keyOf(n); if (k) keyed.set(k, n); });
    const list = Array.from(next.childNodes);
    list.forEach((nb, i) => {
      const k = keyOf(nb);
      let na = k ? keyed.get(k) : cur.childNodes[i];
      if (na && k) keyed.delete(k);
      if (na && (na.nodeType !== nb.nodeType || na.nodeName !== nb.nodeName || (!k && keyOf(na)))) na = null;
      if (!na) { cur.insertBefore(nb, cur.childNodes[i] || null); return; }
      if (na !== cur.childNodes[i]) cur.insertBefore(na, cur.childNodes[i] || null);
      morphNode(na, nb);
    });
    while (cur.childNodes.length > list.length) cur.lastChild.remove();
  }
  function morph(target, html) {
    const tpl = document.createElement('template');
    tpl.innerHTML = html;
    morphChildren(target, tpl.content);
    animateCounts(target);
  }
  // first draw after the loading skeleton: replace (so the page fades in), later: morph
  function render(el, html) {
    if (!el.firstElementChild || el.querySelector(':scope > .card > .card-body > .skeleton')) { el.innerHTML = html; animateCounts(el); } else morph(el, html);
  }
  // one listener per element and event; redraws only swap the handler
  function on(el, type, fn) {
    if (!el) return;
    el._on = el._on || {};
    if (!el._on[type]) el.addEventListener(type, (e) => el._on[type](e));
    el._on[type] = fn;
  }

  // Numbers count up/down to their new value: <span data-count=key …>
  const counts = new Map();
  function cnt(key, text, unit = '') {
    const s = String(text);
    if (!/^-?[\d.]+(,\d+)?$/.test(s)) return esc(s);
    const dec = (s.split(',')[1] || '').length;
    const val = Number(s.replace(/\./g, '').replace(',', '.'));
    return `<span data-count="${esc(key)}" data-val="${val}" data-dec="${dec}" data-unit="${esc(unit)}">${s}</span>`;
  }
  function animateCounts(root) {
    root.querySelectorAll('[data-count]').forEach((el) => {
      const key = el.dataset.count; const to = Number(el.dataset.val); const dec = Number(el.dataset.dec); const unit = el.dataset.unit;
      const prev = counts.get(key);
      counts.set(key, { v: to, unit });
      const from = prev ? (prev.unit === unit ? prev.v : to) : 0;
      if (el._anim) cancelAnimationFrame(el._anim);
      if (from === to || reducedMotion()) return;
      const fmt = (v) => nf(v, dec);
      const t0 = performance.now(); const dur = prev ? 600 : 800;
      const step = (t) => {
        const p = Math.min(1, (t - t0) / dur); const e = 1 - (1 - p) ** 3;
        el.textContent = fmt(from + (to - from) * e);
        el._anim = p < 1 ? requestAnimationFrame(step) : null;
      };
      el.textContent = fmt(from);
      el._anim = requestAnimationFrame(step);
    });
  }
  const store = {
    get(k, d) { try { const v = localStorage.getItem('energypilot.' + k); return v === null ? d : JSON.parse(v); } catch { return d; } },
    set(k, v) { try { localStorage.setItem('energypilot.' + k, JSON.stringify(v)); } catch { /* ignore */ } },
  };


  const P = {
    grid: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
    target: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.5"/>',
    chart: '<path d="M3 3v18h18"/><path d="m7 15 4-5 4 3 5-7"/>',
    euro: '<path d="M18 7.5A6.5 6.5 0 1 0 18 16.5"/><path d="M4 10.5h9M4 13.5h9"/>',
    gear: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>',
    sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
    solar: '<path d="M4 20 6 10h12l2 10z"/><path d="M5 15h14M9.3 10 8.5 20M14.7 10l.8 10"/><path d="M12 2v3M5.6 4.6l1.5 1.5M18.4 4.6l-1.5 1.5"/>',
    moon: '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>',
    contrast: '<circle cx="12" cy="12" r="9"/><path d="M12 3a9 9 0 0 1 0 18z" fill="currentColor"/>',
    cloud: '<path d="M17.5 19a4.5 4.5 0 1 0-1.4-8.8A6 6 0 0 0 4.5 13 3 3 0 0 0 6 19z"/>',
    cloudSun: '<path d="M12 2v2M4.9 4.9l1.4 1.4M2 12h2M19.1 4.9l-1.4 1.4"/><path d="M15.9 9.7A4 4 0 0 0 8.2 10"/><path d="M17.5 21a3.5 3.5 0 1 0-1.1-6.8A4.5 4.5 0 0 0 8 16a2.5 2.5 0 0 0 .5 5z"/>',
    home: '<path d="m3 11 9-8 9 8"/><path d="M5 9.5V20h14V9.5"/>',
    car: '<path d="M5 17H3v-5l2-5h14l2 5v5h-2"/><path d="M3 12h18"/><circle cx="7.5" cy="17" r="2"/><circle cx="16.5" cy="17" r="2"/><path d="M9.5 17h5"/>',
    pin: '<path d="M12 21s-7-6.2-7-11.5A7 7 0 0 1 19 9.5C19 14.8 12 21 12 21z"/><circle cx="12" cy="9.5" r="2.5"/>',
    battery: '<rect x="2" y="7" width="17" height="10" rx="2"/><path d="M22 11v2"/><path d="M6 10v4M10 10v4"/>',
    plug: '<path d="M9 2v6M15 2v6"/><path d="M6 8h12v4a6 6 0 0 1-12 0z"/><path d="M12 18v4"/>',
    zap: '<path d="M13 2 4 14h7l-1 8 9-12h-7z"/>',
    menu: '<path d="M3 6h18M3 12h18M3 18h18"/>',
    message: '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
    x: '<path d="M18 6 6 18M6 6l12 12"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    trash: '<path d="M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>',
    edit: '<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="m13.5 6.5 4 4"/>',
    check: '<path d="M20 6 9 17l-5-5"/>',
    checkCircle: '<circle cx="12" cy="12" r="9"/><path d="m8 12.5 2.5 2.5L16 9.5"/>',
    alert: '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4M12 17h.01"/>',
    info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>',
    refresh: '<path d="M21 12a9 9 0 1 1-2.6-6.4"/><path d="M21 3v6h-6"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    chevron: '<path d="m9 6 6 6-6 6"/>',
    chevronL: '<path d="m15 6-6 6 6 6"/>',
    chevronDown: '<path d="m6 9 6 6 6-6"/>',
    search: '<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/>',
    trophy: '<path d="M8 21h8M12 17v4M7 4h10v5a5 5 0 0 1-10 0z"/><path d="M17 5h3v2a3 3 0 0 1-3 3M7 5H4v2a3 3 0 0 0 3 3"/>',
    database: '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5"/><path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>',
    sliders: '<path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6"/>',
    palette: '<path d="M12 3a9 9 0 0 0 0 18c1.1 0 1.8-.8 1.8-1.8 0-.5-.2-.9-.5-1.2-.3-.3-.5-.7-.5-1.2 0-1 .8-1.8 1.8-1.8H17a4 4 0 0 0 4-4c0-4.4-4-8-9-8z"/><circle cx="7.5" cy="11.5" r="1"/><circle cx="10.5" cy="7.5" r="1"/><circle cx="15" cy="7.5" r="1"/>',
    compass: '<circle cx="12" cy="12" r="9"/><path d="m15.5 8.5-2 5-5 2 2-5z"/>',
    journal: '<rect x="5" y="3" width="14" height="18" rx="2"/><path d="M9 7h6M9 11h6M9 15h4"/>',
    external: '<path d="M14 4h6v6M20 4l-9 9"/><path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>',
    wallet: '<path d="M20 7V5a2 2 0 0 0-2-2H5a2 2 0 0 0 0 4h15v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5"/><path d="M16 13h.01"/>',
  };
  const ic = (name, cls = '') => `<svg class="i ${cls}" viewBox="0 0 24 24" aria-hidden="true">${P[name] || ''}</svg>`;

  // -------------------------------------------------------------------- api
  async function api(path, opts = {}) {
    const init = { method: opts.method || 'GET', headers: {} };
    if (opts.body !== undefined) {
      init.headers['Content-Type'] = 'application/json';
      init.body = JSON.stringify(opts.body);
    }
    let res;
    try { res = await fetch('api/' + path, init); } catch (e) { throw new Error('Keine Verbindung zum Add-on.'); }
    let data = null;
    try { data = await res.json(); } catch { /* not json */ }
    if (!res.ok || !data || !data.ok) throw new Error((data && data.error) || `HTTP ${res.status}`);
    return data.data;
  }

  // ------------------------------------------------------------- formatting
  const fmtTime = (d) => d.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
  const fmtHour = (ts) => fmtTime(new Date(ts * 1000));
  const fmtDay = (ts) => new Date(ts * 1000).toLocaleDateString('de-DE', { weekday: 'short', day: '2-digit', month: '2-digit' });
  const fmtDate = (ts) => new Date(ts * 1000).toLocaleDateString('de-DE', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
  function fmtAgo(ts) {
    if (!ts) return 'nie';
    const s = Math.max(0, Date.now() / 1000 - ts);
    if (s < 60) return 'gerade eben';
    if (s < 3600) return `vor ${Math.round(s / 60)} min`;
    if (s < 86400) return `vor ${Math.round(s / 3600)} h`;
    return `vor ${Math.round(s / 86400)} Tagen`;
  }
  function fmtW(w) {
    if (w == null) return '–';
    const a = Math.abs(w);
    return a >= 1000 ? `${nf(w / 1000, a >= 10000 ? 1 : 2)} kW` : `${nf(w)} W`;
  }
  function fmtDur(h) {
    if (h == null) return '–';
    if (h >= 48) return `${nf(h / 24, 1)} Tage`;
    const m = Math.round(h * 60);
    return m < 60 ? `${m} min` : `${Math.floor(m / 60)} h${m % 60 ? ` ${m % 60} min` : ''}`;
  }
  // "heute 18:40", "morgen 06:15", "Do 07:00"
  function fmtWhen(ts, isEnd = false) {
    if (!ts) return '–';
    let d = new Date(ts * 1000);
    const midnight = isEnd && d.getHours() === 0 && d.getMinutes() === 0;
    if (midnight) d = new Date((ts - 60) * 1000);  // 00:00 is shown as 24:00 of the day before
    const day = localDay(d); const today = localDay();
    const pre = day === today ? 'heute' : day === shiftDay(today, 1) ? 'morgen' : d.toLocaleDateString('de-DE', { weekday: 'short' });
    return `${pre} ${midnight ? '24:00' : fmtTime(d)}`;
  }
  const MODE = { normal: ['Eigenverbrauch', 'home', 'ok'], hold: ['Akku halten', 'battery', 'warn'], charge: ['Aus dem Netz laden', 'plug', 'accent'] };
  const kwh = (v, d = 1) => (v == null ? '–' : `${nf(v, d)} kWh`);
  const pct = (v, d = 1) => (v == null ? '–' : `${nf(v, d)} %`);
  const signed = (v, d = 1) => (v == null ? '–' : `${v > 0 ? '+' : v < 0 ? '−' : '±'}${nf(Math.abs(v), d)}`);
  const ctkwh = (v, d = 1) => (v == null ? '–' : `${nf(v, d)} ct/kWh`);
  const localDay = (d = new Date()) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  const dayTs = (day) => new Date(`${day}T00:00:00`).getTime() / 1000;
  const shiftDay = (day, n) => { const d = new Date(`${day}T12:00:00`); d.setDate(d.getDate() + n); return localDay(d); };

  // Source colours: fixed per source (identity follows the entity, never its rank)
  const SRC_SLOT = { 'om:best_match': 1, 'om:icon_d2': 2, 'om:ecmwf_ifs025': 3, fs: 4, 'om:icon_eu': 5, 'om:gfs_seamless': 6, 'om:meteofrance_seamless': 7, sc: 8, 'om:knmi_seamless': 9, 'om:dmi_seamless': 10 };
  const srcColor = (s) => (s === 'ep' ? 'var(--text)' : s === 'nc' ? 'var(--text-2)' : SRC_SLOT[s] ? `var(--s${SRC_SLOT[s]})` : 'var(--s-other)');
  const BAND = { label: 'Spanne (80 %)', color: 'var(--band)' };
  const BASE = 'base';
  // series picker: all arrays, each array, household base load
  function seriesSelect(id, cur, arrays) {
    const opts = arrays.length > 1 ? [['_total', 'Alle Anlagen'], ...arrays.map((a) => [a.id, a.name])] : arrays.length ? [['_total', arrays[0].name]] : [];
    if (S.settings && S.settings.sensors.house) opts.push([BASE, 'Grundverbrauch']);
    if (opts.length < 2) return '';
    // its own bar above the other controls: it switches the whole page (production or consumption)
    return `<div class="view-switch"><span class="vs-label">Auswertung für</span><div class="seg big" id="${id}" role="tablist">${opts.map(([v, l]) => `<button type="button" role="tab" aria-selected="${cur === v}" data-v="${esc(v)}" class="${cur === v ? 'active' : ''}">${ic(v === BASE ? 'home' : 'solar')}${esc(l)}</button>`).join('')}</div></div>`;
  }
  const CLASS_LABEL = { sunny: ['Sonnig', 'sun'], mixed: ['Wechselhaft', 'cloudSun'], cloudy: ['Trüb', 'cloud'] };
  const HORIZONS = [['d1', 'Vortag', 'Prognose vom Vortag (vor Mitternacht) – die Grundlage für die Planung des nächsten Tages'], ['d0', 'Kurzfristig', 'Letzte Prognose vor der jeweiligen Stunde']];

  // ------------------------------------------------------------------ chart
  function niceMax(v) {
    if (!v || v <= 0) return 1;
    const e = 10 ** Math.floor(Math.log10(v)); const f = v / e;
    return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10) * e;
  }
  // bar with rounded data end (top for positive, bottom for negative values)
  function barPath(x, y0, y1, w, r) {
    const h = Math.abs(y1 - y0); r = Math.min(r, w / 2, h);
    if (h < 0.5) return '';
    if (y1 < y0) return `M${x},${y0}V${y1 + r}Q${x},${y1} ${x + r},${y1}H${x + w - r}Q${x + w},${y1} ${x + w},${y1 + r}V${y0}Z`;
    return `M${x},${y0}V${y1 - r}Q${x},${y1} ${x + r},${y1}H${x + w - r}Q${x + w},${y1} ${x + w},${y1 - r}V${y0}Z`;
  }
  /* Time chart: one optional bar series (measured values or prices) plus lines.
     c = { xs, step, bar: {label, values, cls, clsFor(i)}, lines: [{key,label,color,values}],
           fmt, axisFmt, head(ts), tick(ts), height, now, onClick(i) } */
  function timeChart(el, c) {
    if (!el) return;
    const n = c.xs.length;
    const vals = [...(c.bar ? c.bar.values : []), ...c.lines.flatMap((l) => l.values), ...(c.band ? c.band.hi : [])].filter((v) => v != null);
    if (!n || !vals.length) { el.innerHTML = `<div class="empty" style="padding:70px 0">${c.emptyText || 'Noch keine Daten.'}</div>`; return; }
    const W = Math.max(320, el.clientWidth); const H = c.height || 240;
    const pad = { l: 56, r: 10, t: 14, b: 26 };
    // axis: a "nice" step (1/2/2.5/5·10ⁿ) for about four gridlines, ends just above the data
    const hi = Math.max(0, ...vals); const lo = Math.min(0, ...vals);
    const stepV = c.maxY ? niceMax(c.maxY / 4) : niceMax((hi - lo > 1e-9 ? hi - lo : 1) / 4);
    const max = c.maxY || Math.max(stepV, Math.ceil((hi * 1.02) / stepV) * stepV);
    const min = lo < 0 ? Math.floor((lo * 1.02) / stepV) * stepV : 0;
    const cw = (W - pad.l - pad.r) / n;
    const x = (i) => pad.l + i * cw;
    const y = (v) => pad.t + ((max - v) / (max - min)) * (H - pad.t - pad.b);
    let grid = '';
    for (let k = Math.round(min / stepV); k * stepV <= max + stepV * 1e-6; k += 1) {
      const v = k * stepV; const yy = y(v).toFixed(1);
      grid += `<line class="${k === 0 ? 'zero' : 'grid-line'}" x1="${pad.l}" x2="${W - pad.r}" y1="${yy}" y2="${yy}"/><text class="axis" x="${pad.l - 8}" y="${Number(yy) + 4}" text-anchor="end">${(c.axisFmt || c.fmt)(v)}</text>`;
    }
    const every = Math.max(1, Math.ceil(64 / cw));
    const tick = c.tick || ((ts) => fmtHour(ts));
    for (let i = 0; i < n; i += 1) {
      if (c.tickAt ? !c.tickAt(c.xs[i], i) : i % every) continue;
      grid += `<text class="axis" x="${x(i) + (c.tickCenter ? cw / 2 : 0)}" y="${H - 7}" text-anchor="${i === 0 && !c.tickCenter ? 'start' : 'middle'}">${tick(c.xs[i])}</text>`;
    }
    let bars = '';
    if (c.bar) {
      const gap = cw > 8 ? 2 : cw > 3 ? 1 : 0;
      c.bar.values.forEach((v, i) => {
        if (v == null) return;
        const cls = `${c.bar.cls}${c.bar.clsFor ? ` ${c.bar.clsFor(i, v)}` : ''}`;
        bars += `<path class="${cls}" d="${barPath(x(i) + gap / 2, y(0), y(v), cw - gap, cw > 8 ? 4 : 1.5)}"/>`;
      });
    }
    let bandPath = '';
    if (c.band) {  // one closed shape per stretch where both bounds exist
      let seg = [];
      const flush = () => {
        if (seg.length > 1) {
          const top = seg.map((i) => `${(x(i) + cw / 2).toFixed(1)},${y(c.band.hi[i]).toFixed(1)}`);
          const bot = seg.slice().reverse().map((i) => `${(x(i) + cw / 2).toFixed(1)},${y(c.band.lo[i]).toFixed(1)}`);
          bandPath += `<path class="band" d="M${top.join('L')}L${bot.join('L')}Z" fill="${c.band.color}"/>`;
        }
        seg = [];
      };
      c.xs.forEach((_x, i) => { if (c.band.lo[i] != null && c.band.hi[i] != null) seg.push(i); else flush(); });
      flush();
    }
    let lines = '';
    c.lines.forEach((l) => {
      let d = ''; let pen = false;
      l.values.forEach((v, i) => {
        if (v == null) { pen = false; return; }
        d += `${pen ? 'L' : 'M'}${(x(i) + cw / 2).toFixed(1)},${y(v).toFixed(1)}`; pen = true;
      });
      if (d) lines += `<path class="ln${l.dash ? ' dash' : ''}" ${l.dash ? '' : 'pathLength="1" '}d="${d}" fill="none" stroke="${l.color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>`;
    });
    let nowMark = '';
    if (c.now && c.now >= c.xs[0] && c.now < c.xs[n - 1] + c.step) {
      const nx = (pad.l + ((c.now - c.xs[0]) / c.step) * cw).toFixed(1);
      nowMark = `<line class="now-line" x1="${nx}" x2="${nx}" y1="${pad.t - 4}" y2="${H - pad.b}"/><text class="now-label" x="${nx}" y="${pad.t - 5}" text-anchor="middle">jetzt</text>`;
    }
    const drawIn = !el.querySelector('svg');
    el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" style="height:${H}px" class="${drawIn && !c.noAnim ? 'draw-in' : ''}">
      <g class="gl">${grid}</g><rect class="hover-col" x="0" y="${pad.t}" width="${cw}" height="${H - pad.t - pad.b}" style="display:none"/>
      <g>${bars}</g>${bandPath}<g class="series">${lines}</g>${nowMark}
      <rect x="${pad.l}" y="0" width="${W - pad.l - pad.r}" height="${H}" class="hit-col" style="${c.onClick ? '' : 'cursor:default'}"/>
    </svg><div class="tip" style="display:none"></div>`;
    el.style.minHeight = `${H}px`;
    const svg = el.querySelector('svg'); const tip = el.querySelector('.tip'); const col = svg.querySelector('.hover-col');
    const idx = (ev) => {
      const r = svg.getBoundingClientRect();
      return Math.max(0, Math.min(n - 1, Math.floor((((ev.clientX - r.left) / r.width) * W - pad.l) / cw)));
    };
    const hit = svg.querySelector('.hit-col');
    hit.addEventListener('mousemove', (ev) => {
      const i = idx(ev); const r = svg.getBoundingClientRect();
      col.style.display = ''; col.setAttribute('x', x(i));
      const rows = [];
      if (c.bar && c.bar.values[i] != null) rows.push(`<div class="row-t"><span><i class="box" style="background:${c.bar.color}"></i>${esc(c.bar.label)}</span><span>${c.fmt(c.bar.values[i])}</span></div>`);
      c.lines.forEach((l) => { if (l.values[i] != null) rows.push(`<div class="row-t"><span><i style="background:${l.color}"></i>${esc(l.label)}</span><span>${c.fmt(l.values[i])}</span></div>`); });
      if (c.band && c.band.lo[i] != null && c.band.hi[i] != null) rows.push(`<div class="row-t"><span><i class="box" style="background:${c.band.color}"></i>${esc(c.band.label)}</span><span>${c.fmt(c.band.lo[i])} – ${c.fmt(c.band.hi[i])}</span></div>`);
      if (!rows.length) { tip.style.display = 'none'; return; }
      tip.innerHTML = `<b>${(c.head || fmtHour)(c.xs[i])}</b>${rows.join('')}`;
      tip.style.display = '';
      const cx = ((x(i) + cw / 2) / W) * r.width;
      const tw = tip.offsetWidth;
      tip.style.left = `${Math.max(tw / 2, Math.min(r.width - tw / 2, cx))}px`;
      tip.style.top = `${(pad.t / H) * r.height + 8}px`;
      tip.style.transform = 'translate(-50%, 0)';
    });
    hit.addEventListener('mouseleave', () => { col.style.display = 'none'; tip.style.display = 'none'; });
    if (c.onClick) hit.addEventListener('click', (ev) => c.onClick(idx(ev)));
  }
  // redraw charts when the width changes
  const charts = new Map();
  function chart(el, cfg) { if (!el) return; charts.set(el.id, cfg); timeChart(el, cfg); }
  let resizeT = 0;
  window.addEventListener('resize', () => {
    clearTimeout(resizeT);
    resizeT = setTimeout(() => charts.forEach((cfg, id) => { const el = document.getElementById(id); if (el) timeChart(el, { ...cfg, noAnim: true }); else charts.delete(id); }), 150);
  });

  // legend chips toggle lines; hidden sources are remembered per browser
  function legendHTML(bar, lines, hidden) {
    const all = store.get('legendAll', false);
    const shown = all ? lines : lines.filter((l) => !hidden.has(l.key));
    const more = lines.length - shown.length;
    const toggle = more ? `<button class="more" data-legend-more>+${more} weitere</button>`
      : all && lines.some((l) => hidden.has(l.key)) ? '<button class="more" data-legend-more>weniger</button>' : '';
    return `<div class="legend">${bar ? `<span class="static"><i class="box" style="background:${bar.color}"></i>${esc(bar.label)}</span>` : ''}${shown.map((l) => `<button data-series="${esc(l.key)}" class="${hidden.has(l.key) ? 'off' : ''}" aria-pressed="${!hidden.has(l.key)}"><i style="background:${l.color}"></i>${esc(l.label)}</button>`).join('')}${toggle}</div>`;
  }
  function hiddenSet(ranking, all) {
    const stored = store.get('hidden', null);
    if (stored) return new Set(stored.filter((s) => all.includes(s)));
    // first visit: show the three most accurate sources
    const top = (ranking && ranking.length ? ranking : all).slice(0, 3);
    return new Set(all.filter((s) => !top.includes(s) && !s.startsWith('load:')));  // consumption stays visible
  }
  function toggleHidden(key) {
    const cur = new Set(store.get('hidden', null) || []);
    if (!store.get('hidden', null)) $$('.legend button.off').forEach((b) => cur.add(b.dataset.series));
    if (cur.has(key)) cur.delete(key); else cur.add(key);
    store.set('hidden', [...cur]);
  }

  // ------------------------------------------------------------------ state
  const S = { cleanup: [], overview: null, settings: null, entities: null, pageAnim: false };
  const MEASURED = { label: 'Gemessen', color: 'var(--measured)' };

  // ------------------------------------------------------------------ pages
  const PAGES = [
    { id: 'dashboard', title: 'Übersicht', icon: 'grid', section: 'Heute' },
    { id: 'plan', title: 'Planung', icon: 'clock' },
    { id: 'prices', title: 'Strompreise', icon: 'euro' },
    { id: 'day', title: 'Tagesverlauf', icon: 'chart', section: 'Auswertung' },
    { id: 'accuracy', title: 'Prognose-Check', icon: 'target' },
    { id: 'journal', title: 'Protokoll', icon: 'journal' },
    { id: 'costs', title: 'Kosten', icon: 'wallet' },
    { id: 'setup', title: 'Einrichtung', icon: 'checkCircle', section: 'Verwaltung' },
    { id: 'settings', title: 'Einstellungen', icon: 'gear' },
  ];
  // small number in the menu: problems (red), otherwise notes that need a look (orange)
  function setupBadge() {
    const sm = (S.check && S.check.summary) || {};
    if (sm.err) return `<span class="badge count" title="${sm.err} ${sm.err === 1 ? 'Problem' : 'Probleme'}">${sm.err}</span>`;
    if (sm.warn) return `<span class="badge count warn" title="${sm.warn} ${sm.warn === 1 ? 'Hinweis' : 'Hinweise'}">${sm.warn}</span>`;
    return '';
  }
  function renderNav() {
    const cur = currentPage();
    $('#nav').innerHTML = PAGES.map((p) => `${p.section ? `<div class="nav-section">${p.section}</div>` : ''}
      <a href="#/${p.id}" class="${p.id === cur ? 'active' : ''}">${ic(p.icon)}<span>${p.title}</span>${p.id === 'setup' ? setupBadge() : ''}</a>`).join('');
  }
  function currentPage() {
    const id = (location.hash.replace(/^#\/?/, '').split('?')[0]) || 'dashboard';
    return PAGES.some((p) => p.id === id) ? id : 'dashboard';
  }
  const query = () => new URLSearchParams(location.hash.split('?')[1] || '');
  function setHeader(title, sub = '', actions = '') {
    $('#pageTitle').textContent = title;
    $('#pageSub').innerHTML = sub;
    $('#pageActions').innerHTML = actions;
  }
  const STAGGER = ':scope > .grid > .card, .list > .list-item, tbody > tr';
  let pageAnimT = 0;
  function pageIn(content) {
    const skel = content.children.length === 1 && content.querySelector(':scope > .card > .card-body > .skeleton');
    content.classList.remove('page-in');
    void content.offsetWidth;
    $$(STAGGER, content).slice(0, 20).forEach((nd, i) => nd.style.setProperty('--i', i));
    content.classList.add('page-in');
    clearTimeout(pageAnimT);
    pageAnimT = setTimeout(() => content.classList.remove('page-in'), 1500);
    return !skel;
  }
  function watchPageIn() {
    const content = $('#content');
    new MutationObserver(() => {
      if (!S.pageAnim || !content.firstElementChild) return;
      if (pageIn(content)) S.pageAnim = false;
    }).observe(content, { childList: true });
  }

  let renderToken = 0;
  const stale = (token) => token !== renderToken;
  async function navigate() {
    S.cleanup.forEach((fn) => { try { fn(); } catch { /* ignore */ } });
    S.cleanup = [];
    charts.clear();
    renderToken += 1;
    const page = currentPage();
    renderNav();
    $('#app').classList.remove('nav-open');
    const content = $('#content');
    S.pageAnim = true;
    counts.clear();
    content.innerHTML = loading();
    window.scrollTo(0, 0);
    setHeader(PAGES.find((p) => p.id === page).title);
    try { await RENDER[page](content, renderToken); } catch (e) { content.innerHTML = errorBox(e.message); }
  }
  async function loadSettings() { S.settings = await api('settings'); return S.settings; }
  async function loadEntities(force = false) {
    if (!S.entities || force) S.entities = await api('entities');
    return S.entities;
  }

  const refreshBtn = () => `<button class="btn" id="refreshBtn" title="Prognosen, Preise und Messwerte jetzt abrufen">${ic('refresh')}<span class="hide-sm">Jetzt abrufen</span></button>`;
  function bindRefresh(after) {
    const b = $('#refreshBtn');
    if (b) b.addEventListener('click', () => withBusy(b, async () => {
      try { await api('refresh', { method: 'POST' }); toast('Abruf gestartet – die Daten sind in wenigen Sekunden da.', 'info'); setTimeout(after, 6000); } catch (e) { toast(e.message, 'err'); }
    }));
  }

  // ---------------------------------------------------------------- welcome
  function welcome(el) {
    el.innerHTML = `<div class="card"><div class="card-body">${empty('solar', 'Willkommen bei EnergyPilot',
      'Lege zuerst deine PV-Anlagen an – mit Leistung, Neigung, Ausrichtung und dem Leistungs- oder Energiesensor des Wechselrichters. Danach sammelt EnergyPilot stündlich Prognosen mehrerer Wetterdienste, liest die tatsächliche Erzeugung rückwirkend aus Home Assistant und zeigt, welche Prognose bei dir am genauesten ist.',
      `<a class="btn primary" href="#/settings?tab=arrays&add=1">${ic('plus')}PV-Anlage anlegen</a>`)}</div></div>`;
  }

  // -------------------------------------------------------------- dashboard
  async function renderDashboard(el, token) {
    let day = null; let tomorrow = null; let loadDay = null; let loadTomorrow = null; let lastDayLoad = 0; let drawn = false;
    const load = async () => {
      const ov = await api('overview');
      if (stale(token)) return;
      S.overview = ov;
      if (!ov.arrays.length) { setHeader('Übersicht'); welcome(el); return; }
      if (Date.now() - lastDayLoad > 5 * 60000) {
        const today = localDay();
        [day, tomorrow, loadDay, loadTomorrow] = await Promise.all([api(`day?day=${today}`), api(`day?day=${shiftDay(today, 1)}`),
          ov.load ? api(`day?day=${today}&series=base`) : null, ov.load ? api(`day?day=${shiftDay(today, 1)}&series=base`) : null]);
        lastDayLoad = Date.now();
        if (stale(token)) return;
      }
      draw(ov);
    };
    const draw = (ov) => {
      setHeader('Übersicht', ov.demo ? '<span class="badge warn">Demo-Modus</span>' : `${ov.arrays.length} PV-Anlage${ov.arrays.length > 1 ? 'n' : ''} · ${nf(ov.arrays.reduce((s, a) => s + a.kwp, 0), 1)} kWp`, refreshBtn());
      bindRefresh(() => { lastDayLoad = 0; load(); });
      const lv = ov.live.values || {};
      const pvKeys = ov.arrays.map((a) => `pv:${a.id}`);
      const asleep = new Set(ov.asleep || []);
      // an inverter without light is switched off: its sensor is "unavailable", the production is 0
      const pvW = (a) => { const x = lv[`pv:${a.id}`]; return x && x.unit === 'W' && x.value != null ? x.value : asleep.has(a.id) && a.sensor ? 0 : null; };
      const pvVals = ov.arrays.map(pvW).filter((v) => v != null);
      const pvNow = pvVals.length ? pvVals.reduce((a, b) => a + b, 0) : null;
      const allAsleep = ov.arrays.length > 0 && ov.arrays.every((a) => asleep.has(a.id));
      const val = (k) => (lv[k] ? lv[k].value : null);
      const grid = val('grid'); const soc = val('battery_soc'); const bp = val('battery_power');
      const best = ov.forecasts.find((f) => f.source === ov.best) || ov.forecasts.find((f) => f.source === 'om:best_match');
      const pr = ov.price;
      const plan = ov.plan; const rt = plan && plan.runtime;
      const todayPrices = ov.prices.filter((s) => s.ts < dayTs(shiftDay(localDay(), 1)));
      const avg = todayPrices.length ? todayPrices.reduce((a, s) => a + s.price, 0) / todayPrices.length : null;
      const missing = (k) => '<span class="faint">Sensor in den Einstellungen wählen</span>';
      const kpi = (key, icon, cls, label, value, unit, foot) => `<div class="card kpi" data-key="${key}"><div class="kpi-label"><span class="kpi-icon ${cls}">${ic(icon)}</span>${label}</div><div class="kpi-value">${value}${unit ? `<small>${unit}</small>` : ''}</div><div class="kpi-foot">${foot}</div></div>`;
      const w = (k, v) => (v == null ? '–' : cnt(k, nf(Math.abs(v) >= 1000 ? v / 1000 : v, Math.abs(v) >= 1000 ? 2 : 0)));
      const wu = (v) => (v == null ? '' : Math.abs(v) >= 1000 ? 'kW' : 'W');
      // "Jetzt": what to do + where the power flows – the most important information first
      const flowNode = (icon, cls, label, value, sub) => `<div class="flow-node"><div class="fn-head"><span class="kpi-icon ${cls}">${ic(icon)}</span>${label}</div><div class="fn-value">${value}</div><div class="fn-sub">${sub}</div></div>`;
      const wv = (k, v) => `${w(k, v)}${v == null ? '' : `<small>${wu(v)}</small>`}`;
      const m = plan && plan.ok ? MODE[plan.decision] : null;
      const decision = m ? `<div class="now-decision m-${plan.decision}">
          <div class="now-kicker">Empfehlung jetzt${plan.at ? ` <span class="faint" style="text-transform:none;letter-spacing:0;font-weight:500">· Stand ${fmtHour(plan.at)}</span>` : ''}</div>
          <div class="now-title"><span class="avatar ${m[2]}">${ic(m[1])}</span>${esc(plan.label)}</div>
          <p class="muted">${esc(plan.text)}</p>
          <div class="row wrap" style="gap:8px"><span class="badge ${plan.buy_now ? 'accent' : ''}">Strom kaufen: ${plan.buy_now ? 'ja' : 'nein'}</span><a class="btn sm" href="#/plan">${ic('battery')}Zur Planung</a><a class="btn sm" href="#/plan?why=1">${ic('info')}Warum?</a></div></div>`
        : `<div class="now-decision"><div class="now-kicker">Empfehlung jetzt</div><div class="now-title">Noch kein Plan</div><p class="muted">${esc((plan && plan.reason) || 'Wird berechnet …')}</p></div>`;
      const flows = [
        flowNode('solar', 'warn', 'PV-Erzeugung', wv('pv', pvNow), pvVals.length ? `${allAsleep && !pvVals.some((v) => v > 0) ? 'Wechselrichter aus – keine Sonne' : ov.arrays.map((a) => { const x = lv[`pv:${a.id}`]; const w = pvW(a); return `${esc(a.name)} ${w != null ? fmtW(w) : x && x.value != null ? 'Zähler' : '–'}`; }).join(' · ')}${nowcastText(plan)}` : missing()),
        flowNode('home', '', 'Hausverbrauch', wv('house', val('house')), lv.house ? (ov.load ? `Grundverbrauch heute ~${nf(ov.load.today, 1)} kWh` : 'aktuell') : missing()),
        flowNode('battery', 'ok', 'Akku', soc == null ? '–' : `${cnt('soc', nf(soc, 0))}<small>%</small>`, `${bp == null ? (lv.battery_soc ? 'Ladezustand' : missing()) : bp > 30 ? `lädt mit ${fmtW(bp)}` : bp < -30 ? `entlädt mit ${fmtW(-bp)}` : 'Ruhezustand'}${rt && (rt.empty_at || rt.until) ? ` · Prognose: ${rt.empty_at ? `leer ${fmtWhen(rt.empty_at).replace(' ', ' um ')}` : `reicht über ${fmtWhen(rt.until, true)} hinaus`}` : ''}`),
        // like the battery card: the title names the device, the line below says which way the power flows
        flowNode('plug', grid != null && grid < -20 ? 'ok' : '', 'Netz', wv('grid', grid == null ? null : Math.abs(grid)), lv.grid ? (grid > 20 ? '<b>Netzbezug</b> – Strom wird gekauft' : grid < -20 ? '<b>Einspeisung</b> – Überschuss geht ins Netz' : 'ausgeglichen – kein Bezug, keine Einspeisung') : missing()),
      ].join('');
      const nowCard = `<div class="card now-card"><div class="card-body now-grid">${decision}<div class="flow-grid">${flows}</div></div></div>`;
      const kpis = [
        kpi('price', 'euro', pr && avg != null && pr.price <= avg ? 'ok' : 'warn', 'Strompreis jetzt', pr ? cnt('price', nf(pr.price, 1)) : '–', pr ? 'ct/kWh' : '', pr ? `Börse ${nf(pr.spot, 1)} ct · Ø heute ${nf(avg, 1)} ct` : 'noch keine Preise'),
        kpi('today', 'sun', 'up', 'PV heute', cnt('prod', nf(ov.produced_kwh, 1)), 'kWh', best ? `Prognose ${nf(best.today, 1)} kWh${ov.pv_range ? ` (${nf(ov.pv_range.today[0], 0)}–${nf(ov.pv_range.today[1], 0)})` : ''} · morgen ${nf(best.tomorrow, 1)} kWh` : 'noch keine Prognose'),
        ov.load ? kpi('load', 'home', '', 'Grundverbrauch heute', `~${cnt('lt', nf(ov.load.today, 1))}`, 'kWh', `Prognose ohne E-Auto und Heizstab · morgen ~${nf(ov.load.tomorrow, 1)} kWh`) : '',
      ].join('');

      const ranking = ov.ranking || [];
      const sources = day ? Object.keys(day.forecasts) : [];
      const loadKey = 'load:ep';
      const hidden = hiddenSet(ranking, [...sources, loadKey]);
      const lines = sources.sort((a, b) => (ranking.indexOf(a) + 1 || 99) - (ranking.indexOf(b) + 1 || 99)).map((s) => ({ key: s, label: day.labels[s], color: srcColor(s) }));
      if (loadDay && loadTomorrow && loadDay.forecasts.ep) lines.push({ key: loadKey, label: 'Verbrauch (Prognose)', color: 'var(--s7)', dash: true });
      const statusRows = Object.entries(ov.status).filter(([k]) => !k.startsWith('act:') || !ov.status[k].ok).map(([k, s]) => `<div class="list-item"><span class="dot ${s.ok ? 'ok' : 'err'}"></span><div class="grow"><div class="title">${esc(k === 'price' ? 'Börsenstrompreis' : k === 'actual' ? 'Messwerte aus Home Assistant' : k === 'ha' ? 'Home Assistant' : s.label)}</div><div class="meta ${s.ok ? '' : 'err'}">${s.ok ? `abgerufen ${fmtAgo(s.at)}` : esc(s.text)}</div></div></div>`).join('');
      const acc = (ov.accuracy || []).slice(0, 5);
      const bf = ov.backfill;
      const chk = S.check && S.check.summary.err ? `<a class="notice setup-hint" href="#/setup">${ic('alert')}<div><b>${S.check.summary.err} ${S.check.summary.err === 1 ? 'Einstellung braucht' : 'Einstellungen brauchen'} Aufmerksamkeit</b> – zur Einrichtung</div></a>` : '';
      el.innerHTML = `${chk}${nowCard}<div class="grid kpis">${kpis}</div>
        <div class="grid dash">
          <div class="card"><div class="card-head"><h2>PV-Erzeugung &amp; Verbrauch – heute und morgen <span class="sub">stündlich · Prognose kurzfristig</span></h2></div>
            <div class="card-body">${legendHTML({ ...MEASURED, label: 'Gemessen', color: 'var(--measured)' }, lines, hidden)}<div class="chart tall" id="pvChart"></div></div></div>
          <div class="card"><div class="card-head"><h2>Genauigkeit <span class="sub">Rangliste · letzte 30 Tage · Prognose vom Vortag</span></h2><a class="btn sm" href="#/accuracy">Details</a></div>
            <div class="card-body flush"><div class="list">${acc.length ? acc.map((r, i) => `<div class="list-item"><span class="rank ${i === 0 ? 'r1' : ''}">${i + 1}</span><span class="swatch-dot" style="background:${srcColor(r.source)}"></span><div class="grow"><div class="title">${esc(r.label)}</div><div class="meta">Fehler je Stunde Ø ${pct(r.nmae_pct, 0)} · je Tag Ø ${pct(r.day_nmae_pct, 0)} · ${r.days} Tage</div></div><b class="num" title="Genauigkeit = 100 % minus Fehler je Stunde">${pct(r.score, 0)}</b></div>`).join('')
              : `<div class="muted" style="padding:6px 18px 14px;font-size:13px">Sobald Messwerte und Prognosen für einige Tage vorliegen, erscheint hier die Rangliste der Prognosequellen.</div>`}</div></div></div>
        </div>
        <div class="grid dash">
          <div class="card"><div class="card-head"><h2>Strompreis heute &amp; morgen <span class="sub">inkl. Aufschläge und MwSt</span></h2><a class="btn sm" href="#/prices">Details</a></div>
            <div class="card-body"><div class="chart" id="priceChart"></div></div></div>
          <div class="card"><div class="card-head"><h2>Datenquellen</h2></div>
            <div class="card-body flush">${bf.running ? `<div style="padding:4px 18px 12px"><div class="muted" style="font-size:13px">${ic('database')} ${esc(bf.text)} (${bf.done}/${bf.total})</div><div class="progress"><i style="width:${(bf.done / Math.max(1, bf.total)) * 100}%"></i></div></div>` : ''}
              <div class="list status-list">${statusRows || '<div class="muted" style="padding:6px 18px 14px;font-size:13px">Erster Abruf läuft …</div>'}</div></div></div>
        </div>`;
      // PV chart: today + tomorrow
      if (day && tomorrow) {
        const xs = [...day.hours, ...tomorrow.hours];
        const bar = { ...MEASURED, cls: 'bar-m', values: [...day.actual, ...tomorrow.actual] };
        const series = (d, key) => (key === loadKey ? ((d === day ? loadDay : loadTomorrow).forecasts.ep || {}).d0 : (d.forecasts[key] || {}).d0) || d.hours.map(() => null);
        const ln = lines.filter((l) => !hidden.has(l.key)).map((l) => ({ ...l, values: [...series(day, l.key), ...series(tomorrow, l.key)] }));
        const bd = (d, k) => ((d.band || {}).d0 || {})[k] || d.hours.map(() => null);
        const band = !hidden.has('ep') && sources.includes('ep') ? { ...BAND, lo: [...bd(day, 'lo'), ...bd(tomorrow, 'lo')], hi: [...bd(day, 'hi'), ...bd(tomorrow, 'hi')] } : null;
        chart($('#pvChart'), { xs, step: 3600, bar, lines: ln, band, fmt: (v) => fmtW(v).replace('W', 'Wh'), axisFmt: (v) => (v >= 1000 ? `${nf(v / 1000, 1)} kWh` : `${nf(v)} Wh`), head: (ts) => `${fmtDay(ts)} ${fmtHour(ts)}–${fmtHour(ts + 3600)}`, tick: (ts) => (new Date(ts * 1000).getHours() === 0 ? fmtDay(ts) : fmtHour(ts)), tickAt: (ts) => new Date(ts * 1000).getHours() % 6 === 0, height: 280, now: ov.now, noAnim: drawn, onClick: (i) => { location.hash = `#/day?d=${i < day.hours.length ? day.day : tomorrow.day}`; } });
        $$('.legend button[data-series]', el).forEach((b) => b.addEventListener('click', () => { toggleHidden(b.dataset.series); draw(S.overview); }));
      }
      priceChart($('#priceChart'), ov.prices, ov.now, 200);
      drawn = true;
    };
    await load();
    loadCheck().then(() => { if (!stale(token) && S.overview) draw(S.overview); }).catch(() => {});
    const timer = setInterval(() => { if (!document.hidden) load().catch(() => {}); }, 15000);
    S.cleanup.push(() => clearInterval(timer));
  }

  function priceChart(el, slots, now, height = 220) {
    if (!el) return;
    const xs = slots.map((s) => s.ts);
    const step = slots.length > 1 ? slots[1].ts - slots[0].ts : 900;
    const values = slots.map((s) => s.price);
    chart(el, {
      xs, step, lines: [], height, now,
      bar: { label: 'Strompreis', color: 'var(--price)', cls: 'bar-p', values, clsFor: (i, v) => `${v < 0 ? 'neg' : ''} ${xs[i] + step <= now ? 'past' : ''}` },
      fmt: (v) => ctkwh(v, 2), axisFmt: (v) => `${nf(v)} ct`,
      head: (ts) => `${fmtDay(ts)} ${fmtHour(ts)}–${fmtHour(ts + step)}`,
      tick: (ts) => (new Date(ts * 1000).getHours() === 0 ? fmtDay(ts) : fmtHour(ts)),
      tickAt: (ts) => { const d = new Date(ts * 1000); return d.getMinutes() === 0 && d.getHours() % 6 === 0; },
      emptyText: 'Noch keine Preise.',
    });
  }

  // where the power comes from while the battery rests – from the live values
  function coverText(lv) {
    const pv = Object.entries(lv).filter(([k, v]) => k.startsWith('pv:') && v && v.unit === 'W' && v.value != null).reduce((a, [, v]) => a + Math.max(0, v.value), 0);
    const grid = lv.grid && lv.grid.value;
    if (grid != null && grid > 50) return pv > 50 ? `Verbrauch: ${fmtW(pv)} aus PV, ${fmtW(grid)} aus dem Netz` : `Verbrauch kommt aus dem Netz (${fmtW(grid)})`;
    if (pv > 50) return grid != null && grid < -50 ? `PV deckt den Verbrauch – ${fmtW(-grid)} Überschuss gehen ins Netz` : `PV deckt den Verbrauch (${fmtW(pv)})`;
    return 'der Verbrauch wird ohne Akku gedeckt';
  }

  // how the last hour compares with the forecast (drives the correction of the next hours)
  function nowcastText(plan) {
    const n = plan && plan.nowcast;
    if (!n || !n.factor || Math.abs(n.factor - 1) < 0.05) return '';
    return ` · letzte Stunde ${signed((n.factor - 1) * 100, 0)} % zur Prognose`;
  }

  // ------------------------------------------------------------------- plan
  // "Warum dieser Plan?" - built from the plan itself (see explain.py)
  // "heute 14:00–16:00", over midnight "heute 22:00 – morgen 06:00"
  const span = (a, e) => (localDay(new Date(a * 1000)) === localDay(new Date((e - 1) * 1000))
    ? `${fmtWhen(a)}–${new Date(e * 1000).getHours() === 0 ? '24:00' : fmtHour(e)}` : `${fmtWhen(a)} – ${fmtWhen(e, true)}`);
  function whyItem(i, b) {
    const use = i.use_start ? `für <b>${span(i.use_start, i.use_end)}</b> aufgehoben, wenn Netzstrom Ø ${ctkwh(i.price_use)} kostet (bis ${ctkwh(i.price_use_max)})` : null;
    if (i.mode === 'charge') {
      return `<b>${span(i.start, i.end)}: Aus dem Netz laden</b> – ${kwh(i.energy_kwh)} zu Ø ${ctkwh(i.price_now)}, danach steht der Akku bei ${nf(i.soc_end, 0)} %. `
        + (use ? `Die Energie wird ${use}. Nach ${nf(100 - b.efficiency * 100, 0)} % Lade- und Entladeverlusten bleiben je gekaufter kWh etwa <b>${nf(i.gain_ct_per_kwh, 1)} ct</b> Vorteil.`
          : 'Sie steht bis zum Ende des Planungszeitraums bereit – der Plan bewertet die Restenergie im Akku mit einem vorsichtigen Preis.');
    }
    const gaps = i.gaps && i.gaps.length ? ` In ${i.gaps.length === 1 ? 'einer Stunde' : `${i.gaps.length} Stunden`} dazwischen (${i.gaps.map((g) => fmtHour(g)).join(', ')}) entlädt er trotzdem kurz – der Vorrat reicht dafür, und die Preise unterscheiden sich in dieser Zeit kaum.` : '';
    return `<b>${span(i.start, i.end)}: Akku halten</b> – Netzstrom kostet in dieser Zeit Ø ${ctkwh(i.price_now)}. Statt den Akku zu leeren, kommen die ${kwh(i.energy_kwh)} für den Verbrauch aus dem Netz. `
      + (use ? `Die Energie im Akku wird ${use}${i.gain_ct_per_kwh != null ? ` – Vorteil etwa <b>${nf(i.gain_ct_per_kwh, 1)} ct je kWh</b>` : ''}.` : 'Die Energie im Akku bleibt für das Ende des Planungszeitraums.') + gaps;
  }
  function whyShort(p, st) {  // one line for the hour table
    const i = ((p.why || {}).items || []).find((x) => st.ts >= x.start && st.ts < x.end);
    if (!i || st.mode !== i.mode) return i ? 'Kurz entladen – der Vorrat reicht dafür, die Preise unterscheiden sich in dieser Zeit kaum' : '';
    if (!i.use_start) return '';
    return i.mode === 'charge' ? `Günstig laden (Ø ${nf(i.price_now, 1)} ct) für ${span(i.use_start, i.use_end)} (Ø ${nf(i.price_use, 1)} ct)`
      : `Akku für ${span(i.use_start, i.use_end)} aufheben (Ø ${nf(i.price_use, 1)} statt ${nf(i.price_now, 1)} ct)`;
  }
  function planWhy(p) {
    const w = p.why || {}; const base = w.baseline || {}; const b = p.battery;
    const items = w.items || [];
    const noPlan = base.empty_at
      ? `Ohne Eingriff wäre der Akku <b>${fmtWhen(base.empty_at).replace(' ', ' um ')}</b> auf der Reserve von ${nf(b.min_soc, 0)} %${base.price_after != null ? `; danach würde Netzstrom für Ø ${ctkwh(base.price_after)} (bis ${ctkwh(base.price_after_max)}) gekauft` : ''}.`
      : `Ohne Eingriff reicht der Akku laut Prognose bis zum Ende des Planungszeitraums (${fmtWhen(p.horizon_end, true)}).`;
    let reason = '';
    if (!items.length) {
      reason = w.reason === 'enough' ? 'Deshalb gibt es nichts zu verschieben: In keiner Stunde fehlt der Akku. Halten würde nur Netzstrom kaufen, ohne später etwas zu sparen.'
        : w.reason === 'expensive_first' ? `Der Akku wird ohnehin in den teureren Stunden entladen (dort Ø ${ctkwh(base.price_before)}); danach ist Netzstrom mit Ø ${ctkwh(base.price_after)} nicht teurer. Halten würde teuren gegen billigeren Strom tauschen.`
          : `Vorher kostet Netzstrom Ø ${ctkwh(base.price_before)}, danach Ø ${ctkwh(base.price_after)}. Halten oder Laden brächte im ganzen Zeitraum weniger als ${nf(w.min_savings_ct, 0)} ct – dafür lohnt kein Eingriff.`;
      if (base.empty_at && base.price_after_max != null) {
        reason += b.grid_charge
          ? ` Laden aus dem Netz lohnt sich nicht: Selbst der günstigste Preis (${ctkwh(base.cheapest_price)} ${fmtWhen(base.cheapest_at).replace(' ', ' um ')}) wird durch die Verluste zu ${ctkwh(base.charge_cost)} je kWh aus dem Akku – ${base.charge_cost >= base.price_after_max ? 'teurer als' : 'kaum günstiger als'} der Netzstrom später (bis ${ctkwh(base.price_after_max)}).`
          : ' Laden aus dem Netz ist in den Einstellungen ausgeschaltet.';
      }
    }
    const caution = { 0: 'aus', 0.5: 'mittel', 1: 'vorsichtig' }[Number(b.pv_caution ?? 0.5)] || 'mittel';
    modal({
      title: 'Warum dieser Plan?', wide: true,
      body: `<p class="explain">${noPlan}</p>
        ${items.length ? `<div class="why-list">${items.map((i) => `<div class="why-item m-${i.mode}"><span class="badge ${MODE[i.mode][2]}">${ic(MODE[i.mode][1])}${MODE[i.mode][0]}</span><p>${whyItem(i, b)}</p></div>`).join('')}</div>
          <p class="explain">Stromkosten bis ${fmtWhen(p.horizon_end, true)}: <b>${nf(p.cost_eur, 2)} €</b> mit Plan statt ${nf(p.baseline_eur, 2)} € ohne – Ersparnis ${nf(p.savings_eur, 2)} €.</p>`
          : `<div class="notice info" style="margin-bottom:14px">${ic('home')}<div><b>Der Plan bleibt im Eigenverbrauch.</b> ${reason}</div></div>`}
        <details class="why-rules"><summary>${ic('chevron')}So rechnet der Planer</summary><ul>
          <li><b>Zeitraum:</b> Stunde für Stunde bis ${fmtWhen(p.horizon_end, true)} – so weit Strompreise bekannt sind (die für morgen erscheinen gegen 13 Uhr). Neu berechnet wird alle 5 Minuten mit dem aktuellen Ladezustand.</li>
          <li><b>Grundlage:</b> PV-Prognose ${esc(p.pv_source || 'Open-Meteo Auto')}${p.nowcast && p.nowcast.factor ? ', für die nächsten Stunden live korrigiert' : ''}, Verbrauchsprognose (Grundverbrauch ohne E-Auto und Heizstab) und die Strompreise inklusive aller Aufschläge.</li>
          <li><b>Drei Betriebsarten:</b> <i>Eigenverbrauch</i> – der Akku lädt mit Überschuss und deckt den Verbrauch. <i>Akku halten</i> – er wird nicht entladen, Energie wird für teurere Stunden aufgehoben (Überschuss lädt weiter). <i>Aus dem Netz laden</i> – günstiger Netzstrom wird für später gespeichert.</li>
          <li><b>Verluste:</b> Laden und Entladen zusammen ${nf(b.efficiency * 100, 0)} % Wirkungsgrad – gespeicherte Energie muss später teurer ersetzt werden, als sie gekostet hat, sonst lohnt es nicht.</li>
          <li><b>Grenzen:</b> Reserve ${nf(b.min_soc, 0)} % wird nie unterschritten, aus dem Netz geladen wird höchstens bis ${nf(b.max_soc_grid, 0)} % und mit ${nf(b.max_charge_kw, 1)} kW${b.grid_charge ? '' : ' (Netzladen ist ausgeschaltet)'}.</li>
          <li><b>Vorsicht bei der Sonne:</b> Sicherheitsabschlag ${caution} – bei unsicherer Prognose rechnet der Plan mit weniger PV.</li>
          <li><b>Mindestnutzen:</b> Bringt ein Eingriff im ganzen Zeitraum weniger als ${nf(w.min_savings_ct ?? 1, 0)} ct, bleibt der Akku im Eigenverbrauch.</li>
          <li><b>Ende des Zeitraums:</b> Energie, die dann noch im Akku ist, wird mit einem vorsichtigen Preis bewertet – so leert der Plan den Akku nicht einfach zum Schluss.</li>
        </ul></details>`,
    });
  }

  async function renderPlan(el, token) {
    let first = true;
    const load = async () => {
      const [p, ov] = await Promise.all([api('plan'), api('overview')]);
      if (stale(token)) return;
      draw(p, ov); first = false;
    };
    const draw = (p, ov) => {
      const nc = p.nowcast && p.nowcast.factor && Math.abs(p.nowcast.factor - 1) >= 0.05 ? ` · live korrigiert (${signed((p.nowcast.factor - 1) * 100, 0)} %)` : '';
      // before about 13:00 the prices of tomorrow are not published yet - that is why the plan is shorter then
      const noTomorrow = p.ok && p.horizon_end <= dayTs(shiftDay(localDay(), 1));
      setHeader('Planung', p.ok ? `Plan bis ${fmtWhen(p.horizon_end, true)}${noTomorrow ? ' <span class="faint">(Preise für morgen ab ca. 13 Uhr)</span>' : ''} · PV: ${esc(p.pv_source || 'Open-Meteo Auto')}${nc} · Verbrauch: ${esc(p.load_source)}` : '', refreshBtn());
      bindRefresh(load);
      if (!p.ok && !p.runtime) {
        el.innerHTML = `<div class="card"><div class="card-body">${empty('battery', 'Noch kein Plan', esc(p.reason || ''), `<a class="btn primary" href="#/settings?tab=sensors">${ic('gear')}Sensoren einstellen</a> <a class="btn" href="#/settings?tab=battery">Batterie einstellen</a>`)}</div></div>`;
        return;
      }
      const rt = p.runtime || {};
      const lv = (ov.live && ov.live.values) || {};
      const house = lv.house && lv.house.value;
      const m = p.ok ? MODE[p.decision] : null;
      const loadSum = (from, to) => (p.energy || []).filter((e) => e.ts >= from && e.ts < to).reduce((a, e) => a + e.load, 0);
      const tomorrowTs = dayTs(shiftDay(localDay(), 1)); const afterTs = dayTs(shiftDay(localDay(), 2));
      const kpi = (icon, cls, label, value, foot) => `<div class="card kpi"><div class="kpi-label"><span class="kpi-icon ${cls}">${ic(icon)}</span>${label}</div><div class="kpi-value">${value}</div><div class="kpi-foot">${foot}</div></div>`;
      el.innerHTML = `${p.ok ? `<div class="card decision ${m[2]}"><div class="card-body row" style="gap:16px;align-items:flex-start">
          <div class="avatar ${m[2]}" style="width:48px;height:48px">${ic(m[1])}</div>
          <div class="grow"><div class="faint" style="font-size:12.5px;font-weight:600;text-transform:uppercase;letter-spacing:.05em">Empfehlung jetzt</div>
            <div style="font-size:20px;font-weight:700;margin:2px 0 4px">${esc(p.label)}</div>
            <div class="muted">${esc(p.text)}</div></div>
          <div class="col" style="gap:8px;align-items:flex-end;align-self:center"><span class="badge ${p.buy_now ? 'accent' : ''}">${p.buy_now ? 'Strom kaufen: ja' : 'Strom kaufen: nein'}</span><button class="btn sm" id="whyBtn">${ic('info')}Warum dieser Plan?</button></div></div></div>`
        : `<div class="notice">${ic('alert')}<div>${esc(p.reason)}</div></div>`}
        <div class="grid kpis">
          ${kpi('battery', 'ok', 'Akku jetzt', `${cnt('psoc', nf(p.soc, 0))}<small>%</small>`, `${nf(rt.usable_kwh, 1)} kWh nutzbar bis zur Reserve von ${nf(p.battery.min_soc, 0)} %`)}
          ${rt.state === 'charging' ? kpi('clock', 'ok', 'Akku lädt', `<span class="kpi-text">mit ${esc(fmtW(rt.battery_w))}</span>`, rt.full_at ? `voll voraussichtlich ${fmtWhen(rt.full_at)}` : 'Reichweite wird angezeigt, sobald er entlädt')
            : rt.state === 'idle' ? kpi('clock', '', p.soc >= 99 ? 'Akku voll' : 'Akku ruht', '<span class="kpi-text">entlädt nicht</span>', coverText(lv))
              : kpi('clock', 'warn', 'Reichweite', rt.now_hours != null ? esc(fmtDur(rt.now_hours)) : '–', rt.state === 'discharging' ? `bei der aktuellen Entladeleistung von ${fmtW(-rt.battery_w)}` : house ? `beim aktuellen Verbrauch von ${fmtW(house)}` : 'Hausverbrauch-Sensor fehlt')}
          ${kpi('sun', 'up', 'Akku leer (Prognose)', `<span class="kpi-text">${rt.empty_at ? esc(fmtWhen(rt.empty_at)) : `nicht vor ${esc(fmtWhen(rt.until, true))}`}</span>`, rt.empty_at ? (rt.full_at && rt.full_at > rt.empty_at ? `wieder voll ${fmtWhen(rt.full_at)}` : 'mit PV-Erzeugung und Verbrauchsprognose') : rt.full_at ? `voll ${fmtWhen(rt.full_at)} · reicht bis ${fmtWhen(rt.until, true)}` : `bis ${fmtWhen(rt.until, true)}`)}
          ${kpi('home', '', 'Verbrauch (Prognose)', `${nf(loadSum(0, tomorrowTs), 1)}<small>kWh</small>`, `bis Mitternacht · morgen ${nf(loadSum(tomorrowTs, afterTs), 1)} kWh · ohne E-Auto/Heizstab`)}
          ${p.ok ? kpi('euro', p.savings_eur > 0.005 ? 'ok' : '', 'Ersparnis durch EnergyPilot', `${cnt('sav', nf(Math.max(0, p.savings_eur), 2))}<small>€</small>`, `Stromkosten ${nf(p.cost_eur, 2)} € statt ${nf(p.baseline_eur, 2)} € ohne EnergyPilot bis ${fmtWhen(p.horizon_end, true)}`) : ''}
        </div>
        <div class="grid cols-2">
          <div class="card"><div class="card-head"><h2>Akku-Ladezustand <span class="sub">geplant</span></h2></div><div class="card-body"><div class="chart" id="socChart"></div></div></div>
          <div class="card"><div class="card-head"><h2>Erzeugung, Verbrauch &amp; Netzbezug <span class="sub">Prognose</span></h2></div><div class="card-body">
            <div class="legend"><span class="static"><i style="background:var(--pv)"></i>PV-Erzeugung</span><span class="static"><i style="background:var(--s7)"></i>Verbrauch</span>${p.ok ? '<span class="static"><i class="box" style="background:var(--measured)"></i>Netzbezug (geplant)</span>' : ''}</div>
            <div class="chart" id="flowChart"></div></div></div>
        </div>
        ${p.ok ? `<div class="card"><div class="card-head"><h2>Strompreis &amp; Fahrplan</h2></div><div class="card-body">
          <div class="legend">${Object.entries(MODE).map(([k, [l]]) => `<span class="static"><i class="box m-${k}"></i>${l}</span>`).join('')}</div>
          <div class="chart" id="modeChart"></div></div></div>
        <div class="card"><div class="card-head"><h2>Stundenplan</h2></div><div class="card-body flush"><div class="table-wrap"><table class="table compact">
          <thead><tr><th>Zeit</th><th>Modus</th><th class="num">ct/kWh</th><th class="num">PV kWh</th><th class="num">Verbr. kWh</th><th class="num">Netz kWh</th><th class="num">Akku %</th></tr></thead><tbody>
          ${p.steps.map((st) => `<tr><td class="nowrap">${fmtWhen(st.ts)}</td><td><span class="badge ${MODE[st.mode][2]}" title="${esc(whyShort(p, st))}">${ic(MODE[st.mode][1])}${esc(st.label)}</span></td><td class="num">${nf(st.price, 1)}</td><td class="num">${nf(st.pv, 2)}</td><td class="num">${nf(st.load, 2)}</td><td class="num" title="↓ Bezug, ↑ Einspeisung">${st.import > 0.005 ? `↓ ${nf(st.import, 2)}` : st.export > 0.005 ? `↑ ${nf(st.export, 2)}` : '–'}</td><td class="num">${nf(st.soc_start, 0)} → ${nf(st.soc_end, 0)}</td></tr>`).join('')}
          </tbody></table></div>
          <div class="muted" style="padding:10px 18px 12px;font-size:12.5px;border-top:1px solid var(--border)">Der Plan ist eine <b>Empfehlung</b> – EnergyPilot steuert noch nichts. Für Automationen gibt es <code>sensor.energypilot_empfehlung</code>, <code>binary_sensor.energypilot_netzladen</code> und <code>binary_sensor.energypilot_entladesperre</code>. Neu berechnet wird alle 5 Minuten.</div></div></div>` : ''}`;
      const opts = { noAnim: !first };
      const hourHead = (ts) => `${fmtDay(ts)} ${fmtHour(ts)}–${fmtHour(ts + 3600)}`;
      const tick = (ts) => (new Date(ts * 1000).getHours() === 0 ? fmtDay(ts) : fmtHour(ts));
      const tickAt = (ts) => new Date(ts * 1000).getHours() % 6 === 0;
      if ($('#whyBtn')) $('#whyBtn').addEventListener('click', () => planWhy(p));
      if (p.ok && first && query().get('why') === '1') { history.replaceState(null, '', '#/plan'); planWhy(p); }
      if (p.ok) {
        chart($('#socChart'), { ...opts, xs: p.steps.map((st) => st.ts), step: 3600, height: 220, maxY: 100, lines: [{ key: 'soc', label: 'Ladezustand', color: 'var(--ok)', values: p.steps.map((st) => st.soc_end) }], fmt: (v) => `${nf(v, 0)} %`, head: hourHead, tick, tickAt });
      } else $('#socChart').innerHTML = `<div class="empty" style="padding:60px 0">${esc(p.reason)}</div>`;
      const en = p.energy || [];
      const imp = new Map((p.steps || []).map((st) => [st.ts, st.import]));
      chart($('#flowChart'), { ...opts, xs: en.map((e) => e.ts), step: 3600, height: 220,
        bar: p.ok ? { label: 'Netzbezug (geplant)', color: 'var(--measured)', cls: 'bar-m', values: en.map((e) => (imp.has(e.ts) ? imp.get(e.ts) * 1000 : null)) } : null,
        lines: [{ key: 'pv', label: 'PV-Erzeugung', color: 'var(--pv)', values: en.map((e) => e.pv * 1000) }, { key: 'load', label: 'Verbrauch', color: 'var(--s7)', values: en.map((e) => e.load * 1000) }],
        fmt: (v) => `${nf(v)} Wh`, axisFmt: (v) => (v >= 1000 ? `${nf(v / 1000, 1)} kWh` : `${nf(v)} Wh`), head: hourHead, tick, tickAt });
      if (p.ok) {
        chart($('#modeChart'), { ...opts, xs: p.steps.map((st) => st.ts), step: 3600, height: 200, lines: [],
          bar: { label: 'Strompreis', color: 'var(--price)', cls: 'bar-p', values: p.steps.map((st) => st.price), clsFor: (i) => `m-${p.steps[i].mode}` },
          fmt: (v) => ctkwh(v, 1), axisFmt: (v) => `${nf(v)} ct`, head: (ts) => { const st = p.steps.find((x) => x.ts === ts); return `${hourHead(ts)} · ${st ? esc(st.label) : ''}`; }, tick, tickAt });
      }
    };
    await load();
    const timer = setInterval(() => { if (!document.hidden) load().catch(() => {}); }, 60000);
    S.cleanup.push(() => clearInterval(timer));
  }

  // ---------------------------------------------------------------- journal
  const eur = (v) => (v == null ? '–' : `${Math.round(v * 100) < 0 ? '−' : ''}${nf(Math.abs(v), 2)} €`);
  async function renderJournal(el, token) {
    const days = store.get('journalDays', 14);
    const d = await api(`journal?days=${days}`);
    if (stale(token)) return;
    const t = d.totals;
    setHeader('Protokoll', d.since ? `Empfehlungen seit ${new Date(d.since * 1000).toLocaleDateString('de-DE')} · ${t.hours} ${t.hours === 1 ? 'Stunde' : 'Stunden'} mit vollständigen Messwerten ausgewertet` : '');
    if (!d.days.length) {
      el.innerHTML = `<div class="card"><div class="card-body">${empty('journal', 'Das Protokoll füllt sich ab jetzt', 'Jede Stunde wird festgehalten, was EnergyPilot empfohlen hat – mit Preis, Prognosen und geplantem Ladezustand. Sobald die Messwerte der Stunde da sind, rechnet EnergyPilot nach, was das Befolgen der Empfehlungen wirklich gebracht hätte. Voraussetzung ist ein Plan (Sensor für den Batterie-Ladezustand).')}</div></div>`;
      return;
    }
    const share = t.possible > 0.005 ? Math.max(0, Math.min(100, (t.saved / t.possible) * 100)) : null;
    const kpi = (icon, cls, label, value, foot) => `<div class="card kpi"><div class="kpi-label"><span class="kpi-icon ${cls}">${ic(icon)}</span>${label}</div><div class="kpi-value">${value}</div><div class="kpi-foot">${foot}</div></div>`;
    const withCost = d.days.filter((x) => x.cost_base != null).slice().reverse();
    el.innerHTML = `<div class="toolbar"><div class="seg" id="jDays">${[[7, '7 Tage'], [14, '14 Tage'], [30, '30 Tage'], [90, '90 Tage']].map(([v, l]) => `<button data-v="${v}" class="${days === v ? 'active' : ''}">${l}</button>`).join('')}</div></div>
      <div class="grid kpis">
        ${kpi('euro', t.saved >= 0 ? 'ok' : 'err', 'Mit EnergyPilot gespart', `${cnt('js', nf(t.saved, 2))}<small>€</small>`, 'wenn der Akku allen Empfehlungen gefolgt wäre')}
        ${kpi('trophy', 'up', 'Im Nachhinein möglich', `${cnt('jp', nf(t.possible, 2))}<small>€</small>`, 'mit perfektem Wissen über Sonne und Verbrauch')}
        ${kpi('target', share != null && share >= 60 ? 'ok' : 'warn', 'Davon erreicht', share == null ? '–' : `${cnt('jq', nf(share, 0))}<small>%</small>`, share == null ? 'bisher keine Ersparnis möglich' : 'Anteil der möglichen Ersparnis')}
        ${t.cost_real != null
          ? kpi('home', '', 'Stromkosten gemessen', `${cnt('jc', nf(t.cost_real, 2))}<small>€</small>`, `aus Netzbezug und Einspeisung der ausgewerteten Stunden · nachgerechnet ohne EnergyPilot ${eur(t.cost_base)}`)
          : kpi('home', '', 'Stromkosten ohne EnergyPilot', `${cnt('jc', nf(t.cost_base, 2))}<small>€</small>`, 'nachgerechnet; negativ = Einspeisung bringt mehr, als der Bezug kostet')}
      </div>
      <div class="notice info" style="margin-top:16px">${ic('info')}<div>Für jeden Tag rechnet EnergyPilot drei Stromrechnungen aus den <b>echten</b> Messwerten und Preisen: <b>ohne EnergyPilot</b> (Akku im Eigenverbrauch, wie er tatsächlich lief), <b>mit EnergyPilot</b> (die Empfehlungen, die zur jeweiligen Stunde aus den Prognosen entstanden, wären befolgt worden) und <b>optimal</b> (im Nachhinein bestmöglich). Liegt „mit EnergyPilot“ dauerhaft nahe an „optimal“, sind Prognosen und Planung verlässlich genug für die Steuerung. Die Ersparnis berücksichtigt auch, wie viel Energie am Ende noch im Akku steckt. ${d.load_kind === 'house' ? `Gerechnet wird mit dem gesamten gemessenen Hausverbrauch – inklusive E-Auto, das auch aus dem Akku geladen wird${d.heater_surplus ? '. Der Heizstab läuft nur mit PV-Überschuss: Er nimmt in der Nachrechnung nur auf, was sonst eingespeist würde' : ' und Heizstab'}. Zur Kontrolle steht daneben die <b>gemessene</b> Rechnung aus Netzbezug und Einspeisung.` : 'Grundlage ist der Grundverbrauch – für E-Auto und Heizstab fehlt der Hausverbrauch-Sensor.'} Ein Klick auf einen Tag zeigt die Aufteilung.</div></div>
      <div class="card" style="margin-top:16px"><div class="card-head"><h2>Ersparnis pro Tag</h2></div><div class="card-body">
        <div class="legend"><span class="static"><i class="box" style="background:var(--ok)"></i>Mit EnergyPilot gespart</span><span class="static"><i style="background:var(--text-2)"></i>Im Nachhinein möglich</span></div>
        <div class="chart" id="jChart"></div></div></div>
      <div class="card"><div class="card-head"><h2>Tage <span class="sub">Klick zeigt die einzelnen Stunden</span></h2></div><div class="card-body flush"><div class="table-wrap"><table class="table compact">
        <thead><tr><th>Tag</th><th>Empfehlungen</th><th class="num">PV kWh<br><span class="faint">Prognose → Ist</span></th><th class="num">Verbrauch kWh<br><span class="faint">Prognose → Ist</span></th><th class="num">gemessen</th><th class="num">ohne EnergyPilot</th><th class="num">mit EnergyPilot</th><th class="num">optimal</th><th class="num">gespart</th></tr></thead><tbody>
        ${d.days.map((x, i) => `<tr class="click" data-i="${i}"><td class="nowrap">${fmtDay(dayTs(x.day))}${x.complete_hours < x.hours ? ` <span class="faint" title="Stunden mit vollständigen Messwerten">(${x.complete_hours}/${x.hours} h)</span>` : ''}</td>
          <td>${x.charge_hours ? `<span class="badge accent">${ic('plug')}${x.charge_hours} h laden</span> ` : ''}${x.hold_hours ? `<span class="badge warn">${ic('battery')}${x.hold_hours} h halten</span>` : ''}${!x.charge_hours && !x.hold_hours ? '<span class="faint nowrap">nur Eigenverbrauch</span>' : ''}</td>
          <td class="num">${nf(x.pv_fc, 1)} → ${x.pv == null ? '–' : nf(x.pv, 1)}</td><td class="num">${nf(x.load_fc, 1)} → ${x.load == null ? '–' : nf(x.load, 1)}</td>
          <td class="num">${eur(x.cost_real)}</td><td class="num">${eur(x.cost_base)}</td><td class="num">${eur(x.cost_plan)}</td><td class="num">${eur(x.cost_best)}</td>
          <td class="num ${x.saved > 0.005 ? 'best' : x.saved < -0.005 ? 'pos' : ''}">${x.saved == null ? '–' : eur(x.saved)}</td></tr>`).join('')}
        </tbody></table></div></div></div>`;
    chart($('#jChart'), {
      xs: withCost.map((x) => dayTs(x.day)), step: 86400, height: 200, tickCenter: true,
      bar: { label: 'Mit EnergyPilot gespart', color: 'var(--ok)', cls: 'bar-save', values: withCost.map((x) => x.saved), clsFor: (i, v) => (v < 0 ? 'neg' : '') },
      lines: [{ key: 'possible', label: 'Im Nachhinein möglich', color: 'var(--text-2)', dash: true, values: withCost.map((x) => x.possible) }],
      fmt: (v) => eur(v), axisFmt: (v) => `${nf(v, 2)} €`, head: (ts) => fmtDay(ts), tick: (ts) => new Date(ts * 1000).toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' }),
      emptyText: 'Noch keine vollständig ausgewerteten Tage.',
    });
    $$('#jDays button').forEach((b) => b.addEventListener('click', () => { store.set('journalDays', Number(b.dataset.v)); navigate(); }));
    $$('tr.click[data-i]').forEach((tr) => tr.addEventListener('click', () => journalDay(d.days[Number(tr.dataset.i)], d)));
  }
  function journalDay(x, d) {
    const diff = (fc, act) => (act == null ? '' : ` <span class="faint">(${signed((fc - act), 2)})</span>`);
    const bl = x.bills || {};
    const billRow = (key, label, note) => {
      const v = bl[key];
      return v ? `<tr${key === 'real' ? ' class="strong"' : ''}><td>${label}${note ? `<div class="faint" style="font-size:12px">${note}</div>` : ''}</td><td class="num">${nf(v.import_kwh, 2)}</td><td class="num">${eur(v.import_eur)}</td><td class="num">${nf(v.export_kwh, 2)}</td><td class="num">${eur(-v.export_eur)}</td><td class="num"><b>${eur(v.total_eur)}</b></td></tr>` : '';
    };
    const other = x.house != null ? Math.max(0, x.house - (x.heater || 0) - (x.ev || 0)) : null;
    const grid = (h) => (h.grid_import == null ? '–' : h.grid_import > 0.005 ? `↓ ${nf(h.grid_import, 2)}` : h.grid_export > 0.005 ? `↑ ${nf(h.grid_export, 2)}` : '0');
    modal({
      title: `Protokoll – ${fmtDate(dayTs(x.day))}`, wide: true,
      body: `${x.bills ? `<p class="explain">${x.complete_hours} ausgewertete Stunden · PV ${kwh(x.pv, 1)} · Verbrauch ${kwh(x.house, 1)}${x.house != null && (x.heater != null || x.ev != null) ? ` <span class="faint">(davon ${[x.heater != null ? `Heizstab ${kwh(x.heater, 1)}` : '', x.ev != null ? `E-Auto ${kwh(x.ev, 1)}` : '', `übrige ${kwh(other, 1)}`].filter(Boolean).join(', ')})</span>` : ''}</p>
        <div class="table-wrap" style="margin-bottom:16px"><table class="table compact"><thead><tr><th>Stromrechnung</th><th class="num">Bezug kWh</th><th class="num">Bezug €</th><th class="num">Einspeisung kWh</th><th class="num">Vergütung €</th><th class="num">Summe</th></tr></thead><tbody>
          ${billRow('real', 'Gemessen', 'Netzbezug und Einspeisung laut Sensor')}
          ${billRow('base', 'Ohne EnergyPilot', 'nachgerechnet: Akku im Eigenverbrauch')}
          ${billRow('plan', 'Mit EnergyPilot', 'nachgerechnet: Empfehlungen befolgt')}
          ${billRow('best', 'Optimal', 'im Nachhinein bestmöglich')}
        </tbody></table></div>
        ${x.segments > 1 ? `<div class="notice info" style="margin:-6px 0 12px">${ic('info')}<div>Die ausgewerteten Stunden bestehen aus ${x.segments} Abschnitten – dazwischen fehlen Empfehlungen, z. B. weil das Add-on neu gestartet wurde. Jeder Abschnitt beginnt mit dem gemessenen Ladezustand des Akkus.</div></div>` : ''}
        <p class="faint" style="font-size:12.5px;margin:-6px 0 16px">Summe = Bezug − Vergütung (Einspeisevergütung ${ctkwh(d.feed_in_ct, 2)}); negativ = die Einspeisung bringt mehr, als der Bezug kostet.${d.heater_surplus && x.heater ? ` Der Heizstab läuft nur mit Überschuss und nimmt in der Nachrechnung auf, was sonst eingespeist würde (ohne EnergyPilot ${kwh(bl.base && bl.base.heater_kwh, 1)}, gemessen ${kwh(x.heater, 1)}).` : ''} ${d.grid_floor_wh >= 5 ? `Dein Speicher bezieht auch bei geladenem Akku im Mittel etwa ${nf(d.grid_floor_wh, 0)} Wh pro Stunde aus dem Netz (Regelung, Eigenverbrauch) – das ist in der Nachrechnung berücksichtigt. ` : ''}Weicht „ohne EnergyPilot“ stark von „gemessen“ ab, rechnet die Simulation den Akku anders, als er sich tatsächlich verhält. „Gespart“ und „möglich“ rechnen zusätzlich die Energie, die am Ende noch im Akku steckt.</p>` : ''}
        <div class="table-wrap"><table class="table compact"><thead><tr><th>Stunde</th><th>Empfehlung</th><th class="num">ct/kWh</th><th class="num">PV kWh<br><span class="faint">Prognose (Abw.)</span></th><th class="num">Grundverbr. kWh<br><span class="faint">Prognose (Abw.)</span></th><th class="num">Verbrauch<br><span class="faint">gesamt kWh</span></th><th class="num">Netz kWh<br><span class="faint">gemessen</span></th><th class="num">Akku % am Stundenende<br><span class="faint">geplant / Ist</span></th></tr></thead><tbody>
        ${x.detail.map((h) => `<tr${h.complete ? '' : ' class="offline"'}><td class="nowrap">${fmtHour(h.ts)}–${fmtHour(h.ts + 3600)}</td><td><span class="badge ${MODE[h.mode][2]}">${ic(MODE[h.mode][1])}${MODE[h.mode][0]}</span></td>
          <td class="num">${nf(h.price, 1)}</td><td class="num">${nf(h.pv_fc, 2)}${diff(h.pv_fc, h.pv)}</td><td class="num">${nf(h.load_fc, 2)}${diff(h.load_fc, h.load)}</td>
          <td class="num">${h.house == null ? '–' : nf(h.house, 2)}</td><td class="num" title="↓ Bezug, ↑ Einspeisung">${grid(h)}</td>
          <td class="num">${nf(h.soc_plan, 0)} / ${h.soc_actual == null ? '–' : nf(h.soc_actual, 0)}</td></tr>`).join('')}
        </tbody></table></div>
        <p class="faint" style="font-size:12.5px;margin:10px 0 0">Abw. = Prognose minus Messwert (+ = zu hoch vorhergesagt). Die Verbrauchsprognose gilt für den Grundverbrauch ohne E-Auto und Heizstab. Netz: ↓ Bezug, ↑ Einspeisung. Akku: geplanter und gemessener Ladezustand am Ende der Stunde. Solange EnergyPilot nicht steuert, läuft der Akku im Eigenverbrauch – bei „laden“ und „halten“ zeigt der geplante Wert, wohin der Plan ihn gebracht hätte.</p>`,
    });
  }

  // How the own forecast currently combines the sources (per array)
  function modelCard(model) {
    const arrays = (S.settings ? S.settings.arrays : []).filter((a) => model && model[a.id]);
    if (!arrays.length) return '';
    const hourChips = (f) => {
      const notable = Object.entries(f || {}).filter(([, v]) => Math.abs(v - 1) >= 0.05);
      if (!notable.length) return '<span class="faint">keine nennenswerte Korrektur</span>';
      return notable.map(([h, v]) => `<span class="badge ${v < 1 ? 'warn' : 'accent'}" title="${h}:00–${Number(h) + 1}:00 Uhr">${h} Uhr ${signed((v - 1) * 100, 0)} %</span>`).join(' ');
    };
    return `<div class="card"><div class="card-head"><h2>So rechnet die eigene Prognose <span class="sub">gelernt aus den letzten ${model[arrays[0].id].days} Tagen</span></h2></div>
      <div class="card-body"><p class="explain">EnergyPilot gewichtet jede Quelle danach, wie gut sie bei dieser Anlage zuletzt lag (je nach erwarteter Wetterlage), und korrigiert das Ergebnis je Uhrzeit – <b>getrennt für Sonne und Wolken</b>: Schatten von Bäumen oder Nachbarhäusern wirkt nur bei direkter Sonne, systematische Fehler der Wettermodelle zeigen sich auch bei Bewölkung. Neu gelernt wird jede Stunde.</p>
      <div class="grid cols-2">${arrays.map((a) => {
        const m = model[a.id];
        const w = Object.entries(m.weights).sort((x, y) => y[1] - x[1]);
        const f = m.factors || {};
        return `<div><div style="font-weight:650;margin-bottom:8px">${esc(a.name)}</div>
          ${w.map(([src, share]) => `<div class="row" style="gap:10px;margin-bottom:6px;font-size:13px"><span class="swatch-dot" style="background:${srcColor(src)}"></span><span style="width:130px" class="nowrap">${esc(sourceName(src))}</span><div class="bar" style="flex:1"><i style="width:${Math.round(share * 100)}%;background:${srcColor(src)}"></i></div><b class="num" style="width:44px;text-align:right">${pct(share * 100, 0)}</b></div>`).join('')}
          <div style="font-size:12.5px;margin-top:10px;line-height:2"><span class="muted">${ic('sun')} Bei Sonne:</span> ${hourChips(f.sunny)}</div>
          <div style="font-size:12.5px;line-height:2"><span class="muted">${ic('cloud')} Bei Wolken:</span> ${hourChips(f.cloudy)}</div></div>`;
      }).join('')}</div></div></div>`;
  }
  const SOURCE_NAMES = { 'om:best_match': 'Open-Meteo Auto', 'om:icon_d2': 'DWD ICON-D2', 'om:icon_eu': 'DWD ICON-EU', 'om:ecmwf_ifs025': 'ECMWF IFS', 'om:gfs_seamless': 'NOAA GFS', 'om:meteofrance_seamless': 'Météo-France', 'om:knmi_seamless': 'KNMI Harmonie', 'om:dmi_seamless': 'DMI Harmonie', 'om:ukmo_seamless': 'UK Met Office', fs: 'Forecast.Solar', sc: 'Solcast', ep: 'EnergyPilot (lernend)', nc: 'EnergyPilot (live korrigiert)', lw: 'Wie vor einer Woche' };
  const sourceName = (src) => SOURCE_NAMES[src] || src;

  // --------------------------------------------------------------- accuracy
  async function renderAccuracy(el, token) {
    const cfg = { days: 30, horizon: 'd1', series: '_total', common: false, ...store.get('acc', {}) };
    if (!S.settings) await loadSettings();
    const arrays = S.settings.arrays.filter((a) => a.kwp > 0);
    if (!arrays.length) { welcome(el); return; }
    const load = async () => {
      store.set('acc', cfg);
      const [data, tr] = await Promise.all([
        api(`accuracy?days=${cfg.days}&horizon=${cfg.horizon}&series=${encodeURIComponent(cfg.series)}&common=${cfg.common ? 1 : 0}`),
        api(`trend?horizon=${cfg.horizon}&series=${encodeURIComponent(cfg.series)}`).catch(() => null),
      ]);
      if (stale(token)) return;
      trendData = tr;
      draw(data);
    };
    let trendData = null;
    // how the own forecast develops week by week - its lead over the benchmark is what counts
    const trendCard = (isLoad) => {
      const tr = trendData;
      if (!tr || !tr.weeks.length || !tr.sources.includes('ep')) return '';
      const bench = tr.sources.find((s) => s !== 'ep');
      const lead = tr.weeks.map((w) => (bench && w.values.ep.score != null && w.values[bench].score != null ? w.values.ep.score - w.values[bench].score : null));
      const avg = (arr) => { const v = arr.filter((x) => x != null); return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null; };
      const n = Math.min(4, Math.floor(tr.weeks.length / 2));
      const early = n ? avg(lead.slice(0, n)) : null; const late = n ? avg(lead.slice(-n)) : null;
      const epEarly = n ? avg(tr.weeks.slice(0, n).map((w) => w.values.ep.score)) : null; const epLate = n ? avg(tr.weeks.slice(-n).map((w) => w.values.ep.score)) : null;
      const change = early != null && late != null ? late - early : null;
      // a verdict only when the change is clearly larger than the week-to-week noise of the lead
      const vr = (arr) => { const v = arr.filter((x) => x != null); const m = avg(v); return v.length > 1 ? v.reduce((a, x) => a + (x - m) ** 2, 0) / (v.length - 1) : 0; };
      const se = n ? Math.sqrt(vr(lead.slice(0, n)) / n + vr(lead.slice(-n)) / n) : 0;
      const clear = change != null && Math.abs(change) > Math.max(1, 2 * se);
      const verdict = change == null ? '' : !clear ? '<span class="badge" title="Die Veränderung ist kleiner als die Schwankung von Woche zu Woche">keine klare Veränderung</span>'
        : change > 0 ? `<span class="badge ok">${ic('checkCircle')}lernt dazu</span>` : `<span class="badge err">${ic('alert')}wird schlechter</span>`;
      return `<div class="card"><div class="card-head"><h2>Entwicklung über die Zeit <span class="sub">Genauigkeit je Woche · ${cfg.horizon === 'd1' ? 'Prognose vom Vortag' : 'kurzfristig'}</span></h2>${verdict}</div>
        <div class="card-body">${bench ? `<p class="explain">Vorsprung der eigenen Prognose vor ${esc(tr.labels[bench])}: ${early == null ? '–' : `<b>${signed(early, 1)} Prozentpunkte</b> in den ersten ${n} Wochen`} → ${late == null ? '–' : `<b>${signed(late, 1)} Prozentpunkte</b> in den letzten ${n} Wochen`}. EnergyPilot selbst: ${pct(epEarly, 0)} → ${pct(epLate, 0)}.</p>` : ''}
          <div class="legend">${tr.sources.map((s) => `<span class="static"><i style="background:${srcColor(s)}"></i>${esc(tr.labels[s])}</span>`).join('')}</div>
          <div class="chart" id="trendChart"></div>
          <p class="faint" style="font-size:12.5px;margin:10px 0 0">Wie gut eine Woche vorhergesagt werden kann, hängt stark vom Wetter${isLoad ? ' und vom Alltag' : ''} ab – deshalb der Vergleich auf denselben Stunden mit ${bench ? esc(tr.labels[bench]) : 'einem Maßstab'}. Wächst der Vorsprung, lernt EnergyPilot dazu; schrumpft er, wird die eigene Prognose schlechter. Vergangene Wochen sind mit dem heutigen Verfahren nachgerechnet – jeweils nur mit den Daten, die damals schon vorlagen.</p></div></div>`;
    };
    const toolbar = () => `${seriesSelect('accSeries', cfg.series, arrays)}<div class="toolbar">
        <span class="tb-label">Zeitraum</span><div class="seg" id="accDays">${[[7, '7 Tage'], [14, '14 Tage'], [30, '30 Tage'], [90, '90 Tage'], [365, '1 Jahr']].map(([d, l]) => `<button data-v="${d}" class="${cfg.days === d ? 'active' : ''}">${l}</button>`).join('')}</div>
        <span class="tb-label">Prognose</span><div class="seg" id="accHz">${HORIZONS.map(([k, l, t]) => `<button data-v="${k}" title="${esc(t)}" class="${cfg.horizon === k ? 'active' : ''}">${l}</button>`).join('')}</div>
        <label class="check" title="Nur Stunden vergleichen, für die alle Quellen einen Wert haben – fairer, wenn Quellen unterschiedlich lange gesammelt wurden"><input type="checkbox" id="accCommon" ${cfg.common ? 'checked' : ''}>Nur gemeinsame Stunden</label>
      </div>`;
    const draw = (d) => {
      setHeader('Prognose-Check', `${new Date(d.start * 1000).toLocaleDateString('de-DE')} – ${new Date((d.end - 1) * 1000).toLocaleDateString('de-DE')} · ${HORIZONS.find((h) => h[0] === cfg.horizon)[2]}`);
      const res = d.results;
      const isLoad = cfg.series === BASE;
      const what = isLoad ? 'Tagesverbrauch' : 'Tagesertrag';
      if (!res.length) {
        el.innerHTML = `${toolbar()}<div class="card"><div class="card-body">${empty('target', 'Noch nichts zu vergleichen', 'Für den Vergleich braucht es Messwerte der PV-Anlagen (Sensor mit Langzeitstatistik, siehe Einstellungen) und Prognosen für denselben Zeitraum. Das Archiv der Wettermodelle wird beim ersten Start automatisch nachgeladen – das dauert ein paar Minuten.')}</div></div>`;
        bind(); return;
      }
      const bestDay = Math.min(...res.filter((r) => r.day_nmae_pct != null).map((r) => r.day_nmae_pct));
      const rows = res.map((r, i) => `<tr>
          <td><span class="rank ${i === 0 ? 'r1' : ''}">${i + 1}</span></td>
          <td><div class="cell-main" style="min-width:160px"><span class="swatch-dot" style="background:${srcColor(r.source)}"></span><span class="t">${esc(r.label)}</span></div></td>
          <td><div class="score"><div class="bar"><i style="width:${r.score || 0}%"></i></div><b>${pct(r.score, 1)}</b></div></td>
          <td class="num ${r.day_nmae_pct === bestDay ? 'best' : ''}">${pct(r.day_nmae_pct)}</td>
          <td class="num"><span class="${r.bias_pct > 0 ? 'pos' : 'neg'}">${signed(r.bias_pct)} %</span></td>
          <td class="num">${kwh(r.day_max_err_kwh)}</td>
          <td class="num hide-md">${nf(r.mae_wh)} Wh</td>
          <td class="num hide-md">${nf(r.rmse_wh)} Wh</td>
          <td class="num">${r.days}</td></tr>`).join('');
      const counts2 = { sunny: 0, mixed: 0, cloudy: 0 };
      Object.values(d.classes || {}).forEach((c) => { counts2[c] += 1; });
      const hasClasses = Object.values(counts2).some((v) => v);
      const bestIn = {};
      Object.keys(counts2).forEach((c) => {
        const vals = res.map((r) => r.by_class && r.by_class[c] && r.by_class[c].nmae_pct).filter((v) => v != null);
        bestIn[c] = vals.length ? Math.min(...vals) : null;
      });
      const classTable = hasClasses ? `<div class="card"><div class="card-head"><h2>Nach Wetterlage <span class="sub">Stundenfehler relativ zur Erzeugung – kleiner ist besser</span></h2></div>
        <div class="card-body flush"><div class="table-wrap"><table class="table"><thead><tr><th>Quelle</th>${Object.entries(CLASS_LABEL).map(([k, [l, icon]]) => `<th class="num">${ic(icon)} ${l} <span class="faint">(${counts2[k]} T.)</span></th>`).join('')}</tr></thead><tbody>
        ${res.map((r) => `<tr><td><div class="cell-main" style="min-width:160px"><span class="swatch-dot" style="background:${srcColor(r.source)}"></span><span class="t">${esc(r.label)}</span></div></td>${Object.keys(CLASS_LABEL).map((c) => { const v = r.by_class && r.by_class[c]; return `<td class="num ${v && v.nmae_pct === bestIn[c] ? 'best' : ''}">${v ? `${pct(v.nmae_pct, 0)} <span class="faint">(${signed(v.bias_pct, 0)} %)</span>` : '–'}</td>`; }).join('')}</tr>`).join('')}
        </tbody></table></div><div class="muted" style="padding:10px 18px 12px;font-size:12.5px;border-top:1px solid var(--border)">Wetterlage aus der gemessenen Erzeugung im Verhältnis zu einem wolkenlosen Tag: sonnig ≥ 60 %, wechselhaft 30–60 %, trüb &lt; 30 %. In Klammern die systematische Abweichung (+ = Prognose zu hoch).</div></div></div>` : '';
      const ranking = res.map((r) => r.source);
      const all = Object.keys(d.daily.sources);
      const hidden = hiddenSet(ranking, all);
      const lines = all.sort((a, b) => ranking.indexOf(a) - ranking.indexOf(b)).map((s) => ({ key: s, label: d.labels[s], color: srcColor(s) }));
      el.innerHTML = `${toolbar()}
        <div class="card"><div class="card-head"><h2>Rangliste</h2></div>
          <div class="card-body flush"><p class="explain" style="padding:0 18px">${ic('trophy')} Am genauesten: <b>${esc(res[0].label)}</b> – Genauigkeit ${pct(res[0].score, 1)}, beim ${what} im Mittel ${pct(res[0].day_nmae_pct)} daneben.
            <span class="faint">Sortiert nach Genauigkeit = 100 % minus mittlerer Fehler je Stunde relativ zum Messwert – für die Planung zählt jede Stunde. Tagesabweichung = Fehler beim ${what}; dort kann eine andere Quelle vorn liegen, weil sich Fehler über den Tag ausgleichen. Tendenz = systematische Über- (+) oder Unterschätzung.${isLoad ? ' Grundverbrauch = Hausverbrauch ohne E-Auto und Heizstab; „Wie vor einer Woche“ ist der Vergleichsmaßstab.' : ''}</span></p>
          <div class="table-wrap"><table class="table"><thead><tr><th></th><th>Quelle</th><th>Genauigkeit</th><th class="num">Tagesabw. Ø</th><th class="num">Tendenz</th><th class="num">Größter Tagesfehler</th><th class="num hide-md">Stundenfehler Ø</th><th class="num hide-md">RMSE</th><th class="num">Tage</th></tr></thead><tbody>${rows}</tbody></table></div></div></div>
        ${trendCard(isLoad)}
        ${isLoad ? '' : modelCard(d.model)}
        ${classTable}
        <div class="card"><div class="card-head"><h2>${isLoad ? 'Tagesverbrauch' : 'Tageserträge'} <span class="sub">Klick auf einen Tag zeigt den Stundenverlauf</span></h2></div>
          <div class="card-body">${legendHTML(MEASURED, lines, hidden)}<div class="chart tall" id="dailyChart"></div></div></div>`;
      if ($('#trendChart')) {
        const tr = trendData;
        chart($('#trendChart'), {
          xs: tr.weeks.map((w) => w.start), step: 7 * 86400, height: 220, tickCenter: true,
          lines: tr.sources.map((s) => ({ key: s, label: tr.labels[s], color: srcColor(s), values: tr.weeks.map((w) => w.values[s].score) })),
          fmt: (v) => pct(v, 1), axisFmt: (v) => `${nf(v)} %`, maxY: 100,
          head: (ts) => `Woche ab ${fmtDay(ts)}`, tick: (ts) => new Date(ts * 1000).toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' }),
        });
      }
      const days = d.daily.days;
      chart($('#dailyChart'), {
        xs: days.map(dayTs), step: 86400, height: 280,
        bar: { ...MEASURED, cls: 'bar-m', values: days.map((k) => d.daily.actual[k] ?? null) },
        lines: lines.filter((l) => !hidden.has(l.key)).map((l) => ({ ...l, values: days.map((k) => d.daily.sources[l.key][k] ?? null) })),
        fmt: (v) => kwh(v), axisFmt: (v) => `${nf(v)} kWh`, head: (ts) => fmtDay(ts), tick: (ts) => new Date(ts * 1000).toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' }), tickCenter: true,
        onClick: (i) => { location.hash = `#/day?d=${days[i]}`; },
      });
      $$('.legend button[data-series]', el).forEach((b) => b.addEventListener('click', () => { toggleHidden(b.dataset.series); draw(d); }));
      bind();
    };
    const bind = () => {
      $$('#accDays button').forEach((b) => b.addEventListener('click', () => { cfg.days = Number(b.dataset.v); load(); }));
      $$('#accHz button').forEach((b) => b.addEventListener('click', () => { cfg.horizon = b.dataset.v; load(); }));
      $$('#accSeries button').forEach((b) => b.addEventListener('click', () => { cfg.series = b.dataset.v; load(); }));
      $('#accCommon').addEventListener('change', (e) => { cfg.common = e.target.checked; load(); });
    };
    await load();
  }

  // -------------------------------------------------------------------- day
  async function renderDay(el, token) {
    const q = query();
    const day = q.get('d') || localDay();
    const cfg = { horizon: 'd0', series: '_total', ...store.get('dayCfg', {}) };
    if (!S.settings) await loadSettings();
    const arrays = S.settings.arrays.filter((a) => a.kwp > 0);
    if (!arrays.length) { welcome(el); return; }
    const d = await api(`day?day=${day}&series=${encodeURIComponent(cfg.series)}`);
    if (stale(token)) return;
    const draw = () => {
      store.set('dayCfg', cfg);
      setHeader('Tagesverlauf', fmtDate(dayTs(day)));
      const sources = Object.keys(d.forecasts);
      const ranking = (S.overview && S.overview.ranking) || [];
      const hidden = hiddenSet(ranking, sources);
      const lines = sources.sort((a, b) => (ranking.indexOf(a) + 1 || 99) - (ranking.indexOf(b) + 1 || 99)).map((s) => ({ key: s, label: d.labels[s], color: srcColor(s) }));
      // compare only the hours that were measured (today: up to now) - never a whole day against a few hours
      const measured = d.hours.map((_t, i) => i).filter((i) => d.actual[i] != null);
      const actSum = measured.length ? measured.reduce((a, i) => a + d.actual[i], 0) / 1000 : null;
      const partDay = measured.length > 0 && measured.length < d.hours.length;
      // hours that matter: something was produced or forecast (night hours without values are fine)
      const productive = d.hours.map((_t, i) => i).filter((i) => (d.actual[i] || 0) > 10
        || lines.some((l) => (((d.forecasts[l.key] || {})[cfg.horizon] || [])[i] || 0) > 10));
      const coverage = (vals) => productive.filter((i) => vals[i] != null).length;
      const full = productive.length;
      const rows = lines.map((l) => {
        const vals = (d.forecasts[l.key] || {})[cfg.horizon];
        if (!vals) return '';
        const total = vals.reduce((a, v) => a + (v || 0), 0) / 1000;
        const both = measured.filter((i) => vals[i] != null);
        const fc = both.reduce((a, i) => a + vals[i], 0) / 1000;
        const act = both.reduce((a, i) => a + d.actual[i], 0) / 1000;
        // small amounts (early morning) as kWh - percentages of a few hundred Wh say nothing
        const dev = !both.length ? null : act >= 1 ? { v: ((fc - act) / act) * 100, u: '%' } : { v: fc - act, u: 'kWh' };
        const hrs = coverage(vals);
        return { l, total, dev, partial: hrs < full * 0.8, hrs };
      }).filter(Boolean).sort((a, b) => (a.partial - b.partial) || ((a.dev == null ? 1e9 : Math.abs(a.dev.u === '%' ? a.dev.v : a.dev.v * 100)) - (b.dev == null ? 1e9 : Math.abs(b.dev.u === '%' ? b.dev.v : b.dev.v * 100))));
      // ranking: only sources with a comparison over the measured hours
      let rank = 0;
      rows.forEach((r) => { r.rank = r.dev != null && !r.partial ? ++rank : null; });
      const ranked = rank > 0;
      const rankCell = (r) => (ranked ? `<span class="rank ${r && r.rank === 1 ? 'r1' : ''} ${r && r.rank ? '' : 'none'}">${r && r.rank ? r.rank : ''}</span>` : '');
      const lastH = measured.length ? d.hours[measured[measured.length - 1]] + 3600 : null;
      const devTxt = (r) => (r.dev == null ? (r.partial ? `nur ${r.hrs} ${r.hrs === 1 ? 'Stunde' : 'Stunden'} berechnet` : '&nbsp;')
        : `<span class="${r.dev.v > 0 ? 'pos' : 'neg'}">${r.dev.u === '%' ? `${signed(r.dev.v)} %` : `${signed(r.dev.v, 2)} kWh`}</span> zur Messung${r.partial ? ` · nur ${r.hrs} ${r.hrs === 1 ? 'Stunde' : 'Stunden'} berechnet` : ''}`);
      const today = localDay();
      el.innerHTML = `${seriesSelect('dSeries', cfg.series, arrays)}<div class="toolbar">
          <span class="tb-label">Tag</span><div class="day-nav"><button class="icon-btn" id="dPrev" title="Vorheriger Tag">${ic('chevronL')}</button><input class="input" type="date" id="dPick" value="${day}"><button class="icon-btn" id="dNext" title="Nächster Tag">${ic('chevron')}</button>${day !== today ? `<button class="btn sm" id="dToday">Heute</button>` : ''}</div>
          <span class="tb-label">Prognose</span><div class="seg" id="dHz">${HORIZONS.map(([k, l, t]) => `<button data-v="${k}" title="${esc(t)}" class="${cfg.horizon === k ? 'active' : ''}">${l}</button>`).join('')}</div>
        </div>
        <div class="grid dash">
          <div class="card"><div class="card-head"><h2>${cfg.series === BASE ? 'Grundverbrauch <span class="sub">stündlich, ohne E-Auto und Heizstab</span>' : 'PV-Erzeugung <span class="sub">stündlich</span>'}</h2></div>
            <div class="card-body">${legendHTML(MEASURED, lines, hidden)}<div class="chart tall" id="dayChart"></div></div></div>
          <div class="card"><div class="card-head"><h2>${cfg.series === BASE ? 'Tagessumme Verbrauch' : 'Tagessumme Erzeugung'}<div class="faint" style="font-weight:400;font-size:12.5px">${ranked ? `Rangliste – Platz 1 = kleinste Abweichung zur Messung${partDay ? ' (bisher)' : ''}` : 'Prognosen für den ganzen Tag'}</div></h2>${ranked ? '<span class="faint" style="font-size:12px">Tag gesamt</span>' : ''}</div><div class="card-body flush">
            <div class="list"><div class="list-item">${rankCell(null)}<span class="swatch-dot" style="background:var(--measured);opacity:.6"></span><div class="grow"><div class="title">Gemessen</div><div class="meta">${actSum == null ? 'keine Messwerte' : partDay ? `${measured.length} volle Stunden, bis ${fmtHour(lastH)}` : 'ganzer Tag'}</div></div><b class="num">${kwh(actSum)}</b></div>
            ${rows.map((r) => `<div class="list-item ${r.partial ? 'faded' : ''}">${rankCell(r)}<span class="swatch-dot" style="background:${r.l.color}"></span><div class="grow"><div class="title">${esc(r.l.label)}</div><div class="meta">${devTxt(r)}</div></div><b class="num">${kwh(r.total)}</b></div>`).join('')}</div>
            ${partDay || rows.some((r) => r.partial) ? `<div class="muted" style="padding:10px 18px 12px;font-size:12.5px;border-top:1px solid var(--border)">${partDay ? 'Rechts steht die Prognose für den ganzen Tag, die Abweichung vergleicht nur die Stunden, die schon gemessen sind.' : ''}${rows.some((r) => r.partial) ? ' Die live korrigierte Prognose wird immer nur für die nächsten Stunden berechnet – ihre Summe umfasst nur diese Stunden und ist keine Tagesprognose.' : ''}</div>` : ''}</div></div>
        </div>
        <div class="card"><div class="card-head"><h2>Strompreis <span class="sub">inkl. Aufschläge und MwSt</span></h2></div><div class="card-body"><div class="chart" id="dayPrice"></div></div></div>`;
      chart($('#dayChart'), {
        xs: d.hours, step: 3600, height: 300, now: Math.floor(Date.now() / 1000),
        bar: { ...MEASURED, cls: 'bar-m', values: d.actual },
        lines: lines.filter((l) => !hidden.has(l.key)).map((l) => ({ ...l, values: (d.forecasts[l.key] || {})[cfg.horizon] || d.hours.map(() => null) })),
        band: !hidden.has('ep') && d.forecasts.ep && (d.band || {})[cfg.horizon] ? { ...BAND, ...d.band[cfg.horizon] } : null,
        fmt: (v) => `${nf(v)} Wh`, axisFmt: (v) => (v >= 1000 ? `${nf(v / 1000, 1)} kWh` : `${nf(v)} Wh`),
        head: (ts) => `${fmtHour(ts)}–${fmtHour(ts + 3600)}`, tickAt: (ts) => new Date(ts * 1000).getHours() % 3 === 0,
        emptyText: 'Für diesen Tag gibt es keine Daten.',
      });
      priceChart($('#dayPrice'), d.prices, Math.floor(Date.now() / 1000), 180);
      const go = (nd) => { location.hash = `#/day?d=${nd}`; };
      $('#dPrev').addEventListener('click', () => go(shiftDay(day, -1)));
      $('#dNext').addEventListener('click', () => go(shiftDay(day, 1)));
      $('#dPick').addEventListener('change', (e) => { if (e.target.value) go(e.target.value); });
      if ($('#dToday')) $('#dToday').addEventListener('click', () => go(today));
      $$('#dHz button').forEach((b) => b.addEventListener('click', () => { cfg.horizon = b.dataset.v; draw(); }));
      $$('#dSeries button').forEach((b) => b.addEventListener('click', () => { if (b.dataset.v === cfg.series) return; cfg.series = b.dataset.v; store.set('dayCfg', cfg); navigate(); }));
      $$('.legend button[data-series]', el).forEach((b) => b.addEventListener('click', () => { toggleHidden(b.dataset.series); draw(); }));
    };
    draw();
  }

  // ----------------------------------------------------------------- prices
  function cheapestWindow(slots, hours, from) {
    const fut = slots.filter((s) => s.ts + s.dur > from);
    if (!fut.length) return null;
    const step = fut[0].dur; const n = Math.round((hours * 3600) / step);
    if (fut.length < n) return null;
    let best = null;
    for (let i = 0; i + n <= fut.length; i += 1) {
      const avg = fut.slice(i, i + n).reduce((a, s) => a + s.price, 0) / n;
      if (!best || avg < best.avg) best = { avg, start: fut[i].ts, end: fut[i + n - 1].ts + step };
    }
    return best;
  }
  async function renderPrices(el, token) {
    const d = await api(`prices?day=${localDay()}&days=2`);
    if (stale(token)) return;
    const now = d.now; const slots = d.slots; const t = d.tariff;
    const tomorrowTs = dayTs(shiftDay(localDay(), 1));
    const stats = (list) => (list.length ? { avg: list.reduce((a, s) => a + s.price, 0) / list.length, min: Math.min(...list.map((s) => s.price)), max: Math.max(...list.map((s) => s.price)) } : null);
    const today = stats(slots.filter((s) => s.ts < tomorrowTs));
    const tomorrow = stats(slots.filter((s) => s.ts >= tomorrowTs));
    const cur = slots.find((s) => s.ts <= now && now < s.ts + s.dur);
    setHeader('Strompreise', `Börsenpreis ${esc(t.bidding_zone)} (EPEX Day-Ahead) + ${nf(t.markup_ct, 2)} ct Aufschlag netto + ${nf(t.vat, 0)} % MwSt`);
    const kpi = (icon, cls, label, value, foot) => `<div class="card kpi"><div class="kpi-label"><span class="kpi-icon ${cls}">${ic(icon)}</span>${label}</div><div class="kpi-value">${value}</div><div class="kpi-foot">${foot}</div></div>`;
    const windows = [1, 2, 3, 4].map((h) => [h, cheapestWindow(slots, h, now)]);
    el.innerHTML = `<div class="grid kpis">
        ${kpi('euro', '', 'Jetzt', cur ? `${cnt('p', nf(cur.price, 1))}<small>ct/kWh</small>` : '–', cur ? `Börse ${nf(cur.spot, 2)} ct/kWh netto` : 'kein Preis')}
        ${kpi('clock', 'ok', 'Heute', today ? `${nf(today.avg, 1)}<small>ct Ø</small>` : '–', today ? `min ${nf(today.min, 1)} · max ${nf(today.max, 1)} ct` : '')}
        ${kpi('clock', 'up', 'Morgen', tomorrow ? `${nf(tomorrow.avg, 1)}<small>ct Ø</small>` : '–', tomorrow ? `min ${nf(tomorrow.min, 1)} · max ${nf(tomorrow.max, 1)} ct` : 'erscheint gegen 13 Uhr')}
      </div>
      <div class="card"><div class="card-head"><h2>Verlauf <span class="sub">${slots.length > 1 && slots[1].ts - slots[0].ts === 900 ? 'Viertelstunden' : 'Stunden'}</span></h2></div><div class="card-body"><div class="chart tall" id="prChart"></div></div></div>
      <div class="card"><div class="card-head"><h2>Günstigste Zeitfenster <span class="sub">ab jetzt, soweit Preise bekannt sind</span></h2></div><div class="card-body">
        <div class="window-list">${windows.map(([h, w]) => `<div class="window"><div class="l">${h} Stunde${h > 1 ? 'n' : ''} am Stück</div>${w ? `<div class="v">${nf(w.avg, 1)} ct</div><div class="s">${fmtDay(w.start)} ${fmtHour(w.start)}–${fmtHour(w.end)}</div>` : '<div class="v">–</div><div class="s">zu wenig Preise</div>'}</div>`).join('')}</div>
        <p class="faint" style="font-size:12.5px;margin:14px 0 0">Die Aufschläge (Netzentgelt, Umlagen, Stromsteuer, Anbieteraufschlag) und die Einspeisevergütung stellst du unter <a href="#/settings?tab=tariff">Einstellungen › Strompreis</a> ein. Später plant EnergyPilot damit das Laden von Batterie und E-Auto.</p>
      </div></div>`;
    priceChart($('#prChart'), slots, now, 300);
  }

  // ------------------------------------------------------------------ costs
  const MONTHS = ['Januar', 'Februar', 'März', 'April', 'Mai', 'Juni', 'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember'];
  const monthName = (ym) => new Date(`${ym}-15T12:00:00`).toLocaleDateString('de-DE', { month: 'long', year: 'numeric' });
  const shiftMonth = (ym, n) => { const d = new Date(`${ym}-15T12:00:00`); d.setMonth(d.getMonth() + n); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`; };
  async function renderCosts(el, token) {
    const cur = localDay().slice(0, 7);
    const month = query().get('m') || cur;
    const [d, months] = await Promise.all([api(`costs?month=${month}`), api('costs/months')]);
    if (stale(token)) return;
    const t = d.totals; const tf = d.tariff;
    setHeader('Kosten', `${monthName(month)} · Netzbezug zum Preis der jeweiligen Stunde${d.split ? '' : ' (aus der Netzleistung mit Vorzeichen)'}`);
    const nav = `<div class="toolbar"><div class="day-nav"><button class="icon-btn" id="mPrev" title="Vormonat">${ic('chevronL')}</button><b style="min-width:150px;text-align:center">${esc(monthName(month))}</b><button class="icon-btn" id="mNext" title="Nächster Monat" ${month >= cur ? 'disabled' : ''}>${ic('chevron')}</button></div></div>`;
    const bindNav = () => {
      $('#mPrev').addEventListener('click', () => { location.hash = `#/costs?m=${shiftMonth(month, -1)}`; });
      if (month < cur) $('#mNext').addEventListener('click', () => { location.hash = `#/costs?m=${shiftMonth(month, 1)}`; });
    };
    if (!d.has_grid) {
      el.innerHTML = `${nav}<div class="card"><div class="card-body">${empty('wallet', 'Netzleistung fehlt', 'Für die Kostenübersicht braucht EnergyPilot den Netzbezug – entweder die Netzleistung mit Vorzeichen oder (genauer) Netzbezug und Einspeisung als eigene Sensoren.', `<a class="btn primary" href="#/settings?tab=sensors">${ic('gear')}Sensoren einstellen</a>`)}</div></div>`;
      bindNav(); return;
    }
    if (!d.days.length) {
      el.innerHTML = `${nav}<div class="card"><div class="card-body">${empty('wallet', 'Keine Daten für diesen Monat', 'Für diesen Monat liegen keine Messwerte des Netzbezugs vor.')}</div></div>`;
      bindNav(); return;
    }
    const kpi = (icon, cls, label, value, foot) => `<div class="card kpi"><div class="kpi-label"><span class="kpi-icon ${cls}">${ic(icon)}</span>${label}</div><div class="kpi-value">${value}</div><div class="kpi-foot">${foot}</div></div>`;
    const better = t.avg_paid_ct != null && t.avg_market_ct != null ? t.avg_market_ct - t.avg_paid_ct : null;
    const cmpOn = tf.compare_enabled !== false;
    const isFlat = tf.compare_type === 'flat';
    const cmpName = isFlat ? 'Flat' : 'Festpreis';
    const cmpText = isFlat ? `Flat ${nf(tf.flat_fee_eur, 2)} €/Monat mit ${nf(tf.flat_free_kwh, 0)} kWh Freistrom, darüber ${nf(tf.flat_price_ct, 1)} ct/kWh`
      : `Festpreis ${nf(tf.compare_price_ct, 1)} ct/kWh + ${nf(tf.compare_base_fee_eur, 2)} €/Monat`;
    const fl = d.flat;
    const flatCard = fl && fl.free_kwh > 0 ? `<div class="card" style="margin-top:16px"><div class="card-head"><h2>Freistrom der Flat <span class="sub">Abrechnungsjahr ${new Date(`${fl.year_start}T12:00:00`).toLocaleDateString('de-DE')} – ${new Date(new Date(`${fl.year_end}T12:00:00`) - 86400000).toLocaleDateString('de-DE')}</span></h2></div><div class="card-body">
        <div class="row" style="justify-content:space-between;margin-bottom:6px"><b>${nf(fl.used_kwh, 0)} von ${nf(fl.free_kwh, 0)} kWh verbraucht</b><span class="muted">${fl.remaining_kwh > 0 ? `noch ${nf(fl.remaining_kwh, 0)} kWh frei` : `aufgebraucht am ${fmtDay(dayTs(fl.exhausted))}`}</span></div>
        <div class="progress"><i style="width:${Math.min(100, (fl.used_kwh / fl.free_kwh) * 100)}%;${fl.remaining_kwh > 0 ? '' : 'background:var(--err)'}"></i></div>
        <p class="faint" style="font-size:12.5px;margin:10px 0 0">Stand ${fmtDay(dayTs(d.days[d.days.length - 1].day))} · ${fl.remaining_kwh > 0 ? (fl.until ? `Beim Verbrauch der letzten 30 Tage reicht der Freistrom bis etwa ${new Date(`${fl.until}T12:00:00`).toLocaleDateString('de-DE')}.` : 'Beim Verbrauch der letzten 30 Tage reicht er bis zum Ende des Abrechnungsjahres.') : 'Seitdem kostet jede kWh den Preis über dem Freistrom.'}${fl.estimated_kwh > 0 ? ` Für Tage ohne Messwerte ist der anteilige Freistrom als verbraucht angesetzt (${nf(fl.estimated_kwh, 0)} kWh).` : ''}</p></div></div>` : '';
    el.innerHTML = `${nav}
      <div class="grid kpis">
        ${kpi('wallet', '', 'Stromkosten', `${cnt('ct', nf(t.total_eur, 2))}<small>€</small>`, `Netzbezug ${eur(t.energy_eur)} + Grundgebühr ${eur(t.fee_eur)} − Einspeisung ${eur(t.feed_in_eur)}${t.days < 28 ? ` · ${t.days} Tage` : ''}`)}
        ${kpi('euro', better != null && better > 0 ? 'ok' : 'warn', 'Ø bezahlter Preis', t.avg_paid_ct == null ? '–' : `${cnt('cp', nf(t.avg_paid_ct, 1))}<small>ct/kWh</small>`, t.avg_market_ct == null ? '' : `Ø aller Viertelstunden ${nf(t.avg_market_ct, 1)} ct${better != null ? ` · ${better >= 0 ? `${nf(better, 1)} ct günstiger gekauft` : `${nf(-better, 1)} ct teurer gekauft`}` : ''}`)}
        ${kpi('plug', '', 'Netzbezug', `${cnt('ci', nf(t.import_kwh, t.import_kwh < 10 ? 1 : 0))}<small>kWh</small>`, `Einspeisung ${nf(t.export_kwh, t.export_kwh < 10 ? 1 : 0)} kWh${d.feed_in.avg_ct ? ` à ${d.feed_in.per_array && t.export_kwh > 0.05 ? `Ø ${nf(t.feed_in_eur / t.export_kwh * 100, 2)}` : nf(d.feed_in.avg_ct, 2)} ct` : ' – Vergütung in den Einstellungen eintragen'}`)}
        ${!cmpOn ? '' : kpi('trophy', t.savings_eur >= 0 ? 'ok' : 'err', t.savings_eur >= 0 ? `Gespart ggü. ${cmpName}` : `Mehrkosten ggü. ${cmpName}`, `${cnt('cs', nf(Math.abs(t.savings_eur), 2))}<small>€</small>`, `${cmpText} wäre${isFlat ? '' : 'n'} ${eur(t.compare_total_eur)} gewesen`)}
        ${t.autarky_pct != null ? kpi('home', 'up', 'Autarkie', `${cnt('ca', nf(t.autarky_pct, 0))}<small>%</small>`, `des Hausverbrauchs aus eigener Erzeugung${t.self_use_pct != null ? ` · Eigenverbrauch ${nf(t.self_use_pct, 0)} % der PV` : ''}`) : ''}
      </div>
      ${t.unpriced_kwh > 0.5 ? `<div class="notice" style="margin-top:16px">${ic('info')}<div>Für ${nf(t.unpriced_kwh, 1)} kWh Netzbezug liegt kein Börsenpreis vor – sie fehlen in den Kosten.</div></div>` : ''}
      ${!tf.base_fee_eur ? `<div class="notice info" style="margin-top:16px">${ic('info')}<div>Grundgebühr, Einspeisevergütung und einen Vergleichstarif trägst du unter <a href="#/settings?tab=tariff">Einstellungen › Strompreis</a> ein.</div></div>` : ''}
      ${flatCard}
      <div class="card" style="margin-top:16px"><div class="card-head"><h2>Stromkosten pro Tag <span class="sub">inkl. anteiliger Grundgebühr, abzüglich Einspeisung</span></h2></div><div class="card-body">
        <div class="legend"><span class="static"><i class="box" style="background:var(--price)"></i>Dynamischer Tarif</span>${cmpOn ? `<span class="static"><i style="background:var(--text-2)"></i>${cmpName}</span>` : ''}</div>
        <div class="chart" id="costChart"></div></div></div>
      <div class="grid cols-2">
        <div class="card"><div class="card-head"><h2>Tage</h2></div><div class="card-body flush"><div class="table-wrap"><table class="table compact">
          <thead><tr><th>Tag</th><th class="num">Bezug kWh</th><th class="num">Ø ct</th><th class="num">Einsp. kWh</th><th class="num">Kosten</th>${cmpOn ? `<th class="num">${cmpName}</th>` : ''}</tr></thead><tbody>
          ${d.days.slice().reverse().map((x) => `<tr><td class="nowrap">${fmtDay(dayTs(x.day))}${x.hours < 23 ? ` <span class="faint">(${x.hours} h)</span>` : ''}</td><td class="num">${nf(x.import_kwh, 1)}</td><td class="num">${x.avg_paid_ct == null ? '–' : nf(x.avg_paid_ct, 1)}</td><td class="num">${nf(x.export_kwh, 1)}</td><td class="num">${eur(x.total_eur)}</td>${cmpOn ? `<td class="num faint">${eur(x.compare_total_eur)}</td>` : ''}</tr>`).join('')}
          </tbody></table></div></div></div>
        <div class="card"><div class="card-head"><h2>Monate</h2></div><div class="card-body flush"><div class="table-wrap"><table class="table compact">
          <thead><tr><th>Monat</th><th class="num">Bezug kWh</th><th class="num">Ø ct</th><th class="num">Kosten</th>${cmpOn ? `<th class="num">ggü. ${cmpName}</th>` : ''}</tr></thead><tbody>
          ${months.map((x) => `<tr class="click" data-m="${x.month}"><td class="nowrap">${esc(monthName(x.month))}${x.days < 28 ? ` <span class="faint">(${x.days} T.)</span>` : ''}</td><td class="num">${nf(x.import_kwh, 0)}</td><td class="num">${x.avg_paid_ct == null ? '–' : nf(x.avg_paid_ct, 1)}</td><td class="num">${eur(x.total_eur)}</td>${cmpOn ? `<td class="num ${x.savings_eur >= 0 ? 'best' : 'pos'}">${x.savings_eur >= 0 ? '−' : '+'}${nf(Math.abs(x.savings_eur), 2)} €</td>` : ''}</tr>`).join('')}
          </tbody></table></div></div></div>
      </div>`;
    chart($('#costChart'), {
      xs: d.days.map((x) => dayTs(x.day)), step: 86400, height: 220, tickCenter: true,
      bar: { label: 'Stromkosten', color: 'var(--price)', cls: 'bar-p', values: d.days.map((x) => x.total_eur), clsFor: (i, v) => (v < 0 ? 'neg' : '') },
      lines: cmpOn ? [{ key: 'fix', label: cmpName, color: 'var(--text-2)', dash: true, values: d.days.map((x) => x.compare_total_eur) }] : [],
      fmt: (v) => eur(v), axisFmt: (v) => `${nf(v, 2)} €`, head: (ts) => fmtDay(ts), tick: (ts) => new Date(ts * 1000).toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' }),
    });
    bindNav();
    $$('tr[data-m]').forEach((tr) => tr.addEventListener('click', () => { location.hash = `#/costs?m=${tr.dataset.m}`; }));
  }

  // ------------------------------------------------------------------ setup
  const LEVEL = { err: ['err', 'alert', 'Problem'], warn: ['warn', 'alert', 'Hinweis'], info: ['', 'info', 'Info'], ok: ['ok', 'checkCircle', 'OK'] };
  async function loadCheck(force = false) {
    if (!force && S.check && Date.now() / 1000 - S.check.at < 600) return S.check;
    S.check = await api('setup-check');
    renderNav();
    return S.check;
  }
  async function renderSetup(el, token) {
    const d = await loadCheck(true);
    if (stale(token)) return;
    const sm = d.summary;
    setHeader('Einrichtung', `${sm.ok || 0} in Ordnung · ${sm.warn || 0} Hinweise · ${sm.err || 0} Probleme`,
      `<a class="btn" href="api/export" download title="Datenbank, Einstellungen (ohne Schlüssel) und aktueller Zustand als ZIP – für eine ausführliche Prüfung">${ic('database')}<span class="hide-sm">Diagnose-Export</span></a><button class="btn" id="chkAgain">${ic('refresh')}<span class="hide-sm">Erneut prüfen</span></button>`);
    const order = { err: 0, warn: 1, info: 2, ok: 3 };
    const onlyIssues = store.get('setupIssues', false);
    el.innerHTML = `<div class="toolbar"><label class="check"><input type="checkbox" id="chkIssues" ${onlyIssues ? 'checked' : ''}>Nur Probleme und Hinweise anzeigen</label></div>
      ${!sm.err && !sm.warn ? `<div class="notice info" style="margin-bottom:16px">${ic('checkCircle')}<div><b>Alles eingerichtet.</b> EnergyPilot hat alles, was es braucht, und die Werte sind plausibel.</div></div>` : ''}
      <div class="grid cols-2">${d.groups.map((g) => {
        const checks = g.checks.slice().sort((a, b) => order[a.level] - order[b.level]).filter((c) => !onlyIssues || c.level === 'err' || c.level === 'warn');
        const worst = g.checks.reduce((w, c) => (order[c.level] < order[w] ? c.level : w), 'ok');
        return `<div class="card"><div class="card-head"><span class="dot ${LEVEL[worst][0]}"></span><h2>${esc(g.title)}</h2></div>
          <div class="card-body flush"><div class="list">${checks.map((c) => `<div class="list-item check-item">
            <div class="avatar ${LEVEL[c.level][0]}" style="width:30px;height:30px">${ic(LEVEL[c.level][1])}</div>
            <div class="grow"><div class="title" style="white-space:normal">${esc(c.title)}</div>${c.text ? `<div class="meta" style="white-space:normal">${esc(c.text)}</div>` : ''}</div>
            ${c.link && c.level !== 'ok' ? `<a class="btn sm" href="${c.link}">Beheben</a>` : ''}</div>`).join('')
            || '<div class="muted" style="padding:6px 18px 14px;font-size:13px">Keine Probleme.</div>'}</div></div></div>`;
      }).join('')}</div>`;
    $('#chkAgain').addEventListener('click', () => navigate());
    $('#chkIssues').addEventListener('change', (e) => { store.set('setupIssues', e.target.checked); navigate(); });
  }

  // --------------------------------------------------------------- settings
  const SET_TABS = [['arrays', 'solar', 'PV-Anlagen'], ['sources', 'cloudSun', 'Prognosequellen'], ['tariff', 'euro', 'Strompreis'], ['battery', 'battery', 'Batterie'], ['sensors', 'sliders', 'Sensoren & Standort'], ['look', 'palette', 'Darstellung']];
  async function renderSettings(el, token) {
    const q = query();
    let tab = q.get('tab') || store.get('settingsTab', 'arrays');
    if (!SET_TABS.some((t) => t[0] === tab)) tab = 'arrays';
    store.set('settingsTab', tab);
    await loadSettings();
    if (stale(token)) return;
    el.innerHTML = `<div class="seg" id="setTabs" style="margin-bottom:16px">${SET_TABS.map(([k, icon, label]) => `<button data-tab="${k}" class="${tab === k ? 'active' : ''}">${ic(icon)}${label}</button>`).join('')}</div><div id="setBody"></div>`;
    $$('#setTabs button').forEach((b) => b.addEventListener('click', () => { if (b.dataset.tab !== tab) location.hash = `#/settings?tab=${b.dataset.tab}`; }));
    const body = $('#setBody');
    const fn = { arrays: renderArrays, sources: renderSources, tariff: renderTariff, battery: renderBattery, sensors: renderSensors, look: renderLook }[tab];
    await fn(body, token);
  }

  /* Entity picker: type to search by name or entity ID, or open the list and pick.
     The chosen entity lives in a hidden input with the given id, so forms read
     it with .value like a select. An entity that is not in the list can be
     typed in directly (e.g. sensor.xyz) and confirmed with Enter. */
  const ENTITY_RE = /^[a-z_]+\.[a-z0-9_]+$/;
  const entState = (list, v) => {
    const e = list.find((x) => x.entity_id === v);
    return `${esc(v)}${e ? ` · <b>aktuell ${esc(e.state)} ${esc(e.unit || '')}</b>` : ''}`;
  };
  function entityPicker(id, list, value, kinds) {
    const cur = list.find((e) => e.entity_id === value);
    return `<div class="ent-pick" data-kinds="${kinds.join(',')}">
      <input type="hidden" id="${id}" value="${esc(value || '')}">
      <div class="ent-box"><span class="ent-ico">${ic('search')}</span>
        <input class="input ent-q" type="text" autocomplete="off" spellcheck="false" placeholder="Name oder Entität suchen …" value="${esc(cur ? cur.name : value || '')}" aria-label="Sensor suchen">
        <button type="button" class="icon-btn ent-clear ${value ? '' : 'hidden'}" title="Auswahl entfernen">${ic('x')}</button>
        <button type="button" class="icon-btn ent-open" title="Liste öffnen">${ic('chevronDown')}</button></div>
      <div class="ent-id mono ${value ? '' : 'hidden'}">${value ? entState(list, value) : ''}</div>
      <div class="ent-list hidden" role="listbox"></div></div>`;
  }
  function bindPickers(root, list) {
    $$('.ent-pick', root).forEach((pk) => {
      const kinds = pk.dataset.kinds.split(',');
      const hidden = pk.querySelector('input[type=hidden]');
      const q = pk.querySelector('.ent-q');
      const box = pk.querySelector('.ent-list');
      const idLine = pk.querySelector('.ent-id');
      const clear = pk.querySelector('.ent-clear');
      let active = 0; let shown = [];
      const label = (v) => { const e = list.find((x) => x.entity_id === v); return e ? e.name : v; };
      const set = (v) => {
        hidden.value = v; q.value = v ? label(v) : '';
        idLine.innerHTML = v ? entState(list, v) : ''; idLine.classList.toggle('hidden', !v); clear.classList.toggle('hidden', !v);
        close();
        hidden.dispatchEvent(new Event('change', { bubbles: true }));
      };
      const close = () => { box.classList.add('hidden'); pk.classList.remove('open'); };
      const draw = (term) => {
        const words = term.toLowerCase().split(/\s+/).filter(Boolean);
        const pool = list.filter((e) => kinds.includes(e.kind));
        shown = pool.filter((e) => { const hay = `${e.name} ${e.entity_id}`.toLowerCase(); return words.every((w) => hay.includes(w)); }).slice(0, 60);
        active = Math.max(0, Math.min(active, shown.length - 1));
        const typed = term.trim();
        const manual = ENTITY_RE.test(typed) && !list.some((e) => e.entity_id === typed);
        box.innerHTML = (manual ? `<div class="ent-opt manual" data-v="${esc(typed)}">${ic('plus')}<span>„${esc(typed)}“ übernehmen</span></div>` : '')
          + (shown.map((e, i) => `<div class="ent-opt ${i === active ? 'active' : ''} ${e.entity_id === hidden.value ? 'sel' : ''}" role="option" data-v="${esc(e.entity_id)}">
              <div class="grow"><div class="n">${esc(e.name)}</div><div class="i mono">${esc(e.entity_id)}</div></div>
              <div class="v">${esc(e.state)} ${esc(e.unit)}${e.statistics ? '' : '<br><span class="badge warn">keine Statistik</span>'}</div></div>`).join('')
          || (manual ? '' : `<div class="ent-empty">Kein passender Sensor${pool.length ? '' : ' – Home Assistant liefert keine passenden Sensoren'}. Eine Entitäts-ID wie <span class="mono">sensor.xyz</span> kannst du direkt eintippen.</div>`));
        box.classList.remove('hidden'); pk.classList.add('open');
        const a = box.querySelector('.ent-opt.active'); if (a) a.scrollIntoView({ block: 'nearest' });
      };
      q.addEventListener('focus', () => { q.select(); draw(''); });
      q.addEventListener('input', () => { active = 0; draw(q.value); });
      q.addEventListener('keydown', (e) => {
        if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
          e.preventDefault(); if (box.classList.contains('hidden')) { draw(q.value); return; }
          active = Math.max(0, Math.min(shown.length - 1, active + (e.key === 'ArrowDown' ? 1 : -1))); draw(q.value);
        } else if (e.key === 'Enter') {
          e.preventDefault();
          const typed = q.value.trim();
          if (ENTITY_RE.test(typed) && !shown.some((x) => x.entity_id === typed) && !list.some((x) => x.entity_id === typed)) set(typed);
          else if (shown[active]) set(shown[active].entity_id);
        } else if (e.key === 'Escape') { e.stopPropagation(); set(hidden.value); }
      });
      // leaving the field without choosing keeps the previous selection
      q.addEventListener('blur', () => setTimeout(() => { if (!pk.contains(document.activeElement)) { q.value = hidden.value ? label(hidden.value) : ''; close(); } }, 150));
      box.addEventListener('mousedown', (e) => e.preventDefault());
      box.addEventListener('click', (e) => { const o = e.target.closest('.ent-opt'); if (o) set(o.dataset.v); });
      clear.addEventListener('click', () => set(''));
      pk.querySelector('.ent-open').addEventListener('mousedown', (e) => e.preventDefault());
      pk.querySelector('.ent-open').addEventListener('click', () => { if (pk.classList.contains('open')) close(); else { q.focus(); } });
    });
  }
  const COMPASS = [['Nord', 0], ['Nordost', 45], ['Ost', 90], ['Südost', 135], ['Süd', 180], ['Südwest', 225], ['West', 270], ['Nordwest', 315]];
  const dirName = (az) => COMPASS[Math.round((((az % 360) + 360) % 360) / 45) % 8][0];
  const planesText = (a) => (a.planes || []).map((p) => `${dirName(p.azimuth)} ${nf(p.kwp, 2)} kWp/${nf(p.tilt)}°`).join(' + ');
  // one row per orientation (e.g. east and west string behind one inverter)
  const planeRow = (p = {}) => `<div class="plane-row" data-plane>
      <input class="input" data-k="kwp" type="number" step="0.01" min="0" value="${p.kwp ?? ''}" placeholder="kWp" aria-label="Leistung in kWp">
      <input class="input" data-k="tilt" type="number" step="1" min="0" max="90" value="${p.tilt ?? 30}" aria-label="Neigung in Grad">
      <div class="az"><select class="input" data-k="dir" aria-label="Himmelsrichtung">${COMPASS.map(([l, v]) => `<option value="${v}">${l}</option>`).join('')}<option value="">genau …</option></select>
        <input class="input" data-k="azimuth" type="number" step="1" min="0" max="359" value="${p.azimuth ?? 180}" aria-label="Ausrichtung in Grad"></div>
      <button type="button" class="icon-btn" data-del-plane title="Teilfläche entfernen">${ic('x')}</button></div>`;

  async function renderArrays(el) {
    setHeader('Einstellungen', 'PV-Anlagen – eine pro Messsensor');
    const draw = () => {
      const arrays = S.settings.arrays;
      el.innerHTML = `<div class="card"><div class="card-head"><h2>PV-Anlagen <span class="sub">${arrays.length}</span></h2><button class="btn primary sm" id="addArr">${ic('plus')}Anlage hinzufügen</button></div>
        <div class="card-body flush"><div class="list">${arrays.map((a) => `<div class="list-item clickable" data-edit="${a.id}">
            <div class="avatar accent">${ic('solar')}</div>
            <div class="grow"><div class="title">${esc(a.name)}</div><div class="meta">${nf(a.kwp, 2)} kWp · ${planesText(a)}${a.ac_max_kw ? ` · max. ${nf(a.ac_max_kw, 1)} kW` : ''}${a.feed_in_ct != null ? ` · Einspeisung ${nf(a.feed_in_ct, 2)} ct` : ''} · ${a.sensor ? `<span class="mono">${esc(a.sensor)}</span>` : '<span class="pos">kein Messsensor</span>'}</div></div>
            ${a.sensor ? `<button class="btn sm" data-geo="${a.id}" title="Aus den Messwerten prüfen, ob Ausrichtung und Neigung stimmen">${ic('compass')}<span class="hide-sm">Ausrichtung prüfen</span></button>` : ''}
            <button class="icon-btn" title="Bearbeiten">${ic('edit')}</button></div>`).join('')
          || '<div class="muted" style="padding:6px 18px 14px;font-size:13px">Noch keine Anlage. Lege für jeden Messsensor (meist ein Wechselrichter) eine Anlage an. Zeigen Module an einem Wechselrichter in verschiedene Richtungen – z. B. ein String nach Osten, einer nach Westen –, trägst du sie als Teilflächen derselben Anlage ein.</div>'}</div></div></div>
        <div class="notice info" style="margin-top:16px">${ic('info')}<div><b>Messsensor:</b> Ein Leistungssensor (W/kW, z. B. die AC-Leistung des Wechselrichters) oder ein Energiezähler (Wh/kWh). Er braucht eine Langzeitstatistik (state_class) – dann liest EnergyPilot die Erzeugung der letzten ${S.settings.backfill_days} Tage rückwirkend aus Home Assistant und kann die Prognosen sofort vergleichen.</div></div>`;
      $('#addArr').addEventListener('click', () => arrayForm());
      $$('[data-edit]').forEach((r) => r.addEventListener('click', (e) => { if (!e.target.closest('[data-geo]')) arrayForm(S.settings.arrays.find((a) => a.id === r.dataset.edit)); }));
      $$('[data-geo]').forEach((b) => b.addEventListener('click', () => geometryCheck(S.settings.arrays.find((a) => a.id === b.dataset.geo))));
    };
    function geometryCheck(cfg) {
      const planeTxt = (ps) => ps.map((p) => `${dirName(p.azimuth)} ${nf(p.azimuth, 0)}° · ${nf(p.tilt, 0)}° Neigung`).join('<br>');
      modal({
        title: `Ausrichtung prüfen – ${cfg.name}`,
        body: `<div id="geoBody"><div class="notice info">${ic('refresh', 'spin')}<div>EnergyPilot rechnet für verschiedene Ausrichtungen und Neigungen die Erzeugung der klaren Stunden nach und vergleicht sie mit deinen Messwerten …</div></div></div>`,
        foot: '<button class="btn" data-close>Schließen</button><button class="btn primary hidden" id="geoApply">Übernehmen</button>',
        async onMount(m, close) {
          let r;
          try { r = await api(`arrays/${cfg.id}/geometry`, { method: 'POST' }); } catch (e) { m.querySelector('#geoBody').innerHTML = errorBox(e.message); return; }
          if (!r.ok) { m.querySelector('#geoBody').innerHTML = `<div class="notice">${ic('info')}<div>${esc(r.reason)}</div></div>`; return; }
          const eff = r.implied_efficiency;
          m.querySelector('#geoBody').innerHTML = `
            <p class="explain">Grundlage: <b>${r.hours} klare Stunden</b> an ${r.days} Tagen (Sonnenhöhe über 20°, Wetter aus ${esc(r.model)}). Verglichen wird nur die <b>Form</b> der Tageskurve – die Höhe (kWp, Verluste) wird für jede Variante angepasst.</p>
            <div class="table-wrap"><table class="table compact"><thead><tr><th></th><th>Ausrichtung / Neigung</th><th class="num">Abweichung</th></tr></thead><tbody>
              <tr><td>Eingetragen</td><td>${planeTxt(r.current_planes)}</td><td class="num">${pct(r.current_error, 1)}</td></tr>
              <tr><td><b>Passt am besten</b></td><td>${planeTxt(r.planes)}</td><td class="num best">${pct(r.best_error, 1)}</td></tr>
            </tbody></table></div>
            <div class="notice ${r.suggest ? 'info' : ''}" style="margin-top:12px">${ic(r.suggest ? 'info' : 'checkCircle')}<div>${r.suggest
              ? `Die Messwerte passen deutlich besser zu <b>${r.rotation ? `${signed(r.rotation, 0)}° gedreht` : ''}${r.rotation && r.tilt_offset ? ' und ' : ''}${r.tilt_offset ? `${signed(r.tilt_offset, 0)}° ${r.tilt_offset > 0 ? 'steiler' : 'flacher'}` : ''}</b> (${nf(r.improvement, 0)} % weniger Abweichung). Das kann auch an Schatten liegen, der über den Tag wandert – übernimm den Vorschlag, wenn er zu deinem Dach passt.`
              : 'Die eingetragene Ausrichtung passt gut zu den Messwerten.'}</div></div>
            ${eff && Math.abs(eff - r.efficiency) >= 0.05 ? `<p class="faint" style="font-size:12.5px;margin:10px 0 0">Die Messwerte liegen insgesamt bei etwa ${pct(eff * 100, 0)} statt ${pct(r.efficiency * 100, 0)} Systemwirkungsgrad – das gleicht die lernende Prognose bereits aus; ändern kannst du ihn unter „Erweitert“.</p>` : ''}`;
          const btn = m.querySelector('#geoApply');
          if (r.suggest) {
            btn.classList.remove('hidden');
            btn.addEventListener('click', (e) => withBusy(e.currentTarget, async () => {
              try { await api('arrays', { method: 'POST', body: { id: cfg.id, planes: r.planes } }); await loadSettings(); close(); draw(); toast('Ausrichtung übernommen – alle Wettermodell-Prognosen werden neu berechnet.'); } catch (err) { toast(err.message, 'err'); }
            }));
          }
        },
      });
    }
    async function arrayForm(cfg = {}) {
      const isNew = !cfg.id;
      let ents = [];
      try { ents = await loadEntities(); } catch (e) { toast(`Sensoren konnten nicht geladen werden: ${e.message}`, 'err'); }
      modal({
        title: isNew ? 'PV-Anlage hinzufügen' : 'PV-Anlage bearbeiten',
        body: `<div class="form-grid">
          <div class="field span-2"><label>Name</label><input class="input" id="a_name" value="${esc(cfg.name || '')}" placeholder="z. B. Hausdach Süd oder Carport"></div>
          <div class="field span-2"><label>Messsensor (Wechselrichter)</label>${entityPicker('a_sensor', ents, cfg.sensor || '', ['power', 'energy'])}<span class="hint">Leistung (W/kW) oder Energiezähler (Wh/kWh) – er misst alle Teilflächen unten zusammen</span></div>
          <div class="field span-2"><label>Einspeisevergütung (ct/kWh) <span class="faint">(optional)</span></label><input class="input" id="a_feed" type="number" step="0.01" min="0" value="${cfg.feed_in_ct ?? ''}" placeholder="wie unter Strompreis (${nf(S.settings.tariff.feed_in_ct, 2)} ct)"><span class="hint">Nur nötig, wenn diese Anlage eine andere Vergütung hat. Leer = Wert unter Einstellungen › Strompreis; eingetragen ersetzt er diesen Wert für diese Anlage.</span></div>
        </div>
        <div class="field"><label>Teilflächen</label>
          <div class="plane-head"><span>Leistung (kWp)</span><span>Neigung (°)</span><span>Ausrichtung</span><span></span></div>
          <div id="a_planes">${(cfg.planes && cfg.planes.length ? cfg.planes : [{}]).map((p) => planeRow(p)).join('')}</div>
          <button type="button" class="btn sm" id="a_addPlane" style="align-self:flex-start">${ic('plus')}Teilfläche hinzufügen</button>
          <span class="hint">Eine Zeile pro Ausrichtung – bei einem Ost-West-Dach an einem Wechselrichter also eine Zeile Ost und eine Zeile West. Neigung: 0° = flach, 90° = senkrecht.</span>
          <div class="plane-sum" id="a_sum"></div></div>
        <details style="margin-bottom:6px"><summary class="muted" style="cursor:pointer;font-size:13px">Erweitert</summary>
          <div class="form-grid" style="margin-top:12px">
            <div class="field"><label>Systemwirkungsgrad (%)</label><input class="input" id="a_eff" type="number" step="1" min="50" max="100" value="${Math.round((cfg.efficiency ?? 0.88) * 100)}"><span class="hint">Wechselrichter, Kabel, Verschmutzung – typisch 85–90 %</span></div>
            <div class="field"><label>Wechselrichter-Grenze (kW)</label><input class="input" id="a_ac" type="number" step="0.1" min="0" value="${cfg.ac_max_kw || ''}" placeholder="keine"><span class="hint">Maximale AC-Leistung, falls die Anlage abregelt</span></div>
            <div class="field span-2"><label>Solcast Resource-ID <span class="faint">(optional)</span></label><input class="input mono" id="a_sc" value="${esc(cfg.solcast_id || '')}" placeholder="xxxx-xxxx-xxxx-xxxx"><span class="hint">Nur wenn Solcast unter „Prognosequellen“ eingerichtet ist</span></div>
          </div></details>`,
        foot: `${isNew ? '' : `<button class="btn danger left" id="a_del">${ic('trash')}Löschen</button>`}<button class="btn" data-close>Abbrechen</button><button class="btn primary" id="a_save">${ic('check')}Speichern</button>`,
        onMount(m, close) {
          const v = (id) => m.querySelector(id);
          bindPickers(m, ents);
          const num = (x) => Number(String(x).replace(',', '.'));
          const planes = () => $$('[data-plane]', m).map((r) => ({ kwp: num(r.querySelector('[data-k=kwp]').value), tilt: num(r.querySelector('[data-k=tilt]').value), azimuth: num(r.querySelector('[data-k=azimuth]').value) }));
          // direction list and exact degrees stay in sync; "genau …" allows any other angle
          const syncRow = (r) => {
            const az = num(r.querySelector('[data-k=azimuth]').value);
            const hit = COMPASS.find(([, d]) => d === az);
            if (hit) r.querySelector('[data-k=dir]').value = String(hit[1]);
            else r.querySelector('[data-k=dir]').value = '';
            r.querySelector('.az').classList.toggle('exact', !hit);
          };
          const syncAll = () => {
            const rows = $$('[data-plane]', m);
            rows.forEach(syncRow);
            rows.forEach((r) => { r.querySelector('[data-del-plane]').style.visibility = rows.length > 1 ? '' : 'hidden'; });
            const total = planes().reduce((a, p) => a + (p.kwp > 0 ? p.kwp : 0), 0);
            v('#a_sum').textContent = rows.length > 1 ? `Gesamt ${nf(total, 2)} kWp` : '';
          };
          const bindRow = (r) => {
            r.querySelector('[data-k=dir]').addEventListener('change', (e) => {
              if (e.target.value === '') { r.querySelector('.az').classList.add('exact'); r.querySelector('[data-k=azimuth]').focus(); return; }
              r.querySelector('[data-k=azimuth]').value = e.target.value;
              syncAll();
            });
            r.querySelector('[data-k=azimuth]').addEventListener('change', syncAll);
            r.querySelector('[data-k=kwp]').addEventListener('input', syncAll);
            r.querySelector('[data-del-plane]').addEventListener('click', () => { r.remove(); syncAll(); });
          };
          $$('[data-plane]', m).forEach(bindRow);
          v('#a_addPlane').addEventListener('click', () => {
            const last = planes().slice(-1)[0] || {};
            // typical case: the other half of an east-west roof
            const az = Number.isFinite(last.azimuth) ? (last.azimuth + 180) % 360 : 180;
            v('#a_planes').insertAdjacentHTML('beforeend', planeRow({ kwp: last.kwp || '', tilt: Number.isFinite(last.tilt) ? last.tilt : 30, azimuth: az }));
            const rows = $$('[data-plane]', m);
            bindRow(rows[rows.length - 1]);
            syncAll();
          });
          syncAll();
          v('#a_save').addEventListener('click', (e) => withBusy(e.currentTarget, async () => {
            const pl = planes();
            const body = { id: cfg.id, name: v('#a_name').value.trim(), planes: pl, sensor: v('#a_sensor').value, efficiency: Number(v('#a_eff').value) / 100, ac_max_kw: v('#a_ac').value || 0, solcast_id: v('#a_sc').value.trim(), feed_in_ct: v('#a_feed').value.trim() };
            if (!pl.length || pl.some((p) => !(p.kwp > 0))) { toast('Bitte für jede Teilfläche die Leistung in kWp angeben.', 'err'); return; }
            try {
              await api('arrays', { method: 'POST', body });
              await loadSettings(); close(); draw();
              toast(isNew ? 'Anlage angelegt – Prognosen und Messwerte werden jetzt geladen.' : 'Änderungen gespeichert.');
            } catch (err) { toast(err.message, 'err'); }
          }));
          if (v('#a_del')) v('#a_del').addEventListener('click', async () => {
            if (!(await confirmDialog('Anlage löschen?', `„${esc(cfg.name)}“ und alle gesammelten Prognosen und Messwerte dieser Anlage werden gelöscht.`, { ok: 'Löschen', danger: true }))) return;
            try { await api(`arrays/${cfg.id}`, { method: 'DELETE' }); await loadSettings(); close(); draw(); toast('Anlage gelöscht.'); } catch (err) { toast(err.message, 'err'); }
          });
        },
      });
    }
    draw();
    if (query().get('add') === '1') { history.replaceState(null, '', '#/settings?tab=arrays'); arrayForm(); }
  }

  async function saveSettings(values, msg = 'Einstellungen gespeichert.') {
    try { S.settings = { ...S.settings, ...(await api('settings', { method: 'POST', body: values })) }; await loadSettings(); toast(msg); return true; } catch (e) { toast(e.message, 'err'); return false; }
  }

  const SOLCAST_SIGNUP = 'https://solcast.com/free-rooftop-solar-forecasting';
  const SOLCAST_TOOLKIT = 'https://toolkit.solcast.com.au/';
  // Solcast counts the azimuth from north, east negative and west positive (south = 180)
  const solcastAzimuth = (az) => { const v = ((540 - az) % 360) - 180; return v === -180 ? 180 : v; };

  function solcastGuide() {
    const arrays = S.settings.arrays.filter((a) => a.kwp > 0);
    // Solcast knows one orientation per site: an even east/west split behaves almost like a flat
    // roof, otherwise the largest plane gives the direction
    const site = (a) => {
      const big = [...a.planes].sort((x, y) => y.kwp - x.kwp)[0];
      const [p, q] = a.planes;
      const ew = a.planes.length === 2 && Math.abs(Math.abs(p.azimuth - q.azimuth) - 180) <= 30 && Math.abs(p.kwp - q.kwp) <= 0.25 * Math.max(p.kwp, q.kwp);
      return ew ? { tilt: 0, az: 180, note: 'Ost/West – als flache Fläche' } : { tilt: big.tilt, az: solcastAzimuth(big.azimuth), note: a.planes.length > 1 ? 'Ausrichtung der größten Fläche' : '' };
    };
    const rows = arrays.map((a) => { const x = site(a); return `<tr><td>${esc(a.name)}${x.note ? `<div class="faint" style="font-size:12px">${x.note}</div>` : ''}</td><td>${nf(a.kwp, 2)} kWp</td><td>${a.ac_max_kw ? `${nf(a.ac_max_kw, 1)} kW` : '–'}</td><td>${nf(x.tilt, 0)}°</td><td>${nf(x.az, 0)}°</td></tr>`; });
    const multi = arrays.some((a) => a.planes.length > 1);
    modal({
      title: 'Solcast einrichten',
      wide: true,
      body: `<p class="explain">Solcast berechnet PV-Prognosen aus Satellitenbildern und gilt als eine der genauesten Quellen. Der Hobby-Zugang ist kostenlos: bis zu <b>2 Dachflächen</b> und <b>10 Abrufe am Tag</b>.</p>
        <ol class="guide">
          <li><b>Kostenlos registrieren</b> – auf der Solcast-Seite die Anmeldung starten und als Kontotyp <b>Home User / Hobbyist</b> wählen.<div class="row wrap" style="gap:8px;margin-top:8px"><a class="btn sm primary" href="${SOLCAST_SIGNUP}" target="_blank" rel="noopener">${ic('external')}Zur Solcast-Anmeldung</a></div></li>
          <li><b>Dachfläche anlegen</b> – im <a href="${SOLCAST_TOOLKIT}" target="_blank" rel="noopener">Solcast Toolkit</a> eine neue Rooftop-Site anlegen, den Standort auf der Karte setzen und diese Werte eintragen:
            ${rows.length ? `<div class="table-wrap" style="margin-top:8px"><table class="table"><thead><tr><th>Anlage</th><th>Leistung DC</th><th>Wechselrichter AC</th><th>Neigung</th><th>Azimut (Solcast)</th></tr></thead><tbody>${rows.join('')}</tbody></table></div>` : '<p class="muted">Lege zuerst deine PV-Anlagen in EnergyPilot an – dann stehen hier die passenden Werte.</p>'}
            <p class="hint" style="margin-top:6px">Achtung: Solcast zählt den Azimut anders als EnergyPilot – Norden 0°, Osten −90°, Westen 90°, Süden 180°. Die Tabelle ist schon umgerechnet. Wechselrichter AC nur eintragen, wenn bekannt – sonst die DC-Leistung.${multi ? ' Solcast kennt pro Site nur eine Ausrichtung, deshalb steht hier je Anlage eine Site mit der Gesamtleistung. Gleich große Ost- und West-Flächen erzeugen über den Tag fast wie eine flache Fläche.' : ''}</p></li>
          <li><b>Resource-ID übernehmen</b> – jede Site hat eine ID der Form <span class="mono">xxxx-xxxx-xxxx-xxxx</span>. Trage sie unter Einstellungen › PV-Anlagen bei der passenden Anlage ein (Erweitert).</li>
          <li><b>API-Schlüssel eintragen</b> – im Toolkit unter deinem Konto den API-Key kopieren, hier im Feld „API-Schlüssel“ einfügen und speichern.</li>
        </ol>
        <p class="explain" style="margin-top:12px">Solcast hat kein Prognose-Archiv: Vergleiche im Prognose-Check gibt es erst ab dem Tag der Einrichtung, das Lernmodell bezieht die Quelle nach wenigen sonnigen Tagen mit ein und gewichtet sie mit jeder Woche genauer.</p>`,
      foot: '<a class="btn" href="#/settings?tab=arrays" data-close>PV-Anlagen öffnen</a><button class="btn primary" data-close>Schließen</button>',
    });
  }

  async function renderSources(el) {
    setHeader('Einstellungen', 'Welche Prognosen gesammelt und verglichen werden');
    const s = S.settings.sources;
    const models = S.settings.models_available;
    el.innerHTML = `<div class="grid cols-2">
      <div class="card"><div class="card-head"><div class="avatar accent">${ic('cloudSun')}</div><h2>Open-Meteo Wettermodelle<div class="faint" style="font-weight:400;font-size:12.5px">Kostenlos, ohne Anmeldung – PV-Leistung berechnet EnergyPilot selbst</div></h2>${sw(s.open_meteo, 'id="s_om"')}</div>
        <div class="card-body"><p class="explain">Jedes Modell wird stündlich abgerufen. Aus Global- und Diffusstrahlung und der Temperatur berechnet EnergyPilot für jede Anlage mit ihrer Neigung und Ausrichtung die Leistung. Für die Vergangenheit lädt es das Prognose-Archiv nach.</p>
          <div class="models">${Object.entries(models).map(([k, l]) => `<label class="check"><input type="checkbox" data-model="${k}" ${s.models.includes(k) ? 'checked' : ''}><span class="swatch-dot" style="background:${srcColor(`om:${k}`)}"></span>${esc(l)}</label>`).join('')}</div></div></div>
      <div class="card"><div class="card-head"><div class="avatar accent">${ic('sun')}</div><h2>Forecast.Solar<div class="faint" style="font-weight:400;font-size:12.5px">Kostenlos – heute und morgen, eigener PV-Rechner</div></h2>${sw(s.forecast_solar, 'id="s_fs"')}</div>
        <div class="card-body"><p class="explain">Wird höchstens einmal pro Stunde und Anlage abgefragt – ein Abruf je Teilfläche (Limit 12 Abrufe pro Stunde und IP-Adresse; nach „Abruflimit“ pausiert EnergyPilot eine Stunde). Nutzt die Anlagendaten aus EnergyPilot. Werte liegen erst ab dem Tag vor, an dem die Quelle aktiviert wurde.</p></div></div>
      <div class="card"><div class="card-head"><div class="avatar accent">${ic('solar')}</div><h2>Solcast<div class="faint" style="font-weight:400;font-size:12.5px">Optional – kostenloser Hobby-Zugang mit API-Schlüssel</div></h2></div>
        <div class="card-body">
          <div class="field"><label>API-Schlüssel</label><input class="input mono" id="s_sckey" type="password" autocomplete="off" placeholder="${s.has_solcast_key ? 'gespeichert – leer lassen, um ihn zu behalten' : 'von toolkit.solcast.com.au'}"></div>
          <div class="field"><label>Abrufzeiten (Uhr)</label><input class="input" id="s_schours" value="${esc(s.solcast_hours.join(', '))}"><span class="hint">Pro Zeitpunkt ein Abruf je Anlage. Der Hobby-Zugang erlaubt 10 Abrufe am Tag – bei 2 Anlagen also höchstens 5 Zeitpunkte.</span></div>
          <p class="explain">Die Resource-ID jeder Dachfläche trägst du bei der jeweiligen PV-Anlage ein (Erweitert).</p>
          <div class="row wrap" style="gap:8px"><button class="btn sm" id="s_schelp">${ic('info')}Anleitung</button><a class="btn sm" href="${SOLCAST_TOOLKIT}" target="_blank" rel="noopener">${ic('external')}Solcast Toolkit</a>
          ${s.has_solcast_key ? `<button class="btn sm" id="s_scclear">${ic('trash')}Schlüssel entfernen</button>` : ''}</div></div></div>
      <div class="card"><div class="card-head"><div class="avatar accent">${ic('database')}</div><h2>Rückblick</h2></div>
        <div class="card-body"><div class="field"><label>Tage rückwirkend laden</label><input class="input" id="s_back" type="number" min="0" max="730" value="${S.settings.backfill_days}"><span class="hint">Messwerte aus der Langzeitstatistik von Home Assistant und archivierte Wettermodell-Prognosen. Erhöhen lädt die fehlenden Tage nach.</span></div></div></div>
    </div>
    <div class="row" style="margin-top:16px"><button class="btn primary" id="s_save">${ic('check')}Speichern</button></div>`;
    $('#s_save').addEventListener('click', (e) => withBusy(e.currentTarget, () => saveSettings({
      sources: {
        open_meteo: $('#s_om').checked, forecast_solar: $('#s_fs').checked,
        models: $$('[data-model]').filter((c) => c.checked).map((c) => c.dataset.model),
        solcast_key: $('#s_sckey').value.trim(),
        solcast_hours: $('#s_schours').value.split(/[,;\s]+/).filter(Boolean).map(Number).filter((n) => n >= 0 && n <= 23),
      },
      backfill_days: Number($('#s_back').value),
    }).then((ok) => { if (ok) renderSources(el); })));
    $('#s_schelp').addEventListener('click', solcastGuide);
    if ($('#s_scclear')) $('#s_scclear').addEventListener('click', () => saveSettings({ sources: { solcast_clear: true } }, 'Solcast-Schlüssel entfernt.').then(() => renderSources(el)));
  }

  async function renderTariff(el) {
    setHeader('Einstellungen', 'Dynamischer Stromtarif');
    const t = S.settings.tariff;
    const pvArrays = S.settings.arrays.filter((a) => a.kwp > 0);
    const ownFeed = pvArrays.filter((a) => a.feed_in_ct != null);
    const tariffFeed = pvArrays.filter((a) => a.feed_in_ct == null);  // arrays that use the payment below
    const feedUnused = ownFeed.length > 0 && !tariffFeed.length;
    if (!S.overview) { try { S.overview = await api('overview'); } catch { /* example uses a placeholder */ } }
    const draw = () => {
      el.innerHTML = `<div class="grid cols-2">
        <div class="card"><div class="card-head"><div class="avatar accent">${ic('euro')}</div><h2>Arbeitspreis</h2></div><div class="card-body">
          <p class="explain">Dynamische Stromtarife geben den Börsenpreis (EPEX Day-Ahead) stündlich bzw. viertelstündlich weiter. Auf den Börsenpreis kommen feste Bestandteile: Netzentgelt, Umlagen, Stromsteuer und der Aufschlag des Anbieters. Die Werte stehen im Vertrag oder auf der Rechnung.</p>
          <div class="form-grid">
            <div class="field"><label>Gebotszone</label><input class="input" id="t_zone" list="t_zones" value="${esc(t.bidding_zone)}"><datalist id="t_zones"><option value="DE-LU"><option value="AT"><option value="CH"><option value="NL"><option value="BE"><option value="FR"></datalist><span class="hint">Deutschland: DE-LU</span></div>
            <div class="field"><label>Aufschlag netto (ct/kWh)</label><input class="input" id="t_markup" type="number" step="0.01" min="0" value="${t.markup_ct}"><span class="hint">Summe aller festen Preisbestandteile ohne MwSt</span></div>
            <div class="field"><label>Mehrwertsteuer (%)</label><input class="input" id="t_vat" type="number" step="0.1" min="0" value="${t.vat}"></div>
            <div class="field ${feedUnused ? 'unused' : ''}"><label>Einspeisevergütung (ct/kWh)${feedUnused ? ' <span class="badge">nicht verwendet</span>' : ''}</label><input class="input" id="t_feed" type="number" step="0.01" min="0" value="${t.feed_in_ct}"><span class="hint">${feedUnused
              ? 'Alle PV-Anlagen haben eine eigene Vergütung (Einstellungen › PV-Anlagen) – dieser Wert wird deshalb nicht verwendet.'
              : ownFeed.length ? `Gilt für: ${tariffFeed.map((a) => esc(a.name)).join(', ')} – ${ownFeed.map((a) => esc(a.name)).join(', ')} ${ownFeed.length > 1 ? 'haben' : 'hat'} eine eigene Vergütung`
                : 'Für Planung und Kostenübersicht – eine eigene Vergütung je Anlage stellst du bei der Anlage ein'}</span></div>
            ${ownFeed.length ? `<div class="field span-2"><label>Einspeisung aufteilen</label><div class="seg" id="t_split">${[['kwp', 'nach Anlagenleistung (kWp)'], ['production', 'nach gemessener Erzeugung']].map(([v, l]) => `<button type="button" data-v="${v}" class="${(t.feed_in_split || 'kwp') === v ? 'active' : ''}">${l}</button>`).join('')}</div>
              <div class="feed-rates">${pvArrays.map((a) => `<span>${esc(a.name)} <b>${nf(a.feed_in_ct ?? t.feed_in_ct, 2)} ct</b> <span class="faint">· ${nf(a.kwp, 2)} kWp${a.feed_in_ct == null ? ' · Wert oben' : ''}</span></span>`).join('')}</div>
              <ul class="hint feed-explain">
                <li><b>Nach Anlagenleistung (kWp):</b> Die eingespeiste Energie wird im Verhältnis der installierten Leistung auf die Anlagen verteilt – so rechnen die meisten Netzbetreiber, wenn mehrere Anlagen einen gemeinsamen Einspeisezähler haben. Mit deinen Anlagen ergibt das <b>${nf(pvArrays.reduce((x, a) => x + a.kwp * (a.feed_in_ct ?? t.feed_in_ct), 0) / pvArrays.reduce((x, a) => x + a.kwp, 0), 2)} ct/kWh</b>.</li>
                <li><b>Nach gemessener Erzeugung:</b> In jeder Stunde bekommt jede Anlage den Anteil, den sie in dieser Stunde erzeugt hat. Nachts oder ohne Messwerte wird nach kWp aufgeteilt. Nur wählen, wenn dein Netzbetreiber so abrechnet (z. B. mit eigenen Erzeugungszählern).</li>
              </ul></div>` : ''}
            <div class="field"><label>Grundgebühr (€/Monat)</label><input class="input" id="t_fee" type="number" step="0.01" min="0" value="${t.base_fee_eur ?? 0}"><span class="hint">Nur für die Kostenübersicht</span></div>
          </div>
          <label class="check" style="margin:6px 0 12px"><input type="checkbox" id="t_cmpon" ${t.compare_enabled !== false ? 'checked' : ''}><span><b>Mit einem anderen Tarif vergleichen</b> <span class="faint">– die Kosten-Seite zeigt dann, was er gekostet hätte</span></span></label>
          <div id="t_cmpbox">
          <div class="field" style="margin-top:4px"><label>Vergleichen mit</label>
            <div class="seg" id="t_ctype">${[['fixed', 'Festpreis'], ['flat', 'Flat mit Freistrom']].map(([v, l]) => `<button type="button" data-v="${v}" class="${(t.compare_type || 'fixed') === v ? 'active' : ''}">${l}</button>`).join('')}</div>
            <span class="hint">Die Kosten-Seite zeigt, was du mit diesem Tarif statt dem dynamischen bezahlt hättest.</span></div>
          <div class="form-grid" id="t_fixed">
            <div class="field"><label>Arbeitspreis brutto (ct/kWh)</label><input class="input" id="t_cmp" type="number" step="0.01" min="0" value="${t.compare_price_ct ?? 32}"></div>
            <div class="field"><label>Grundpreis (€/Monat)</label><input class="input" id="t_cmpfee" type="number" step="0.01" min="0" value="${t.compare_base_fee_eur ?? 12}"></div></div>
          <div class="form-grid" id="t_flat">
            <div class="field"><label>Grundgebühr (€/Monat)</label><input class="input" id="t_ffee" type="number" step="0.01" min="0" value="${t.flat_fee_eur ?? 0}"></div>
            <div class="field"><label>Freistrom (kWh/Jahr)</label><input class="input" id="t_ffree" type="number" step="1" min="0" value="${t.flat_free_kwh ?? 0}"><span class="hint">Netzbezug, der mit der Grundgebühr bezahlt ist</span></div>
            <div class="field"><label>Preis über dem Freistrom (ct/kWh)</label><input class="input" id="t_fprice" type="number" step="0.01" min="0" value="${t.flat_price_ct ?? 0}"><span class="hint">brutto</span></div>
            <div class="field"><label>Einspeisevergütung (ct/kWh)</label><input class="input" id="t_ffeed" type="number" step="0.01" min="0" value="${t.flat_feed_in_ct ?? 0}"><span class="hint">die in diesem Tarif gezahlt wird</span></div>
            <div class="field"><label>Abrechnungsjahr beginnt</label><select class="input" id="t_fstart">${MONTHS.map((m, i) => `<option value="${i + 1}" ${Number(t.flat_year_start || 1) === i + 1 ? 'selected' : ''}>${m}</option>`).join('')}</select><span class="hint">Ab dann wird der Freistrom verbraucht</span></div></div>
          </div>
          <div class="notice info" id="t_prev">${ic('info')}<div></div></div>
          <div class="row" style="margin-top:14px"><button class="btn primary" id="t_save">${ic('check')}Speichern</button></div>
        </div></div>
        <div class="card"><div class="card-head"><div class="avatar accent">${ic('target')}</div><h2>Aufschlag aus einem Preis berechnen</h2></div><div class="card-body">
          <p class="explain">Trag einen Gesamtpreis aus der <b>App deines Stromanbieters</b> (oder von der Rechnung) ein – mit Tag und Uhrzeit der Viertelstunde. EnergyPilot sucht den Börsenpreis dieser Viertelstunde und rechnet den Aufschlag zurück. Mit zwei, drei Preisen zu verschiedenen Uhrzeiten siehst du auch, ob alles zusammenpasst.</p>
          <div class="calib-head"><span>Tag</span><span>Uhrzeit</span><span>Gesamtpreis (ct/kWh)</span><span></span></div>
          <div id="c_rows"></div>
          <button type="button" class="btn sm" id="c_add">${ic('plus')}Weiteren Preis</button>
          <div id="c_result" style="margin-top:14px"></div>
        </div></div></div>`;
      // markup from sample prices: price / (1 + VAT) - spot price of that quarter hour
      const calibRow = () => `<div class="calib-row" data-calib><input class="input" type="date" data-k="day" value="${localDay()}"><input class="input" type="time" step="900" data-k="time" value="08:15"><input class="input" type="number" step="0.01" data-k="price" placeholder="z. B. 35,20"><button type="button" class="icon-btn" data-del title="Entfernen">${ic('x')}</button></div>`;
      const calcMarkup = async () => {
        const rows = $$('[data-calib]').map((r) => ({ day: r.querySelector('[data-k=day]').value, time: r.querySelector('[data-k=time]').value, price: Number(String(r.querySelector('[data-k=price]').value).replace(',', '.')) })).filter((r) => r.day && r.time && r.price > 0);
        const out = $('#c_result');
        if (!rows.length) { out.innerHTML = ''; return; }
        const vat = Number($('#t_vat').value) || 0;
        const days = {};
        const results = [];
        for (const r of rows) {
          try { days[r.day] = days[r.day] || (await api(`prices?day=${r.day}&days=1`)).slots; } catch (e) { out.innerHTML = errorBox(e.message); return; }
          const ts = new Date(`${r.day}T${r.time}:00`).getTime() / 1000;
          const slot = days[r.day].find((s) => s.ts <= ts && ts < s.ts + s.dur);
          results.push({ ...r, spot: slot ? slot.spot : null, markup: slot ? r.price / (1 + vat / 100) - slot.spot : null });
        }
        const ok = results.filter((r) => r.markup != null);
        const mean = ok.length ? ok.reduce((a, r) => a + r.markup, 0) / ok.length : null;
        const spread = ok.length > 1 ? Math.max(...ok.map((r) => r.markup)) - Math.min(...ok.map((r) => r.markup)) : 0;
        out.innerHTML = `<div class="table-wrap"><table class="table compact"><thead><tr><th>Viertelstunde</th><th class="num">Gesamt</th><th class="num">Börse netto</th><th class="num">Aufschlag netto</th></tr></thead><tbody>
            ${results.map((r) => `<tr><td class="nowrap">${fmtDay(dayTs(r.day))} ${esc(r.time)}</td><td class="num">${nf(r.price, 2)} ct</td><td class="num">${r.spot == null ? '<span class="pos">kein Börsenpreis</span>' : `${nf(r.spot, 2)} ct`}</td><td class="num">${r.markup == null ? '–' : `<b>${nf(r.markup, 2)} ct</b>`}</td></tr>`).join('')}
          </tbody></table></div>
          ${mean == null ? `<div class="notice" style="margin-top:10px">${ic('alert')}<div>Für diese Zeit liegt kein Börsenpreis vor – EnergyPilot speichert die Preise ab dem ersten Start, Tage davor sind nicht verfügbar.</div></div>`
            : `<div class="notice ${spread > 0.3 ? '' : 'info'}" style="margin-top:10px">${ic(spread > 0.3 ? 'alert' : 'checkCircle')}<div>Aufschlag netto: <b>${nf(mean, 2)} ct/kWh</b>${ok.length > 1 ? (spread > 0.3 ? ` – die Werte weichen um ${nf(spread, 2)} ct voneinander ab. Prüfe Uhrzeit und Preis; manche Anbieter rechnen stündlich statt viertelstündlich ab.` : ' – die Preise passen gut zusammen.') : ''}</div></div>
              <button class="btn primary sm" id="c_apply" style="margin-top:10px">${ic('check')}Als Aufschlag übernehmen</button>`}`;
        if ($('#c_apply')) $('#c_apply').addEventListener('click', () => { $('#t_markup').value = mean.toFixed(2); prev(); $('#t_markup').focus(); toast('Aufschlag eingetragen – mit „Speichern“ übernehmen.', 'info'); });
      };
      let calcT = 0;
      const bindRow = (r) => {
        r.querySelectorAll('input').forEach((i) => i.addEventListener('input', () => { clearTimeout(calcT); calcT = setTimeout(calcMarkup, 400); }));
        r.querySelector('[data-del]').addEventListener('click', () => { r.remove(); calcMarkup(); });
      };
      const addRow = () => { $('#c_rows').insertAdjacentHTML('beforeend', calibRow()); const rows = $$('[data-calib]'); bindRow(rows[rows.length - 1]); };
      addRow();
      $('#c_add').addEventListener('click', addRow);
      $('#t_vat').addEventListener('input', () => { clearTimeout(calcT); calcT = setTimeout(calcMarkup, 400); });
      const prev = () => {
        const spot = S.overview && S.overview.price ? S.overview.price.spot : 10;
        const mk = Number($('#t_markup').value) || 0; const vat = Number($('#t_vat').value) || 0;
        $('#t_prev div').innerHTML = `Beispiel: Börsenpreis ${nf(spot, 2)} ct + Aufschlag ${nf(mk, 2)} ct = ${nf(spot + mk, 2)} ct netto → <b>${nf((spot + mk) * (1 + vat / 100), 2)} ct/kWh</b> brutto`;
      };
      ['#t_markup', '#t_vat'].forEach((id) => $(id).addEventListener('input', prev));
      prev();
      const ctype = () => ($('#t_ctype button.active') || {}).dataset?.v || 'fixed';
      const showType = () => { $('#t_fixed').classList.toggle('hidden', ctype() !== 'fixed'); $('#t_flat').classList.toggle('hidden', ctype() !== 'flat'); };
      $$('#t_ctype button').forEach((btn) => btn.addEventListener('click', () => { $$('#t_ctype button').forEach((x) => x.classList.toggle('active', x === btn)); showType(); }));
      showType();
      // the entered values stay saved while the comparison is off
      const showCmp = () => $('#t_cmpbox').classList.toggle('hidden', !$('#t_cmpon').checked);
      $('#t_cmpon').addEventListener('change', showCmp);
      showCmp();
      $$('#t_split button').forEach((btn) => btn.addEventListener('click', () => { $$('#t_split button').forEach((x) => x.classList.toggle('active', x === btn)); }));
      $('#t_save').addEventListener('click', (e) => withBusy(e.currentTarget, () => saveSettings({ tariff: { bidding_zone: $('#t_zone').value,
        feed_in_split: ($('#t_split button.active') || { dataset: { v: t.feed_in_split || 'kwp' } }).dataset.v, markup_ct: $('#t_markup').value, vat: $('#t_vat').value, feed_in_ct: $('#t_feed').value, base_fee_eur: $('#t_fee').value, compare_price_ct: $('#t_cmp').value, compare_base_fee_eur: $('#t_cmpfee').value,
        compare_enabled: $('#t_cmpon').checked, compare_type: ctype(), flat_fee_eur: $('#t_ffee').value, flat_free_kwh: $('#t_ffree').value, flat_price_ct: $('#t_fprice').value, flat_feed_in_ct: $('#t_ffeed').value, flat_year_start: $('#t_fstart').value } })));
    };
    draw();
  }

  async function renderBattery(el) {
    setHeader('Einstellungen', 'Heimspeicher für die Planung');
    const b = S.settings.battery;
    const f = (id, label, val, unit, hint, attrs = '') => `<div class="field"><label>${label}${unit ? ` (${unit})` : ''}</label><input class="input" id="${id}" type="number" ${attrs} value="${val}"><span class="hint">${hint}</span></div>`;
    el.innerHTML = `<div class="grid cols-2"><div class="card"><div class="card-head"><div class="avatar accent">${ic('battery')}</div><h2>Batterie</h2></div><div class="card-body">
        <p class="explain">Die Werte stehen im Datenblatt bzw. in der App des Speichers. Der Ladezustand kommt aus dem Sensor unter <a href="#/settings?tab=sensors">Sensoren</a>.</p>
        <div class="form-grid">
          ${f('b_cap', 'Nutzbare Kapazität', b.capacity_kwh, 'kWh', 'z. B. 11', 'step="0.1" min="0.5"')}
          ${f('b_min', 'Reserve', b.min_soc, '%', 'unter diesen Ladezustand wird nicht entladen', 'step="1" min="0" max="90"')}
          ${f('b_pc', 'Max. Ladeleistung', b.max_charge_kw, 'kW', '', 'step="0.1" min="0.1"')}
          ${f('b_pd', 'Max. Entladeleistung', b.max_discharge_kw, 'kW', '', 'step="0.1" min="0.1"')}
          ${f('b_eff', 'Wirkungsgrad Laden + Entladen', Math.round(b.efficiency * 100), '%', 'typisch 88–95 %', 'step="1" min="50" max="100"')}
          ${f('b_max', 'Netzladen bis', b.max_soc_grid, '%', 'höchster Ladezustand beim Laden aus dem Netz', 'step="1" min="10" max="100"')}
        </div>
        <label class="check" style="margin:4px 0 16px"><input type="checkbox" id="b_grid" ${b.grid_charge ? 'checked' : ''}>Laden aus dem Netz einplanen, wenn es sich lohnt</label>
        <div class="field"><label>Sicherheitsabschlag bei unsicherer PV-Prognose</label>
          <div class="seg" id="b_caution">${[[0, 'Aus'], [0.5, 'Mittel'], [1, 'Vorsichtig']].map(([v, l]) => `<button type="button" data-v="${v}" class="${Number(b.pv_caution ?? 0.5) === v ? 'active' : ''}">${l}</button>`).join('')}</div>
          <span class="hint">Der Planer rechnet mit weniger Sonne, je unsicherer die Prognose ist („Vorsichtig“ = untere Grenze der Spanne). So bleibt der Akku eher für den Abend gefüllt, wenn der Tag trüber wird als erwartet.</span></div>
        <button class="btn primary" id="b_save">${ic('check')}Speichern</button></div></div></div>`;
    $('#b_save').addEventListener('click', (e) => withBusy(e.currentTarget, () => saveSettings({ battery: {
      capacity_kwh: $('#b_cap').value, min_soc: $('#b_min').value, max_charge_kw: $('#b_pc').value, max_discharge_kw: $('#b_pd').value,
      efficiency: Number($('#b_eff').value) / 100, max_soc_grid: $('#b_max').value, grid_charge: $('#b_grid').checked,
      pv_caution: Number(($('#b_caution button.active') || {}).dataset?.v ?? 0.5) } })));
    $$('#b_caution button').forEach((btn) => btn.addEventListener('click', () => { $$('#b_caution button').forEach((x) => x.classList.toggle('active', x === btn)); }));
  }

  // Plausibility check: what the chosen sensors measured on average per day
  async function consumptionCheck(box) {
    if (!box) return;
    let d;
    try { d = await api('consumption-check'); } catch (e) { box.innerHTML = `<div class="card-body">${errorBox(e.message)}</div>`; return; }
    const names = { house: ['Hausverbrauch', 'home'], ev: ['E-Auto / Wallbox', 'plug'], heater: ['Heizstab', 'zap'], base: ['Grundverbrauch', 'home'] };
    const rows = Object.entries(d.series).map(([k, v]) => `<div class="list-item"><div class="avatar ${k === 'base' ? 'accent' : ''}">${ic(names[k][1])}</div>
        <div class="grow"><div class="title">${names[k][0]}${k === 'base' ? ' <span class="faint" style="font-weight:400">= Haus − E-Auto − Heizstab</span>' : ''}</div>
          <div class="meta">${v.hours} von ${d.days * 24} Stunden mit Messwert${v.negative ? ' · <span class="pos">negative Werte – das Vorzeichen wird automatisch umgedreht</span>' : ''}${k !== 'base' && v.hours < d.days * 24 * 0.9 ? ' · <span class="pos">Lücken: diese Stunden fehlen im Grundverbrauch</span>' : ''}</div></div>
        <b class="num">${nf(Math.abs(v.kwh_per_day), 1)} kWh/Tag</b></div>`).join('');
    box.innerHTML = `<div class="card-head"><h2>Kontrolle <span class="sub">Durchschnitt pro Tag, letzte ${d.days} Tage</span></h2></div>
      <div class="card-body flush"><div class="list">${rows || '<div class="muted" style="padding:6px 18px 14px;font-size:13px">Noch keine Messwerte – bitte zuerst den Hausverbrauch auswählen und speichern.</div>'}</div>
      ${d.forecast_kwh_per_day != null ? `<div class="muted" style="padding:10px 18px 12px;font-size:12.5px;border-top:1px solid var(--border)">Verbrauchsprognose (Vortag) im selben Zeitraum: <b>${nf(d.forecast_kwh_per_day, 1)} kWh/Tag</b>. Passt der Grundverbrauch nicht zu deinem Gefühl, prüfe den Hausverbrauch-Sensor: Er soll den gesamten Verbrauch des Hauses messen – nicht den Netzbezug und nicht den Zählerstand des Smartmeters.</div>` : ''}</div>`;
  }

  async function renderSensors(el) {
    setHeader('Einstellungen', 'Welche Sensoren EnergyPilot liest');
    let ents = [];
    try { ents = await loadEntities(true); } catch (e) { toast(`Sensoren konnten nicht geladen werden: ${e.message}`, 'err'); }
    const s = S.settings.sensors; const loc = S.settings.location; const ha = S.settings.ha_location;
    const inv = S.settings.invert || {};
    // key, input id, label, hint, kinds, required, has direction
    const F = {
      house: ['n_house', 'Hausverbrauch', 'Gesamter Verbrauch des Hauses, inklusive E-Auto und Heizstab', ['power', 'energy'], true, true],
      grid: ['n_grid', 'Netzleistung', 'Vom Smartmeter: positiv = Bezug, negativ = Einspeisung', ['power'], true, true],
      grid_import: ['n_gin', 'Netzbezug', '', ['power', 'energy'], false, false],
      grid_export: ['n_gout', 'Einspeisung', '', ['power', 'energy'], false, false],
      battery_soc: ['n_soc', 'Ladezustand', 'In Prozent', ['percent'], true, false],
      battery_power: ['n_bp', 'Leistung', 'Positiv = Laden, negativ = Entladen', ['power'], true, true],
      ev: ['n_ev', 'E-Auto / Wallbox', 'Ladeleistung oder Ladezähler', ['power', 'energy'], false, false],
      heater: ['n_heater', 'Heizstab', 'Leistung oder Energiezähler', ['power', 'energy'], false, false],
    };
    const row = (key) => {
      const [id, label, hint, kinds, req, dir] = F[key];
      return `<div class="sens-row">
        <div class="sens-label"><div class="n">${label}${req ? '' : ' <span class="faint">optional</span>'}</div>${hint ? `<div class="h">${hint}</div>` : ''}</div>
        <div class="sens-pick">${entityPicker(id, ents, s[key] || '', kinds)}
          ${dir ? `<div class="sens-dir" id="dirrow_${key}"><span class="dir-line" id="dir_${key}"></span><label class="check inv"><input type="checkbox" id="inv_${key}" ${inv[key] ? 'checked' : ''}>Richtung umkehren</label></div>` : ''}</div></div>`;
    };
    const section = (icon, title, sub, keys, body, foot = '') => `<div class="card sens-sec" data-keys="${keys.join(',')}">
      <div class="card-head"><div class="avatar accent">${ic(icon)}</div><h2>${title}<div class="faint" style="font-weight:400;font-size:12.5px">${sub}</div></h2><span class="badge sens-state"></span></div>
      <div class="card-body">${body}${foot}</div></div>`;
    const locSet = loc.latitude != null && loc.latitude !== '' && loc.longitude != null && loc.longitude !== '';
    el.innerHTML = `<div class="sens-page">
      ${section('home', 'Haus', 'Grundlage der Verbrauchsprognose', ['house'], row('house'))}
      ${section('zap', 'Stromnetz', 'Bezug und Einspeisung am Smartmeter', ['grid'], row('grid'),
        `<details class="sens-more" ${s.grid_import || s.grid_export ? 'open' : ''}><summary>${ic('chevron')}Bezug und Einspeisung getrennt <span class="faint">– optional, genauer für die Kosten</span></summary>
          <p class="explain">Mit der Netzleistung allein heben sich Bezug und Einspeisung innerhalb einer Stunde gegenseitig auf. Viele Speicher und Smartmeter liefern beide Werte getrennt.</p>
          ${row('grid_import')}${row('grid_export')}</details>`)}
      ${section('battery', 'Batterie', 'Für Planung und Reichweite', ['battery_soc', 'battery_power'], row('battery_soc') + row('battery_power'))}
      ${section('car', 'Große Verbraucher', 'Werden vom Hausverbrauch abgezogen – die Prognose lernt nur den Grundverbrauch', ['ev', 'heater'], row('ev') + row('heater'),
        `<div class="sens-row"><div></div><label class="check" style="font-size:13px"><input type="checkbox" id="n_hsurplus" ${(S.settings.devices || {}).heater_surplus !== false ? 'checked' : ''}><span>Heizstab läuft nur mit PV-Überschuss <span class="faint">– eigene Regelung, nimmt nie Strom aus Akku oder Netz</span></span></label></div>`)}
      <div class="card sens-sec"><div class="card-head"><div class="avatar accent">${ic('pin')}</div><h2>Standort<div class="faint" style="font-weight:400;font-size:12.5px" id="locSub">${locSet ? `Eigener Standort (${nf(+loc.latitude, 3)}, ${nf(+loc.longitude, 3)})` : `Aus Home Assistant${ha ? ` (${nf(ha[0], 3)}, ${nf(ha[1], 3)})` : ''}`}</div></h2>
        <button class="btn sm" id="locToggle">${locSet ? 'Ändern' : 'Abweichend eintragen'}</button></div>
        <div class="card-body ${locSet ? '' : 'hidden'}" id="locBody">
          <div class="form-grid"><div class="field"><label>Breitengrad</label><input class="input" id="n_lat" type="number" step="0.0001" value="${loc.latitude ?? ''}" placeholder="${ha ? ha[0] : ''}"></div>
          <div class="field"><label>Längengrad</label><input class="input" id="n_lon" type="number" step="0.0001" value="${loc.longitude ?? ''}" placeholder="${ha ? ha[1] : ''}"></div></div>
          <span class="hint faint" style="font-size:12px">Nur nötig, wenn die Anlage nicht am Home-Assistant-Standort steht. Leer lassen = Standort aus Home Assistant. Eine Änderung lädt die Wetterdaten für den neuen Ort neu.</span></div></div>
      <div class="savebar" id="saveBar"><span class="muted" id="saveMsg">Alles gespeichert</span><button class="btn" id="n_reset" disabled>Verwerfen</button><button class="btn primary" id="n_save" disabled>${ic('check')}Speichern</button></div>
      <div class="card" id="consCheck"></div></div>`;
    bindPickers(el, ents);
    // what EnergyPilot makes of the current value – updates when the entity or the checkbox changes
    const watts = (e) => { const v = parseFloat(e.state); if (!Number.isFinite(v)) return null; return e.unit === 'kW' ? v * 1000 : e.unit === 'MW' ? v * 1e6 : v; };
    const explain = (key) => {
      const line = $(`#dir_${key}`); const id = $(`#${F[key][0]}`).value;
      const e = ents.find((x) => x.entity_id === id);
      const box = $(`#inv_${key}`);
      $(`#dirrow_${key}`).classList.toggle('hidden', !id);
      if (!e || e.kind !== 'power') { line.innerHTML = ''; return; }
      let w = watts(e);
      if (w == null) { line.innerHTML = '<span class="faint">kein aktueller Wert</span>'; return; }
      if (box.checked) w = -w;
      const a = fmtW(Math.abs(w));
      const txt = key === 'grid' ? (w > 20 ? `Netzbezug ${a}` : w < -20 ? `Einspeisung ${a}` : 'ausgeglichen')
        : key === 'battery_power' ? (w > 20 ? `Batterie lädt mit ${a}` : w < -20 ? `Batterie entlädt mit ${a}` : 'Batterie im Ruhezustand')
          : (w >= 0 ? `Hausverbrauch ${a}` : `<span class="pos">negativer Verbrauch (${fmtW(w)}) – Richtung umkehren?</span>`);
      line.innerHTML = `EnergyPilot versteht: <b>${txt}</b>`;
    };
    // badge per section: all required set / missing / optional
    const states = () => $$('.sens-sec[data-keys]', el).forEach((sec) => {
      const keys = sec.dataset.keys.split(',');
      const set = keys.filter((k) => $(`#${F[k][0]}`).value).length;
      const req = keys.some((k) => F[k][4]);
      const b = sec.querySelector('.sens-state');
      b.className = `badge sens-state ${set === keys.length ? 'ok' : req ? 'err' : ''}`;
      b.textContent = set === keys.length ? 'eingerichtet' : req ? (set ? `${set} von ${keys.length}` : 'fehlt') : (set ? `${set} von ${keys.length}` : 'optional');
    });
    const values = () => ({
      sensors: Object.fromEntries(Object.entries(F).map(([k, f]) => [k, $(`#${f[0]}`).value])),
      location: { latitude: $('#n_lat').value, longitude: $('#n_lon').value },
      invert: Object.fromEntries(Object.keys(F).filter((k) => F[k][5]).map((k) => [k, $(`#inv_${k}`).checked])),
      devices: { heater_surplus: $('#n_hsurplus').checked },
    });
    let saved = JSON.stringify(values());
    const dirty = () => {
      const d = JSON.stringify(values()) !== saved;
      $('#saveBar').classList.toggle('dirty', d);
      $('#saveMsg').textContent = d ? 'Nicht gespeichert' : 'Alles gespeichert';
      $('#n_save').disabled = !d; $('#n_reset').disabled = !d;
      states();
    };
    Object.keys(F).forEach((key) => {
      $(`#${F[key][0]}`).addEventListener('change', dirty);
      if (!F[key][5]) return;
      $(`#inv_${key}`).addEventListener('change', () => { explain(key); dirty(); });
      $(`#${F[key][0]}`).addEventListener('change', () => explain(key));
      explain(key);
    });
    ['n_lat', 'n_lon'].forEach((id) => $(`#${id}`).addEventListener('input', dirty));
    $('#n_hsurplus').addEventListener('change', dirty);
    $('#locToggle').addEventListener('click', () => { const b = $('#locBody'); b.classList.toggle('hidden'); if (!b.classList.contains('hidden')) $('#n_lat').focus(); });
    states();
    consumptionCheck($('#consCheck'));
    $('#n_reset').addEventListener('click', () => navigate());
    $('#n_save').addEventListener('click', (e) => withBusy(e.currentTarget, async () => {
      const v = values();
      if (await saveSettings(v)) { saved = JSON.stringify(v); consumptionCheck($('#consCheck')); }
    }).then(dirty));  // after withBusy re-enabled the button
  }

  function renderLook(el) {
    setHeader('Einstellungen', 'Design und Akzentfarbe');
    const draw = () => {
      const theme = store.get('theme', 'auto'); const accent = store.get('accent', 'blue');
      el.innerHTML = `<div class="card"><div class="card-head"><h2>Design</h2></div><div class="card-body">
          <div class="seg" id="lookTheme">${THEMES.map(([k, icon, label]) => `<button data-theme-set="${k}" class="${theme === k ? 'active' : ''}">${ic(icon)}${esc(label.replace('Design: ', '').replace(/^./, (c) => c.toUpperCase()))}</button>`).join('')}</div>
          <p class="faint" style="font-size:12.5px;margin:10px 0 0">„Automatisch“ folgt der Einstellung von Betriebssystem bzw. Browser.</p></div></div>
        <div class="card" style="margin-top:16px"><div class="card-head"><h2>Akzentfarbe</h2></div><div class="card-body">
          <div class="swatches">${Object.entries(ACCENTS).map(([k, a]) => `<button class="swatch ${accent === k ? 'active' : ''}" data-accent="${k}" style="--sw:${a[1]}" title="${esc(a[0])}" aria-pressed="${accent === k}"><i>${ic('check')}</i><span>${esc(a[0])}</span></button>`).join('')}</div>
          <p class="faint" style="font-size:12.5px;margin:12px 0 0">Gilt für Schaltflächen und Hervorhebungen. Die Farben der Prognosequellen bleiben gleich, damit jede Quelle überall wiedererkennbar ist.</p></div></div>`;
      $$('[data-theme-set]', el).forEach((b) => b.addEventListener('click', () => { setTheme(b.dataset.themeSet); draw(); }));
      $$('[data-accent]', el).forEach((b) => b.addEventListener('click', () => { store.set('accent', b.dataset.accent); withTransition(applyAccent); draw(); }));
    };
    draw();
  }

  const RENDER = { setup: renderSetup, costs: renderCosts, dashboard: renderDashboard, plan: renderPlan, journal: renderJournal, accuracy: renderAccuracy, day: renderDay, prices: renderPrices, settings: renderSettings };
  // -------------------------------------------------------------- UI pieces
  function toast(msg, type = 'ok') {
    const el = document.createElement('div');
    el.className = `toast ${type}`;
    el.innerHTML = `${ic(type === 'err' ? 'alert' : type === 'info' ? 'info' : 'checkCircle')}<div>${esc(msg)}</div>`;
    // the check mark draws itself
    if (type === 'ok') el.querySelectorAll('svg path').forEach((p) => p.setAttribute('pathLength', '1'));
    $('#toasts').appendChild(el);
    const hide = () => { el.classList.add('leaving'); setTimeout(() => el.remove(), reducedMotion() ? 0 : 220); };
    const t = setTimeout(hide, type === 'err' ? 7000 : 3500);
    el.addEventListener('click', () => { clearTimeout(t); hide(); });
  }

  function modal({ title, body, foot = '', wide = false, cls = '', onMount, onClose }) {
    const root = document.createElement('div');
    root.className = 'modal-back';
    root.innerHTML = `<div class="modal ${wide ? 'wide' : ''} ${cls}" role="dialog" aria-modal="true">
      <div class="modal-head"><h3>${esc(title)}</h3><button class="icon-btn" data-close aria-label="Schließen">${ic('x')}</button></div>
      <div class="modal-body">${body}</div>
      ${foot ? `<div class="modal-foot">${foot}</div>` : ''}
    </div>`;
    const close = () => {
      if (!root.isConnected || root.classList.contains('closing')) return;
      root.classList.add('closing'); document.removeEventListener('keydown', onKey);
      setTimeout(() => root.remove(), reducedMotion() ? 0 : 170);
      if (onClose) onClose();
    };
    const onKey = (e) => { if (e.key === 'Escape') close(); };
    root.addEventListener('mousedown', (e) => { if (e.target === root) close(); });
    root.addEventListener('click', (e) => { if (e.target.closest('[data-close]')) close(); });
    document.addEventListener('keydown', onKey);
    $('#modalRoot').appendChild(root);
    const m = root.querySelector('.modal');
    if (onMount) onMount(m, close);
    const first = m.querySelector('input:not([type=hidden]), select, textarea');
    if (first) first.focus();
    return close;
  }

  function confirmDialog(title, text, { ok = 'Bestätigen', danger = false } = {}) {
    return new Promise((resolve) => {
      let result = false;
      modal({
        title,
        body: `<p class="muted" style="margin:0 0 6px">${text}</p>`,
        foot: `<button class="btn" data-close>Abbrechen</button><button class="btn ${danger ? 'danger solid' : 'primary'}" data-ok>${esc(ok)}</button>`,
        onMount(m, closeFn) {
          m.querySelector('[data-ok]').addEventListener('click', () => { result = true; closeFn(); });
          m.querySelector('[data-ok]').focus();
        },
        onClose: () => resolve(result),
      });
    });
  }

  async function withBusy(btn, fn) {
    const old = btn ? btn.innerHTML : '';
    if (btn) { btn.disabled = true; const svg = btn.querySelector('svg'); if (svg) svg.classList.add('spin'); }
    try { return await fn(); } finally { if (btn && document.body.contains(btn)) { btn.disabled = false; btn.innerHTML = old; } }
  }

  const sw = (checked, attrs = '', disabled = false) => `<label class="switch"><input type="checkbox" ${checked ? 'checked' : ''} ${disabled ? 'disabled' : ''} ${attrs}><span></span></label>`;
  const empty = (icon, title, text, action = '') => `<div class="empty"><div class="avatar accent">${ic(icon)}</div><h3>${esc(title)}</h3><p>${text}</p>${action}</div>`;
  const errorBox = (msg) => `<div class="notice err">${ic('alert')}<div>${esc(msg)}</div></div>`;
  const loading = (rows = 4) => `<div class="card"><div class="card-body">${Array.from({ length: rows }, () => '<div class="skeleton" style="height:18px;margin:10px 0"></div>').join('')}</div></div>`;
  // ------------------------------------------------------------------ theme
  const THEMES = [['auto', 'contrast', 'Design: automatisch'], ['light', 'sun', 'Design: hell'], ['dark', 'moon', 'Design: dunkel']];
  function applyTheme(t) {
    if (t === 'auto') document.documentElement.removeAttribute('data-theme'); else document.documentElement.setAttribute('data-theme', t);
    const def = THEMES.find((x) => x[0] === t);
    $('#themeToggle').innerHTML = `${ic(def[1])}<span>${def[2]}</span>`;
    applyAccent();
  }
  // smooth cross-fade between old and new look where the browser supports it
  function withTransition(fn) {
    if (document.startViewTransition && !reducedMotion()) document.startViewTransition(fn); else fn();
  }
  function setTheme(t) {
    store.set('theme', t);
    withTransition(() => applyTheme(t));
  }

  // name, light accent, light hover, dark accent, dark hover
  const ACCENTS = {
    blue: ['Blau', '#2563eb', '#1d4ed8', '#5b8cff', '#7aa2ff'],
    teal: ['Türkis', '#0d9488', '#0f766e', '#2dd4bf', '#5eead4'],
    green: ['Grün', '#16a34a', '#15803d', '#4ade80', '#86efac'],
    violet: ['Violett', '#7c3aed', '#6d28d9', '#a78bfa', '#c4b5fd'],
    orange: ['Orange', '#ea580c', '#c2410c', '#fb923c', '#fdba74'],
    pink: ['Pink', '#db2777', '#be185d', '#f472b6', '#f9a8d4'],
  };
  const isDark = () => {
    const t = document.documentElement.getAttribute('data-theme');
    return t ? t === 'dark' : window.matchMedia('(prefers-color-scheme: dark)').matches;
  };
  function applyAccent() {
    const name = store.get('accent', 'blue');
    const st = document.documentElement.style;
    const a = ACCENTS[name];
    if (!a || name === 'blue') { ['--accent', '--accent-2', '--accent-soft'].forEach((v) => st.removeProperty(v)); return; }
    const dark = isDark();
    const c = dark ? a[3] : a[1];
    st.setProperty('--accent', c);
    st.setProperty('--accent-2', dark ? a[4] : a[2]);
    st.setProperty('--accent-soft', `color-mix(in srgb, ${c} ${dark ? 16 : 11}%, transparent)`);
  }


  // ------------------------------------------------------------------- boot
  function boot() {
    const forced = new URLSearchParams(location.search).get('theme');
    applyTheme(THEMES.some((x) => x[0] === forced) ? forced : store.get('theme', 'auto'));
    $('#themeToggle').addEventListener('click', () => {
      const cur = document.documentElement.getAttribute('data-theme') || 'auto';
      const i = THEMES.findIndex((x) => x[0] === cur);
      const next = THEMES[(i + 1) % THEMES.length][0];
      setTheme(next);
      $$('[data-theme-set]').forEach((b) => b.classList.toggle('active', b.dataset.themeSet === next));
    });
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', applyAccent);
    watchPageIn();
    $('#menuBtn').innerHTML = ic('menu');
    $('#feedbackLink').innerHTML = `${ic('message')}<span>Feedback &amp; Fehler melden</span>`;
    $('#menuBtn').addEventListener('click', () => $('#app').classList.toggle('nav-open'));
    $('#scrim').addEventListener('click', () => $('#app').classList.remove('nav-open'));
    window.addEventListener('scroll', () => $('.topbar').classList.toggle('scrolled', window.scrollY > 4), { passive: true });
    window.addEventListener('hashchange', navigate);
    loadCheck().catch(() => {});
    setInterval(() => { if (!document.hidden) loadCheck(true).catch(() => {}); }, 10 * 60000);
    document.addEventListener('click', (e) => {
      if (!e.target.closest('[data-legend-more]')) return;
      store.set('legendAll', !store.get('legendAll', false));
      navigate();
    });
    navigate();
  }
  boot();
})();
