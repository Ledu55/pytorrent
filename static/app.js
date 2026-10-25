'use strict';

// ── State ─────────────────────────────────────────────────────────────────
const statuses = new Map();   // info_hash -> last status object
const rows = new Map();       // info_hash -> { tr, cells }
const ui = {
  filter: 'all',
  search: '',
  sortKey: 'added_time',
  sortDir: -1,
  selected: null,
  tab: 'general',
  details: null,             // last /details payload for the selected torrent
  config: { download_root: '', free_space: null },
  renderQueued: false,
  order: [],
};

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

// ── Formatting ────────────────────────────────────────────────────────────
function fmtBytes(b) {
  if (b == null || b < 0) return '—';
  if (b === 0) return '0 B';
  const units = ['B', 'KiB', 'MiB', 'GiB', 'TiB'];
  const i = Math.min(Math.floor(Math.log(b) / Math.log(1024)), units.length - 1);
  const v = b / 1024 ** i;
  return `${v >= 100 || i === 0 ? v.toFixed(0) : v.toFixed(1)} ${units[i]}`;
}
const fmtRate = (bps) => (bps > 0 ? `${fmtBytes(bps)}/s` : '—');

function fmtEta(s) {
  if (s == null || s < 0) return '∞';
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60), h = Math.floor(m / 60), d = Math.floor(h / 24);
  if (d > 0) return `${d}d ${h % 24}h`;
  if (h > 0) return `${h}h ${m % 60}m`;
  return `${m}m ${s % 60}s`;
}

function fmtDate(ts) {
  if (!ts) return '—';
  const d = new Date(ts * 1000);
  const today = new Date();
  return d.toDateString() === today.toDateString()
    ? d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
    : d.toLocaleDateString();
}

