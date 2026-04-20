import { api, wsLogs, wsStats } from './api.js';
import { icon, typeIcon, badge, toast, confirm, spinner, fmtUptime, fmtSize, fmtDate, logClass, setBtn } from './utils.js';

const params = new URLSearchParams(location.search);
const APP_ID = parseInt(params.get('id'));

let app = null;
let logWs  = null;
let statWs = null;
let logLines = [];
let chartCpu = null;
let chartMem = null;
let cpuData = [];
let memData = [];

/* ─── Init ──────────────────────────────────────────────────────────────── */
export async function initApp() {
  if (!APP_ID || isNaN(APP_ID)) {
    window.location.href = '/';
    return;
  }

  try {
    app = await api.getApp(APP_ID);
  } catch (err) {
    document.body.innerHTML = `
      <div style="display:flex;align-items:center;justify-content:center;height:100vh;flex-direction:column;gap:12px;color:#8b949e">
        <div style="font-size:18px;color:#f85149">Failed to load application</div>
        <div style="font-size:13px">${err.message}</div>
        <a href="/" style="color:#58a6ff;font-size:13px;margin-top:8px">← Back to dashboard</a>
      </div>`;
    return;
  }

  renderHeader();
  initTabs();
  setInterval(refreshApp, 6000);
}

async function refreshApp() {
  try {
    app = await api.getApp(APP_ID);
    updateHeaderStatus();
  } catch {}
}

/* ─── Header ────────────────────────────────────────────────────────────── */
function renderHeader() {
  document.getElementById('app-name').textContent = app.name;
  document.getElementById('app-name-crumb').textContent = app.name;
  document.title = `${app.name} — PDManager`;
  document.getElementById('app-meta').textContent =
    `${app.app_type || 'unknown'} · Port ${app.port || 'N/A'}`;
  updateHeaderStatus();

  document.getElementById('btn-start').addEventListener('click',   () => quickAction('start'));
  document.getElementById('btn-stop').addEventListener('click',    () => quickAction('stop'));
  document.getElementById('btn-restart').addEventListener('click', () => quickAction('restart'));
}

function updateHeaderStatus() {
  document.getElementById('app-badge').innerHTML = badge(app.status);

  const s = app.status;
  const busy = (s === 'deploying');

  const btnStart   = document.getElementById('btn-start');
  const btnStop    = document.getElementById('btn-stop');
  const btnRestart = document.getElementById('btn-restart');

  btnStart.disabled   = (s === 'running') || busy;
  btnStop.disabled    = (s === 'stopped') || busy;
  btnRestart.disabled = busy;

  // Visual: dim the non-applicable button slightly
  btnStart.style.opacity   = (s === 'running') ? '0.4' : '1';
  btnStop.style.opacity    = (s === 'stopped') ? '0.4' : '1';
}

async function quickAction(action) {
  const btn = document.getElementById(`btn-${action}`);
  const prev = btn.innerHTML;
  const transitional = action === 'start' ? 'starting' : action === 'stop' ? 'stopping' : 'restarting';
  const labels = { start: 'Starting…', stop: 'Stopping…', restart: 'Restarting…' };

  // Lock all three buttons and show transitional badge
  ['start','stop','restart'].forEach(a => {
    const b = document.getElementById(`btn-${a}`);
    b.disabled = true;
    b.style.opacity = a === action ? '1' : '0.4';
  });
  btn.innerHTML = `${spinner} ${labels[action]}`;
  document.getElementById('app-badge').innerHTML = badge(transitional);

  try {
    const fns = { start: api.start, stop: api.stop, restart: api.restart };
    await fns[action](APP_ID);
    // Keep transitional badge visible while the process actually loads
    if (action === 'start' || action === 'restart') {
      await new Promise(r => setTimeout(r, 2500));
    }
    app = await api.getApp(APP_ID);
    toast(`${action.charAt(0).toUpperCase() + action.slice(1)} successful`);
  } catch (e) {
    toast(e.message, 'error');
    try { app = await api.getApp(APP_ID); } catch {}
  } finally {
    btn.innerHTML = prev;
    updateHeaderStatus();
    // Reset logs terminal so fresh output starts clean
    if (activeTab === 'logs') {
      teardownTab('logs');
      setupTab('logs');
    }
  }
}

/* ─── Tabs ──────────────────────────────────────────────────────────────── */
function initTabs() {
  const tabs = ['logs', 'stats', 'files', 'settings'];
  tabs.forEach(t => {
    document.getElementById(`tab-${t}`).addEventListener('click', () => switchTab(t));
  });
  switchTab('logs');
}

let activeTab = null;