function escHtml(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

// ── Torrent classification ────────────────────────────────────────────────
function group(t) {
  if (t.error) return 'error';
  switch (t.state) {
    case 'paused': return 'paused';
    case 'seeding': return 'seeding';
    case 'finished': return 'completed';
    case 'checking':
    case 'checking resume': return 'checking';
    case 'queued': return t.progress >= 1 ? 'seeding' : 'downloading';
    default: return 'downloading';
  }
}

const STATE_LABELS = {
  'downloading metadata': 'Fetching metadata',
  'checking resume': 'Checking',
  finished: 'Completed',
};
function stateLabel(t) {
  if (t.error) return 'Error';
  const label = STATE_LABELS[t.state] || t.state;
  return label.charAt(0).toUpperCase() + label.slice(1);
}

const isPaused = (t) => t.state === 'paused';

function matchesFilter(t) {
  const g = group(t);
  switch (ui.filter) {
    case 'downloading': return g === 'downloading' || g === 'checking';
    case 'seeding': return g === 'seeding';
    case 'completed': return t.progress >= 1;
    case 'paused': return g === 'paused';
    case 'error': return g === 'error';
    default: return true;
  }
}

function matchesSearch(t) {
  return !ui.search || (t.name || '').toLowerCase().includes(ui.search);
}

// ── Icons ─────────────────────────────────────────────────────────────────
const ICONS = {
  pause: '<path d="M8 5v14M16 5v14"/>',
  play: '<path d="M7 5v14l11-7z"/>',
  folder: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
  trash: '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3"/>',
};
const icon = (name) => `<svg aria-hidden="true" viewBox="0 0 24 24">${ICONS[name]}</svg>`;

// ── Table rendering ───────────────────────────────────────────────────────
function createRow(hash) {
  const tr = document.createElement('tr');
  tr.dataset.hash = hash;
  tr.tabIndex = -1;
  tr.innerHTML = `
    <td class="name"><span class="title"></span></td>
    <td class="num hide-sm" data-k="size"></td>
    <td class="progress-cell"><div class="progress"><div class="bar"><i></i></div><span class="pct"></span></div></td>
    <td data-k="state"><span class="badge"></span></td>
    <td class="num" data-k="down" data-label="↓"></td>
    <td class="num" data-k="up" data-label="↑"></td>
    <td class="num" data-k="eta" data-label="ETA"></td>
    <td class="num hide-sm" data-k="peers"></td>
    <td class="num hide-sm" data-k="ratio"></td>
    <td class="num hide-sm" data-k="added"></td>
    <td class="actions-cell"><div class="actions">
      <button class="icon-btn" data-act="toggle"></button>
      <button class="icon-btn" data-act="open" title="Open folder" aria-label="Open folder">${icon('folder')}</button>
      <button class="icon-btn" data-act="remove" title="Remove" aria-label="Remove">${icon('trash')}</button>
    </div></td>`;
  const cells = {
    title: $('.title', tr),
    bar: $('.bar > i', tr),
    pct: $('.pct', tr),
    badge: $('.badge', tr),
    toggle: $('[data-act="toggle"]', tr),
  };
  for (const td of $$('td[data-k]', tr)) cells[td.dataset.k] = td;
  const entry = { tr, cells, paused: null };
  rows.set(hash, entry);
  return entry;
}

function setText(el, text) {
  if (el.textContent !== text) el.textContent = text;
}

function updateRow(entry, t) {
  const { tr, cells } = entry;
  const g = group(t);
  if (tr.dataset.group !== g) tr.dataset.group = g;

  const name = t.name || 'Fetching metadata…';
  setText(cells.title, name);
  cells.title.title = `${name}\n${t.save_path}`;
  setText(cells.size, t.total_size ? fmtBytes(t.total_size) : '—');

  const pct = (t.progress * 100).toFixed(1);
  cells.bar.style.width = `${pct}%`;
  setText(cells.pct, `${pct}%`);

  setText(cells.badge, stateLabel(t));
  cells.badge.className = `badge ${g}`;
  cells.badge.title = t.error || '';

  setText(cells.down, fmtRate(t.download_rate));
  setText(cells.up, fmtRate(t.upload_rate));
  setText(cells.eta, g === 'downloading' && !isPaused(t) ? fmtEta(t.eta) : '—');
  setText(cells.peers, `${t.num_seeds} / ${t.num_peers}`);
  setText(cells.ratio, t.ratio.toFixed(2));
  setText(cells.added, fmtDate(t.added_time));

  const paused = isPaused(t);
  if (entry.paused !== paused) {
    entry.paused = paused;
    cells.toggle.innerHTML = icon(paused ? 'play' : 'pause');
    const label = paused ? 'Resume' : 'Pause';
    cells.toggle.title = label;
    cells.toggle.setAttribute('aria-label', `${label} ${name}`);
  }
  tr.setAttribute('aria-selected', String(ui.selected === t.info_hash));
  tr.classList.toggle('selected', ui.selected === t.info_hash);
}

function compare(a, b) {
  const k = ui.sortKey;
  let x = a[k], y = b[k];
  if (k === 'name') { x = (x || '').toLowerCase(); y = (y || '').toLowerCase(); }
  if (k === 'state') { x = stateLabel(a); y = stateLabel(b); }
  if (k === 'eta') { x = x < 0 ? Infinity : x; y = y < 0 ? Infinity : y; }
  if (x < y) return -ui.sortDir;
  if (x > y) return ui.sortDir;
  return 0;
}

function scheduleRender() {
  if (ui.renderQueued) return;
  ui.renderQueued = true;
  requestAnimationFrame(() => { ui.renderQueued = false; render(); });
}

function render() {
  const body = $('#torrent-body');
  const visible = [...statuses.values()].filter((t) => matchesFilter(t) && matchesSearch(t));
  visible.sort(compare);

  for (const t of statuses.values()) {
    const entry = rows.get(t.info_hash) || createRow(t.info_hash);
    updateRow(entry, t);
  }

  // Only touch DOM order when it actually changed, so hover and focus survive
  const order = visible.map((t) => t.info_hash);
  if (order.join() !== ui.order.join()) {
    ui.order = order;
    const frag = document.createDocumentFragment();
    for (const h of order) frag.appendChild(rows.get(h).tr);
    body.replaceChildren(frag);
  }

  const total = statuses.size;
  $('#empty-state').hidden = total > 0;
  $('#no-match').hidden = total === 0 || visible.length > 0;
  $('#torrent-table').hidden = total === 0;

  renderCounts();
  renderStatusBar();
  if (ui.selected && ui.tab === 'general') renderDetails();
}

function renderCounts() {
  const all = [...statuses.values()];
  const saved = ui.filter;
  for (const btn of $$('#filters button')) {
    ui.filter = btn.dataset.filter;
    const n = all.filter(matchesFilter).length;
    setText($('.count', btn), n ? String(n) : '');
  }
  ui.filter = saved;
}

function renderStatusBar() {
  let down = 0, up = 0;
  for (const t of statuses.values()) { down += t.download_rate; up += t.upload_rate; }
  setText($('#sb-down'), `↓ ${fmtRate(down)}`);
  setText($('#sb-up'), `↑ ${fmtRate(up)}`);
  document.title = down || up
    ? `↓ ${fmtRate(down)} ↑ ${fmtRate(up)} — PyTorrent`
    : 'PyTorrent';
}

// ── Updates & notifications ───────────────────────────────────────────────
function applyUpdate(t) {
  const prev = statuses.get(t.info_hash);
  statuses.set(t.info_hash, t);
  if (prev && prev.progress < 1 && t.progress >= 1 && t.total_size > 0) {
    notifyDone(t);
  }
}

function notifyDone(t) {
  toast(`Finished downloading “${t.name}”`, 'ok', {
    label: 'Open folder', run: () => act('open', t.info_hash),
  });
  if ('Notification' in window && Notification.permission === 'granted' && document.hidden) {
    try { new Notification('Download complete', { body: t.name, icon: 'favicon.svg' }); } catch { /* ignore */ }
  }
}

function askNotificationPermission() {
  if ('Notification' in window && Notification.permission === 'default') {
    Notification.requestPermission().catch(() => {});
  }
}

function connectSSE() {
  const es = new EventSource('/api/events');
  let snapshot = true;   // first frame after (re)connect is the full list

  es.onopen = () => {
    snapshot = true;
    $('#conn-dot').className = 'dot ok';
    $('#conn-label').textContent = 'Connected';
  };

  es.onmessage = (e) => {
    const updates = JSON.parse(e.data);
    if (snapshot) {
      snapshot = false;
      const present = new Set(updates.map((t) => t.info_hash));
      for (const h of [...statuses.keys()]) if (!present.has(h)) dropTorrent(h);
    }
    updates.forEach(applyUpdate);
    scheduleRender();
  };

  es.onerror = () => {
    $('#conn-dot').className = 'dot bad';
    $('#conn-label').textContent = 'Disconnected — retrying…';
    // EventSource reconnects automatically; no manual retry needed
  };
}

function dropTorrent(hash) {
  statuses.delete(hash);
  rows.get(hash)?.tr.remove();
  rows.delete(hash);
  ui.order = ui.order.filter((h) => h !== hash);
  if (ui.selected === hash) closeDetails();
}

// ── API helpers ───────────────────────────────────────────────────────────
async function api(path, opts = {}) {
  let res;
  try {
    res = await fetch(path, opts);
  } catch {
    throw new Error("Can't reach PyTorrent. Is it still running?");
  }
  let data = null;
  try { data = await res.json(); } catch { /* empty body */ }
  if (!res.ok) {
    const detail = data && data.detail;
    throw new Error(typeof detail === 'string' ? detail : `Request failed (${res.status})`);
  }
  return data;
}

const postJSON = (path, body, method = 'POST') => api(path, {
  method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
});

// ── Toasts ────────────────────────────────────────────────────────────────
function toast(message, kind = 'info', action = null) {
  const el = document.createElement('div');
  el.className = `toast ${kind}`;
  el.setAttribute('role', kind === 'error' ? 'alert' : 'status');
  el.innerHTML = `<p>${escHtml(message)}</p>`;
  if (action) {
    const b = document.createElement('button');
    b.textContent = action.label;
    b.onclick = () => { action.run(); el.remove(); };
    el.appendChild(b);
  }
  $('#toasts').appendChild(el);
  setTimeout(() => el.remove(), kind === 'error' ? 8000 : 5000);
}

// ── Torrent actions ───────────────────────────────────────────────────────
async function act(action, hash) {
  const t = statuses.get(hash);
  if (!t) return;
  if (action === 'remove') return openRemove(hash);
  if (action === 'toggle') action = isPaused(t) ? 'resume' : 'pause';
  try {
    await api(`/api/torrents/${hash}/${action}`, { method: 'POST' });
    if (action === 'recheck') toast(`Rechecking “${t.name}”`);
    if (action === 'reannounce') toast('Asked trackers for more peers');
  } catch (err) {
    toast(err.message, 'error');
  }
}

let removeHash = null;
function openRemove(hash) {
  removeHash = hash;
  $('#remove-name').textContent = statuses.get(hash)?.name || hash;
  $('#remove-files').checked = false;
  $('#remove-dialog').showModal();
}

$('#remove-form').addEventListener('submit', async () => {
  const hash = removeHash;
  const deleteFiles = $('#remove-files').checked;
  const name = statuses.get(hash)?.name || 'torrent';
  try {
    await api(`/api/torrents/${hash}?delete_files=${deleteFiles}`, { method: 'DELETE' });
    dropTorrent(hash);
    scheduleRender();
    toast(deleteFiles ? `Removed “${name}” and deleted its files` : `Removed “${name}” (files kept)`, 'ok');
  } catch (err) {
    toast(`Couldn't remove “${name}”: ${err.message}`, 'error');
  }
});

// ── Adding torrents ───────────────────────────────────────────────────────
async function addFiles(files, subfolder = '') {
  for (const f of files) {
    if (!f.name.toLowerCase().endsWith('.torrent')) {
      toast(`Skipped “${f.name}” — only .torrent files can be added`, 'error');
      continue;
    }
    const fd = new FormData();
    // DO NOT set Content-Type manually — browser must set it to include the boundary
    fd.append('file', f);
    if (subfolder) fd.append('save_path', subfolder);
    try {
      await api('/api/torrents', { method: 'POST', body: fd });
      toast(`Added “${f.name.replace(/\.torrent$/i, '')}”`, 'ok');
    } catch (err) {
      toast(err.message, 'error');
    }
  }
}

async function addMagnets(links, subfolder = '') {
  for (const uri of links) {
    try {
      await postJSON('/api/torrents/magnet', { uri, save_path: subfolder || null });
      toast('Magnet added — fetching metadata…', 'ok');
    } catch (err) {
      toast(err.message, 'error');
    }
  }
}

const parseMagnets = (text) => text.split(/\s+/).filter((s) => /^magnet:\?/i.test(s));

function openAdd() {
  askNotificationPermission();
  $('#add-form').reset();
  $('#add-files-label').innerHTML = 'Choose <strong>.torrent</strong> files or drop them here';
  $('#add-root').textContent = ui.config.download_root || 'your download folder';
  $('#add-dialog').showModal();
}

$('#add-files').addEventListener('change', (e) => {
  const n = e.target.files.length;
  $('#add-files-label').textContent = n
    ? (n === 1 ? e.target.files[0].name : `${n} files selected`)
    : 'Choose .torrent files or drop them here';
});

$('#add-form').addEventListener('submit', (e) => {
  const files = [...$('#add-files').files];
  const magnets = parseMagnets($('#add-magnets').value);
  if (!files.length && !magnets.length) {
    e.preventDefault();
    toast('Choose a .torrent file or paste a magnet link first', 'error');
    return;
  }
  const sub = $('#add-subfolder').value.trim();
  addFiles(files, sub);
  addMagnets(magnets, sub);
});

// Dropping onto the dialog's zone fills the file input instead of adding right away
const dz = $('#add-dropzone');
dz.addEventListener('dragover', (e) => { e.preventDefault(); e.stopPropagation(); dz.classList.add('over'); });
dz.addEventListener('dragleave', () => dz.classList.remove('over'));
dz.addEventListener('drop', (e) => {
  e.preventDefault(); e.stopPropagation(); dz.classList.remove('over');
  if (e.dataTransfer.files.length) {
    $('#add-files').files = e.dataTransfer.files;
    $('#add-files').dispatchEvent(new Event('change'));
  }
});

// Whole-window drag & drop
let dragDepth = 0;
const overlay = $('#drop-overlay');
window.addEventListener('dragenter', (e) => {
  if ($('#add-dialog').open) return;
  e.preventDefault(); dragDepth++; overlay.hidden = false;
});
window.addEventListener('dragleave', () => { if (--dragDepth <= 0) { dragDepth = 0; overlay.hidden = true; } });
window.addEventListener('dragover', (e) => e.preventDefault());
window.addEventListener('drop', (e) => {
  e.preventDefault(); dragDepth = 0; overlay.hidden = true;
  if ($('#add-dialog').open) return;
  askNotificationPermission();
  const files = [...e.dataTransfer.files];
  if (files.length) return addFiles(files);
  const text = e.dataTransfer.getData('text/uri-list') || e.dataTransfer.getData('text/plain');
  const magnets = parseMagnets(text || '');
  if (magnets.length) addMagnets(magnets);
  else toast('Drop .torrent files or a magnet link', 'error');
});

// Paste a magnet link anywhere outside a text field
document.addEventListener('paste', (e) => {
  if (e.target.closest('input, textarea') || $('dialog[open]')) return;
  const magnets = parseMagnets(e.clipboardData.getData('text'));
  if (magnets.length) { e.preventDefault(); addMagnets(magnets); }
});

// ── Details panel ─────────────────────────────────────────────────────────
let detailsTimer = null;

function select(hash, { focus = false } = {}) {
  ui.selected = hash;
  ui.details = null;
  for (const [h, { tr }] of rows) {
    tr.classList.toggle('selected', h === hash);
    tr.setAttribute('aria-selected', String(h === hash));
  }
  if (!hash) return closeDetails();
  if (focus) rows.get(hash)?.tr.focus();
  $('#details').hidden = false;
  renderDetails();
  refreshDetails();
  clearInterval(detailsTimer);
  detailsTimer = setInterval(refreshDetails, 2000);
}

function closeDetails() {
  ui.selected = null;
  ui.details = null;
  clearInterval(detailsTimer);
  $('#details').hidden = true;
  for (const { tr } of rows.values()) tr.classList.remove('selected');
}

async function refreshDetails() {
  const hash = ui.selected;
  if (!hash || ui.tab === 'general') return;
  try {
    const d = await api(`/api/torrents/${hash}/details`);
    if (hash !== ui.selected) return;
    ui.details = d;
    // Don't yank a <select> out from under the user mid-interaction
    const active = document.activeElement;
    if (active && $('#details-body').contains(active) && active.matches('select, input')) return;
    renderDetails();
  } catch { /* torrent may have just been removed */ }
}

function renderDetails() {
  const t = statuses.get(ui.selected);
  const body = $('#details-body');
  if (!t) return;
  const d = ui.details;
  const loading = '<p class="muted">Loading…</p>';

  if (ui.tab === 'general') {
    const html = `
      <dl class="kv">
        <dt>Name</dt><dd>${escHtml(t.name || '—')}</dd>
        <dt>Status</dt><dd>${escHtml(stateLabel(t))}${t.error ? ` — ${escHtml(t.error)}` : ''}</dd>
        <dt>Saved to</dt><dd>${escHtml(t.save_path)}</dd>
        <dt>Size</dt><dd>${fmtBytes(t.downloaded)} of ${fmtBytes(t.total_size)} (${(t.progress * 100).toFixed(1)}%)</dd>
        <dt>Uploaded</dt><dd>${fmtBytes(t.uploaded)} · ratio ${t.ratio.toFixed(2)}</dd>
        <dt>Peers</dt><dd>${t.num_seeds} seeds, ${t.num_peers} peers connected</dd>
        <dt>Added</dt><dd>${t.added_time ? new Date(t.added_time * 1000).toLocaleString() : '—'}</dd>
        <dt>Info hash</dt><dd><code>${escHtml(t.info_hash)}</code></dd>
      </dl>
      <div class="row-actions">
        <button class="btn small" data-act="toggle">${isPaused(t) ? 'Resume' : 'Pause'}</button>
        <button class="btn small" data-act="open">Open folder</button>
        <button class="btn small" data-act="recheck">Verify files</button>
        <button class="btn small" data-act="reannounce">Find more peers</button>
        <button class="btn small" data-act="remove">Remove…</button>
      </div>`;
    if (body.dataset.html !== html) { body.innerHTML = html; body.dataset.html = html; }
    return;
  }
  body.dataset.html = '';

  if (!d) { body.innerHTML = loading; return; }

  if (ui.tab === 'files') {
    if (!d.files.length) { body.innerHTML = '<p class="muted">The file list appears once metadata has been downloaded.</p>'; return; }
    body.innerHTML = `<table><thead><tr><th>Download</th><th>File</th><th class="num">Size</th><th>Progress</th><th>Priority</th></tr></thead><tbody>${
      d.files.map((f) => `<tr>
        <td><input type="checkbox" data-file="${f.index}" ${f.priority > 0 ? 'checked' : ''} aria-label="Download ${escHtml(f.path)}"></td>
        <td class="path" title="${escHtml(f.path)}">${escHtml(f.path)}</td>
        <td class="num">${fmtBytes(f.size)}</td>
        <td><div class="progress"><div class="bar"><i style="width:${(f.progress * 100).toFixed(1)}%"></i></div><span class="pct">${(f.progress * 100).toFixed(0)}%</span></div></td>
        <td><select data-prio="${f.index}" ${f.priority === 0 ? 'disabled' : ''} aria-label="Priority">
          <option value="4" ${f.priority > 0 && f.priority < 7 ? 'selected' : ''}>Normal</option>
          <option value="7" ${f.priority === 7 ? 'selected' : ''}>High</option>
        </select></td></tr>`).join('')
    }</tbody></table>`;
  } else if (ui.tab === 'peers') {
    body.innerHTML = d.peers.length
      ? `<table><thead><tr><th>Address</th><th>Client</th><th class="num">Progress</th><th class="num">Down</th><th class="num">Up</th></tr></thead><tbody>${
        d.peers.map((p) => `<tr><td>${escHtml(p.address)}</td><td>${escHtml(p.client || '—')}</td>
          <td class="num">${(p.progress * 100).toFixed(0)}%</td><td class="num">${fmtRate(p.download_rate)}</td><td class="num">${fmtRate(p.upload_rate)}</td></tr>`).join('')
      }</tbody></table>`
      : '<p class="muted">No peers connected right now.</p>';
  } else if (ui.tab === 'trackers') {
    body.innerHTML = d.trackers.length
      ? `<table><thead><tr><th>Tier</th><th>URL</th><th>Message</th></tr></thead><tbody>${
        d.trackers.map((tr) => `<tr><td>${tr.tier}</td><td class="path">${escHtml(tr.url)}</td><td>${escHtml(tr.message || '—')}</td></tr>`).join('')
      }</tbody></table>`
      : '<p class="muted">No trackers — this torrent relies on DHT to find peers.</p>';
  }
}

$('#details-body').addEventListener('click', (e) => {
  const b = e.target.closest('[data-act]');
  if (b && ui.selected) act(b.dataset.act, ui.selected);
});

$('#details-body').addEventListener('change', async (e) => {
  const hash = ui.selected;
  let prio = null, index = null;
  if (e.target.dataset.file != null) {
    index = e.target.dataset.file;
    prio = e.target.checked ? 4 : 0;
  } else if (e.target.dataset.prio != null) {
    index = e.target.dataset.prio;
    prio = Number(e.target.value);
  } else return;
  try {
    await postJSON(`/api/torrents/${hash}/files`, { [index]: prio }, 'PUT');
    e.target.blur();
    setTimeout(refreshDetails, 300);
  } catch (err) {
    toast(err.message, 'error');
  }
});

for (const tab of $$('.tabs [role="tab"]')) {
  tab.addEventListener('click', () => {
    ui.tab = tab.dataset.tab;
    for (const t of $$('.tabs [role="tab"]')) t.setAttribute('aria-selected', String(t === tab));
    ui.details = null;
    renderDetails();
    refreshDetails();
  });
}
$('#details-close').addEventListener('click', closeDetails);

// ── Table interaction ─────────────────────────────────────────────────────
$('#torrent-body').addEventListener('click', (e) => {
  const tr = e.target.closest('tr');
  if (!tr) return;
  const b = e.target.closest('[data-act]');
  if (b) { e.stopPropagation(); act(b.dataset.act, tr.dataset.hash); return; }
  select(ui.selected === tr.dataset.hash ? null : tr.dataset.hash);
});

$('#torrent-body').addEventListener('dblclick', (e) => {
  const tr = e.target.closest('tr');
  if (tr && !e.target.closest('[data-act]')) act('open', tr.dataset.hash);
});

for (const th of $$('th[data-sort]')) {
  th.tabIndex = 0;
  const sort = () => {
    const k = th.dataset.sort;
    if (ui.sortKey === k) ui.sortDir *= -1;
    else { ui.sortKey = k; ui.sortDir = k === 'name' ? 1 : -1; }
    for (const h of $$('th[data-sort]')) {
      h.classList.toggle('sorted', h === th);
      h.classList.toggle('desc', h === th && ui.sortDir < 0);
      h.removeAttribute('aria-sort');
    }
    th.setAttribute('aria-sort', ui.sortDir > 0 ? 'ascending' : 'descending');
    ui.order = [];
    render();
  };
  th.addEventListener('click', sort);
  th.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); sort(); } });
}

for (const btn of $$('#filters button')) {
  btn.addEventListener('click', () => {
    ui.filter = btn.dataset.filter;
    for (const b of $$('#filters button')) {
      b.classList.toggle('active', b === btn);
      b.setAttribute('aria-pressed', String(b === btn));
    }
    render();
  });
}

$('#search').addEventListener('input', (e) => {
  ui.search = e.target.value.trim().toLowerCase();
  render();
});

// ── Toolbar ───────────────────────────────────────────────────────────────
$('#add-btn').addEventListener('click', openAdd);
$('#empty-add-btn').addEventListener('click', openAdd);
$('#pause-all-btn').addEventListener('click', () =>
  api('/api/torrents/pause-all', { method: 'POST' }).then(() => toast('Paused all torrents')).catch((e) => toast(e.message, 'error')));
$('#resume-all-btn').addEventListener('click', () =>
  api('/api/torrents/resume-all', { method: 'POST' }).then(() => toast('Resumed all torrents')).catch((e) => toast(e.message, 'error')));

for (const b of $$('dialog [data-close]')) b.addEventListener('click', () => b.closest('dialog').close());

// ── Theme ─────────────────────────────────────────────────────────────────
function storedTheme() {
  try { return localStorage.getItem('theme'); } catch { return null; }
}
function applyTheme(theme) {
  if (theme) document.documentElement.dataset.theme = theme;
  else delete document.documentElement.dataset.theme;
}
applyTheme(storedTheme());
$('#theme-btn').addEventListener('click', () => {
  const current = document.documentElement.dataset.theme
    || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
  const next = current === 'dark' ? 'light' : 'dark';
  applyTheme(next);
  try { localStorage.setItem('theme', next); } catch { /* private mode */ }
});