function switchTab(t) {
  if (activeTab === t) return;

  // Deactivate old
  if (activeTab) {
    document.getElementById(`tab-${activeTab}`).classList.remove('active');
    document.getElementById(`panel-${activeTab}`).classList.remove('active');
    teardownTab(activeTab);
  }

  activeTab = t;
  document.getElementById(`tab-${t}`).classList.add('active');
  document.getElementById(`panel-${t}`).classList.add('active');
  setupTab(t);
}

function teardownTab(t) {
  if (t === 'logs'  && logWs)  { logWs.close();  logWs  = null; }
  if (t === 'stats' && statWs) { statWs.close(); statWs = null; }
}

function setupTab(t) {
  if (t === 'logs')     initLogs();
  if (t === 'stats')    initStats();
  if (t === 'files')    initFiles();
  if (t === 'settings') initSettings();
}

/* ─── LOGS ──────────────────────────────────────────────────────────────── */
function initLogs() {
  const terminal = document.getElementById('log-terminal');
  terminal.innerHTML = `<div class="log-empty">Waiting for log output…</div>`;
  logLines = [];

  logWs = wsLogs(APP_ID, line => {
    if (terminal.querySelector('.log-empty')) terminal.innerHTML = '';
    const n = logLines.length + 1;
    logLines.push(line);

    const div = document.createElement('div');
    div.className = `log-line ${logClass(line)}`;
    div.innerHTML = `<span class="log-num">${String(n).padStart(4)}</span><span class="log-text">${escHtml(line)}</span>`;
    terminal.appendChild(div);

    // Auto-scroll if near bottom
    const atBottom = terminal.scrollHeight - terminal.clientHeight - terminal.scrollTop < 60;
    if (atBottom) terminal.scrollTop = terminal.scrollHeight;

    // Cap lines
    if (logLines.length > 2000) {
      terminal.removeChild(terminal.firstChild);
    }
  });
}

function escHtml(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

/* ─── STATS ─────────────────────────────────────────────────────────────── */
function initStats() {
  cpuData = [];
  memData = [];

  document.getElementById('stats-stopped').style.display = 'none';
  document.getElementById('stats-content').style.display = 'none';

  initCharts();

  statWs = wsStats(APP_ID, data => {
    if (data.status === 'stopped') {
      document.getElementById('stats-stopped').style.display = 'flex';
      document.getElementById('stats-content').style.display = 'none';
      return;
    }

    document.getElementById('stats-stopped').style.display = 'none';
    document.getElementById('stats-content').style.display = 'block';

    document.getElementById('s-cpu').textContent    = `${(data.cpu_percent || 0).toFixed(1)}%`;
    document.getElementById('s-mem').textContent    = `${(data.memory_mb   || 0).toFixed(0)} MB`;
    document.getElementById('s-uptime').textContent = fmtUptime(data.uptime_seconds || 0);
    document.getElementById('s-syscpu').textContent = `${(data.system_cpu_percent || 0).toFixed(1)}%`;

    const sysMem = data.system_memory_percent || 0;
    document.getElementById('sys-mem-fill').style.width = `${sysMem}%`;
    document.getElementById('sys-mem-used').textContent  = `${(data.system_memory_used_mb  || 0).toFixed(0)} MB used`;
    document.getElementById('sys-mem-total').textContent = `${(data.system_memory_total_mb || 0).toFixed(0)} MB total`;
    document.getElementById('sys-mem-pct').textContent   = `${sysMem.toFixed(1)}%`;

    const now = new Date().toLocaleTimeString('nl', { hour:'2-digit', minute:'2-digit', second:'2-digit' });
    cpuData.push({ t: now, v: data.cpu_percent || 0 });
    memData.push({ t: now, v: data.memory_mb   || 0 });
    if (cpuData.length > 60) { cpuData.shift(); memData.shift(); }

    updateChart(chartCpu, cpuData);
    updateChart(chartMem, memData);
  });
}

function initCharts() {
  chartCpu = createChart('chart-cpu', '#58a6ff', '%');
  chartMem = createChart('chart-mem', '#bc8cff', ' MB');
}

function createChart(canvasId, color, unit) {
  const canvas = document.getElementById(canvasId);
  const ctx    = canvas.getContext('2d');

  return {
    canvas, ctx, color, unit,
    draw(data) { drawSparkline(ctx, canvas, data, color, unit); }
  };
}

function updateChart(chart, data) {
  if (!chart) return;
  const canvas = chart.canvas;
  canvas.width  = canvas.offsetWidth  * devicePixelRatio;
  canvas.height = canvas.offsetHeight * devicePixelRatio;
  drawSparkline(chart.ctx, canvas, data, chart.color, chart.unit);
}

function drawSparkline(ctx, canvas, data, color, unit) {
  const W = canvas.width, H = canvas.height;
  const dpr = devicePixelRatio;

  ctx.clearRect(0, 0, W, H);
  if (data.length < 2) return;

  const vals = data.map(d => d.v);
  const min  = Math.min(...vals);
  const max  = Math.max(...vals) || 1;
  const pad  = 6 * dpr;

  const xStep = (W - pad * 2) / (data.length - 1);
  const yScale = d => H - pad - ((d - min) / (max - min || 1)) * (H - pad * 2);

  // Gradient fill
  const grad = ctx.createLinearGradient(0, 0, 0, H);
  grad.addColorStop(0, color + '55');
  grad.addColorStop(1, color + '00');

  ctx.beginPath();
  ctx.moveTo(pad, yScale(vals[0]));
  vals.forEach((v, i) => { if (i > 0) ctx.lineTo(pad + i * xStep, yScale(v)); });
  ctx.lineTo(pad + (vals.length - 1) * xStep, H);
  ctx.lineTo(pad, H);
  ctx.closePath();
  ctx.fillStyle = grad;
  ctx.fill();

  // Line
  ctx.beginPath();
  ctx.moveTo(pad, yScale(vals[0]));
  vals.forEach((v, i) => { if (i > 0) ctx.lineTo(pad + i * xStep, yScale(v)); });
  ctx.strokeStyle = color;
  ctx.lineWidth   = 2 * dpr;
  ctx.lineJoin    = 'round';
  ctx.stroke();

  // Latest value
  ctx.fillStyle = '#e6edf3';
  ctx.font      = `${12 * dpr}px Inter, sans-serif`;
  ctx.textAlign = 'right';
  ctx.fillText(`${vals[vals.length - 1].toFixed(1)}${unit}`, W - pad, pad + 12 * dpr);
}

/* ─── FILES ─────────────────────────────────────────────────────────────── */
let currentFilePath = '';

async function initFiles() {
  await loadDir('');
}

async function loadDir(path) {
  currentFilePath = path;
  const list = document.getElementById('files-list');
  const bcrumb = document.getElementById('files-breadcrumb');
  list.innerHTML = `<div style="padding:16px;color:var(--text-muted);font-size:12px">Loading…</div>`;

  try {
    const data = await api.listFiles(APP_ID, path);

    // Breadcrumb
    const parts = data.path === '.' ? [] : data.path.split('/').filter(Boolean);
    bcrumb.innerHTML = renderBreadcrumb(parts);
    bcrumb.querySelectorAll('.crumb-btn').forEach(btn => {
      btn.addEventListener('click', () => loadDir(btn.dataset.path));
    });

    // Entries
    list.innerHTML = '';

    if (path !== '' && path !== '.') {
      const up = document.createElement('div');
      up.className = 'file-entry';
      up.innerHTML = `${icon.folder} ..`;
      up.addEventListener('click', () => loadDir(parts.slice(0,-1).join('/')));
      list.appendChild(up);
    }

    data.entries.forEach(entry => {
      const el = document.createElement('div');
      el.className = 'file-entry';
      el.innerHTML = entry.is_dir
        ? `<span class="dir-icon">${icon.folder}</span><span>${entry.name}</span>`
        : `<span class="file-icon">${icon.file}</span><span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${entry.name}</span><span class="file-size">${fmtSize(entry.size)}</span>`;

      el.addEventListener('click', () => {
        if (entry.is_dir) loadDir(entry.path);
        else openFile(entry, el);
      });
      list.appendChild(el);
    });

  } catch (e) {
    list.innerHTML = `<div style="padding:16px;color:var(--red);font-size:12px">${e.message}</div>`;
  }
}

function renderBreadcrumb(parts) {
  const items = [{ label:'~', path:'' }, ...parts.map((p, i) => ({ label:p, path:parts.slice(0,i+1).join('/') }))];
  return items.map((item, i) => `
    ${i > 0 ? '<span class="sep">/</span>' : ''}
    <button class="crumb-btn" data-path="${item.path}">${item.label}</button>
  `).join('');
}

async function openFile(entry, el) {
  document.querySelectorAll('.file-entry.active').forEach(e => e.classList.remove('active'));
  el.classList.add('active');

  const header  = document.getElementById('file-viewer-header');
  const hint    = document.getElementById('file-empty-hint');
  const content = document.getElementById('file-content');

  header.innerHTML = `
    ${icon.file}
    <span class="file-path">${entry.path}</span>
    <span class="file-mime">Loading…</span>`;

  hint.style.display    = 'none';
  content.style.display = 'block';
  content.textContent   = '';

  try {
    const data = await api.fileContent(APP_ID, entry.path);
    header.querySelector('.file-mime').textContent = data.mime || '';

    if (data.binary) {
      content.textContent = '[Binary file — cannot display]';
    } else {
      content.textContent = data.content || '';
    }
  } catch (e) {
    content.textContent = `Error: ${e.message}`;
  }
}

/* ─── SETTINGS ──────────────────────────────────────────────────────────── */
function initSettings() {
  // Info rows
  document.getElementById('si-name').textContent  = app.name;
  document.getElementById('si-repo').textContent  = app.repo_url;
  document.getElementById('si-type').textContent  = app.app_type || '—';
  document.getElementById('si-date').textContent  = fmtDate(app.created_at);

  // Form fields
  document.getElementById('cfg-cmd').value          = app.start_command  || '';
  document.getElementById('cfg-port').value         = app.port           || '';
  document.getElementById('cfg-domain').value       = app.domain         || '';
  document.getElementById('cfg-cert').value         = app.ssl_cert_path  || '';
  document.getElementById('cfg-key').value          = app.ssl_key_path   || '';
  document.getElementById('cfg-autostart').checked  = !!app.auto_start;

  // Env vars
  const envContainer = document.getElementById('cfg-env-rows');
  envContainer.innerHTML = '';
  Object.entries(app.env_vars || {}).forEach(([k, v]) => addEnvRow(envContainer, k, v));

  document.getElementById('cfg-add-env').addEventListener('click', () => addEnvRow(envContainer, '', ''));

  // Save
  document.getElementById('btn-save').addEventListener('click', saveSettings);

  // Action tiles
  document.getElementById('tile-pull').addEventListener('click',    () => tileAction('pull', 'Pull'));
  document.getElementById('tile-install').addEventListener('click', () => tileAction('install-deps', 'Install'));

  // Delete
  document.getElementById('btn-delete').addEventListener('click', async () => {
    const ok = await confirm('Delete Application', `This will permanently remove "${app.name}" and all its files. This action cannot be undone.`);
    if (!ok) return;
    try {
      await api.deleteApp(APP_ID);
      window.location.href = '/';
    } catch (e) {
      toast(e.message, 'error');
    }
  });
}

function addEnvRow(container, key = '', value = '') {
  const row = document.createElement('div');
  row.className = 'env-row';
  row.innerHTML = `
    <input class="input input-mono" placeholder="KEY"   value="${escAttr(key)}"   data-env-key />
    <input class="input input-mono" placeholder="value" value="${escAttr(value)}" data-env-val />
    <button type="button" class="btn-remove" title="Remove">${icon.trash}</button>`;
  row.querySelector('.btn-remove').addEventListener('click', () => row.remove());
  container.appendChild(row);
}

function escAttr(s) {
  return (s || '').replace(/"/g, '&quot;').replace(/</g, '&lt;');
}

async function saveSettings() {
  const btn = document.getElementById('btn-save');
  btn.disabled = true;
  btn.innerHTML = `${spinner} Saving…`;

  const env_vars = {};
  document.querySelectorAll('#cfg-env-rows .env-row').forEach(row => {
    const k = row.querySelector('[data-env-key]').value.trim();
    const v = row.querySelector('[data-env-val]').value;
    if (k) env_vars[k] = v;
  });

  const token = document.getElementById('cfg-token')?.value?.trim();

  const payload = {
    start_command:  document.getElementById('cfg-cmd').value.trim()    || null,
    port:           parseInt(document.getElementById('cfg-port').value) || null,
    domain:         document.getElementById('cfg-domain').value.trim() || null,
    ssl_cert_path:  document.getElementById('cfg-cert').value.trim()   || null,
    ssl_key_path:   document.getElementById('cfg-key').value.trim()    || null,
    auto_start:     document.getElementById('cfg-autostart').checked,
    env_vars,
    ...(token ? { github_token: token } : {}),
  };

  try {
    app = await api.updateApp(APP_ID, payload);
    toast('Settings saved');
  } catch (e) {
    toast(e.message, 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = `${icon.save} Save Settings`;
  }
}

async function tileAction(endpoint, label) {
  const tileId = endpoint === 'pull' ? 'tile-pull' : 'tile-install';
  const tile = document.getElementById(tileId);
  tile.disabled = true;
  const origIcon = tile.querySelector('.action-tile-icon').innerHTML;
  tile.querySelector('.action-tile-icon').innerHTML = spinner;

  try {
    const res = await (endpoint === 'pull' ? api.pull(APP_ID) : api.installDeps(APP_ID));
    toast(res.message || `${label} complete`);
  } catch (e) {
    toast(e.message, 'error');
  } finally {
    tile.disabled = false;
    tile.querySelector('.action-tile-icon').innerHTML = origIcon;
  }
}