// ── Settings ──────────────────────────────────────────────────────────────
$('#settings-btn').addEventListener('click', async () => {
  try {
    const s = await api('/api/settings');
    const form = $('#settings-form');
    for (const [k, v] of Object.entries(s)) {
      const input = form.elements[k];
      if (!input) continue;
      if (input.type === 'checkbox') input.checked = !!v; else input.value = v;
    }
    $('#settings-dialog').showModal();
  } catch (err) {
    toast(err.message, 'error');
  }
});

$('#settings-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const form = e.target;
  const payload = {};
  for (const el of form.elements) {
    if (!el.name) continue;
    payload[el.name] = el.type === 'checkbox' ? el.checked
      : el.type === 'number' ? Number(el.value) : el.value;
  }
  try {
    await postJSON('/api/settings', payload, 'PUT');
    $('#settings-dialog').close();
    toast('Settings saved', 'ok');
    loadConfig();
    setTimeout(loadSession, 1500);
  } catch (err) {
    toast(err.message, 'error');
  }
});

// ── Keyboard shortcuts ────────────────────────────────────────────────────
document.addEventListener('keydown', (e) => {
  if ($('dialog[open]')) return;
  const typing = e.target.closest('input, textarea, select');
  if (e.key === 'Escape') {
    if (typing) { e.target.blur(); return; }
    if (ui.selected) closeDetails();
    return;
  }
  if (typing || e.ctrlKey || e.metaKey || e.altKey) return;

  if (e.key === '/') { e.preventDefault(); $('#search').focus(); return; }
  if (e.key === 'n' || e.key === 'N') { e.preventDefault(); openAdd(); return; }

  if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
    if (!ui.order.length) return;
    e.preventDefault();
    const i = ui.order.indexOf(ui.selected);
    const next = e.key === 'ArrowDown'
      ? Math.min(i + 1, ui.order.length - 1)
      : Math.max(i < 0 ? 0 : i - 1, 0);
    select(ui.order[next], { focus: true });
    return;
  }
  if (!ui.selected) return;
  if (e.key === ' ' && !e.target.closest('button')) { e.preventDefault(); act('toggle', ui.selected); }
  if (e.key === 'Delete' || e.key === 'Backspace') { e.preventDefault(); openRemove(ui.selected); }
});

// ── Periodic info ─────────────────────────────────────────────────────────
async function loadConfig() {
  try {
    ui.config = await api('/api/config');
    const free = ui.config.free_space;
    const el = $('#sb-free');
    el.textContent = free == null ? '' : `${fmtBytes(free)} free`;
    el.classList.toggle('warn-text', free != null && free < 2 * 1024 ** 3);
  } catch { /* status bar just stays stale */ }
}

async function loadSession() {
  try {
    const s = await api('/api/session');
    const el = $('#sb-net');
    if (s.listening) {
      el.textContent = `Port ${s.listen_port} · ${s.dht_nodes} DHT nodes`;
      el.classList.remove('warn-text');
    } else {
      el.textContent = 'Not listening for peers — check the port in Settings';
      el.classList.add('warn-text');
    }
  } catch { /* ignore */ }
}

loadConfig();
loadSession();
setInterval(loadConfig, 30000);
setInterval(loadSession, 10000);
connectSSE();
