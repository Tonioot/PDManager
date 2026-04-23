import { api, wsLogs, wsStats } from './api.js';
import { icon, typeIcon, badge, toast, confirm, spinner, fmtUptime, fmtSize, fmtDate, logClass, setBtn } from './utils.js';
import { pickGitHubToken } from './sidebar.js';

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
let statsTabActive = false;
let lastStatStatus = null; // 'running' | 'stopped' | null (unknown/loading)

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
  startBgStats();          // Collect stats in the background from the start
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

  const typeIconEl = document.getElementById('app-type-icon');
  if (typeIconEl) typeIconEl.innerHTML = typeIcon[app.app_type] || typeIcon.unknown;

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
    // Clear chart history on start/restart — new process = fresh data
    if (action === 'start' || action === 'restart') {
      cpuData = [];
      memData = [];
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
  if (t === 'logs'  && logWs) { logWs.close(); logWs = null; }
  if (t === 'stats') { statsTabActive = false; } // Keep statWs alive — data keeps accumulating
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

/* ─── STATS — background collection ─────────────────────────────────────── */
function startBgStats() {
  statWs = wsStats(APP_ID, handleStatData);
}

function handleStatData(data) {
  if (data.status === 'stopped') {
    lastStatStatus = 'stopped';
    if (statsTabActive) {
      _removeStatsLoading();
      document.getElementById('stats-stopped').style.display = 'flex';
      document.getElementById('stats-content').style.display = 'none';
    }
    return;
  }
  lastStatStatus = 'running';

  // Always accumulate — even while on a different tab
  const now = new Date().toLocaleTimeString('nl', { hour:'2-digit', minute:'2-digit', second:'2-digit' });
  cpuData.push({ t: now, v: data.cpu_percent || 0 });
  memData.push({ t: now, v: data.memory_mb   || 0 });
  if (cpuData.length > 60) { cpuData.shift(); memData.shift(); }

  if (!statsTabActive) return;

  _removeStatsLoading();
  document.getElementById('stats-stopped').style.display = 'none';
  document.getElementById('stats-content').style.display = 'block';

  document.getElementById('s-cpu').textContent    = `${(data.cpu_percent || 0).toFixed(1)}%`;
  document.getElementById('s-mem').textContent    = `${(data.memory_mb   || 0).toFixed(0)} MB`;
  document.getElementById('s-uptime').textContent = fmtUptime(data.uptime_seconds || 0);
  document.getElementById('s-syscpu').textContent = `${(data.system_cpu_percent || 0).toFixed(1)}%`;

  document.getElementById('s-pid').textContent     = data.pid ?? '—';
  document.getElementById('s-threads').textContent = data.num_threads ?? '—';
  document.getElementById('s-conns').textContent   = data.num_connections ?? '—';
  document.getElementById('s-vms').textContent     = `${(data.memory_vms_mb || 0).toFixed(0)} MB`;

  const sysMem = data.system_memory_percent || 0;
  document.getElementById('sys-mem-fill').style.width = `${sysMem}%`;
  document.getElementById('sys-mem-used').textContent  = `${(data.system_memory_used_mb  || 0).toFixed(0)} MB used`;
  document.getElementById('sys-mem-total').textContent = `${(data.system_memory_total_mb || 0).toFixed(0)} MB total`;
  document.getElementById('sys-mem-pct').textContent   = `${sysMem.toFixed(1)}%`;

  updateChart(chartCpu, cpuData);
  updateChart(chartMem, memData);
}

function initStats() {
  statsTabActive = true;

  initCharts();

  // Show the right panel immediately based on last known status
  if (lastStatStatus === 'stopped') {
    document.getElementById('stats-stopped').style.display = 'flex';
    document.getElementById('stats-content').style.display = 'none';
  } else if (cpuData.length > 0) {
    document.getElementById('stats-stopped').style.display = 'none';
    document.getElementById('stats-content').style.display = 'block';
    updateChart(chartCpu, cpuData);
    updateChart(chartMem, memData);
  } else {
    // Status unknown (still connecting) — show a subtle loading state
    document.getElementById('stats-stopped').style.display = 'none';
    document.getElementById('stats-content').style.display = 'none';
    document.getElementById('panel-stats').insertAdjacentHTML('afterbegin',
      '<div id="stats-loading" style="display:flex;align-items:center;justify-content:center;height:120px;color:var(--text-muted);font-size:13px;gap:8px">'
      + '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/></svg>'
      + 'Loading stats…</div>');
  }
}

function _removeStatsLoading() {
  document.getElementById('stats-loading')?.remove();
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
  const dataMin = Math.min(...vals);
  const dataMax = Math.max(...vals);
  const range   = dataMax - dataMin;
  const pad     = 6 * dpr;

  // When all values are equal, add padding so the line appears centered
  const lo = range === 0 ? Math.max(0, dataMin - Math.max(dataMin * 0.1, 1)) : dataMin;
  const hi = range === 0 ? dataMax + Math.max(dataMax * 0.1, 1) : dataMax;
  const effectiveRange = (hi - lo) || 1;

  const xStep  = (W - pad * 2) / (data.length - 1);
  const yScale = d => H - pad - ((d - lo) / effectiveRange) * (H - pad * 2);

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
  const last = vals[vals.length - 1];
  ctx.fillText(`${last % 1 === 0 ? last.toFixed(0) : last.toFixed(1)}${unit}`, W - pad, pad + 12 * dpr);
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

/* ─── SETTINGS ──────────────────────────────────────────────────────────── */function showCertPicker(inputEl, items, label, displayEl) {
  document.querySelectorAll('.cert-picker').forEach(p => p.remove());
  if (!items.length) { toast(`No ${label} found in app folder`, 'warn'); return; }

  const picker = document.createElement('div');
  picker.className = 'cert-picker';
  picker.style.cssText = 'position:absolute;z-index:9999;background:#161b22;border:1px solid #30363d;border-radius:6px;max-height:200px;overflow-y:auto;box-shadow:0 8px 24px rgba(0,0,0,.5);font-size:12px;';

  items.forEach(path => {
    const row = document.createElement('div');
    row.textContent = path;
    row.style.cssText = 'padding:8px 12px;cursor:pointer;color:#e6edf3;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;';
    row.addEventListener('mouseenter', () => row.style.background = '#21262d');
    row.addEventListener('mouseleave', () => row.style.background = '');
    row.addEventListener('click', () => {
      inputEl.value = path;
      if (displayEl) { displayEl.textContent = path.split('/').pop(); displayEl.classList.add('has-value'); }
      picker.remove();
    });
    picker.appendChild(row);
  });

  // Anchor to the visible row container (cert-upload-row), not the hidden input
  const anchorEl = displayEl ? displayEl.closest('.cert-upload-row') || displayEl : inputEl;
  const rect = anchorEl.getBoundingClientRect();
  picker.style.top   = `${rect.bottom + window.scrollY + 4}px`;
  picker.style.left  = `${rect.left + window.scrollX}px`;
  picker.style.width = `${Math.max(rect.width, 280)}px`;
  document.body.appendChild(picker);

  const close = e => { if (!picker.contains(e.target)) { picker.remove(); document.removeEventListener('click', close, true); } };
  setTimeout(() => document.addEventListener('click', close, true), 0);
}
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
  document.getElementById('cfg-autostart').checked  = !!app.auto_start;
  document.getElementById('cfg-restart-policy').value = app.restart_policy || 'no';

  // Cert/key hidden inputs + filename display
  function setCertDisplay(inputId, nameId, path) {
    document.getElementById(inputId).value = path || '';
    const nameEl = document.getElementById(nameId);
    if (path) { nameEl.textContent = path.split('/').pop(); nameEl.classList.add('has-value'); }
    else      { nameEl.textContent = 'No file selected'; nameEl.classList.remove('has-value'); }
  }
  setCertDisplay('cfg-cert', 'cfg-cert-name', app.ssl_cert_path || '');
  setCertDisplay('cfg-key',  'cfg-key-name',  app.ssl_key_path  || '');

  // Env vars
  const envContainer = document.getElementById('cfg-env-rows');
  envContainer.innerHTML = '';
  Object.entries(app.env_vars || {}).forEach(([k, v]) => addEnvRow(envContainer, k, v));

  document.getElementById('cfg-add-env').addEventListener('click', () => addEnvRow(envContainer, '', ''));

  // Pick saved GitHub token
  document.getElementById('cfg-token-pick').addEventListener('click', () => {
    pickGitHubToken(document.getElementById('cfg-token'));
  });

  // Save
  document.getElementById('btn-save').addEventListener('click', saveSettings);

  // Action tiles
  document.getElementById('tile-pull').addEventListener('click',    () => tileAction('pull', 'Pull'));
  document.getElementById('tile-install').addEventListener('click', () => tileAction('install-deps', 'Install'));
  document.getElementById('tile-nginx').addEventListener('click',   openNginxModal);

  // Cert scan buttons (search within app folder only)
  document.getElementById('cfg-scan-cert').addEventListener('click', async () => {
    const btn = document.getElementById('cfg-scan-cert');
    btn.disabled = true; btn.textContent = 'Scanning…';
    try {
      const { certs } = await api.discoverAppCerts(APP_ID);
      showCertPicker(document.getElementById('cfg-cert'), certs, 'certificates', document.getElementById('cfg-cert-name'));
    } catch { toast('Scan failed', 'error'); }
    finally { btn.disabled = false; btn.innerHTML = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg> Scan'; }
  });
  document.getElementById('cfg-scan-key').addEventListener('click', async () => {
    const btn = document.getElementById('cfg-scan-key');
    btn.disabled = true; btn.textContent = 'Scanning…';
    try {
      const { keys } = await api.discoverAppCerts(APP_ID);
      showCertPicker(document.getElementById('cfg-key'), keys, 'private keys', document.getElementById('cfg-key-name'));
    } catch { toast('Scan failed', 'error'); }
    finally { btn.disabled = false; btn.innerHTML = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg> Scan'; }
  });

  // Cert upload buttons
  document.getElementById('cfg-upload-cert').addEventListener('click', () => document.getElementById('cfg-cert-file').click());
  document.getElementById('cfg-cert-file').addEventListener('change', async e => {
    const file = e.target.files[0]; if (!file) return;
    document.getElementById('cfg-upload-cert').disabled = true;
    try {
      const res = await api.uploadAppCert(APP_ID, file);
      setCertDisplay('cfg-cert', 'cfg-cert-name', res.path);
    } catch (err) { toast(err.message, 'error'); }
    finally { document.getElementById('cfg-upload-cert').disabled = false; e.target.value = ''; }
  });
  document.getElementById('cfg-upload-key').addEventListener('click', () => document.getElementById('cfg-key-file').click());
  document.getElementById('cfg-key-file').addEventListener('change', async e => {
    const file = e.target.files[0]; if (!file) return;
    document.getElementById('cfg-upload-key').disabled = true;
    try {
      const res = await api.uploadAppCert(APP_ID, file);
      setCertDisplay('cfg-key', 'cfg-key-name', res.path);
    } catch (err) { toast(err.message, 'error'); }
    finally { document.getElementById('cfg-upload-key').disabled = false; e.target.value = ''; }
  });

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
    restart_policy: document.getElementById('cfg-restart-policy').value,
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

async function openNginxModal() {
  const modal    = document.getElementById('nginx-modal');
  const textarea = document.getElementById('nginx-config-textarea');
  const pathEl   = document.getElementById('nginx-config-path');
  const badge    = document.getElementById('nginx-status-badge');
  const msgEl    = document.getElementById('nginx-save-msg');
  msgEl.style.display = 'none';
  textarea.value = 'Loading…';
  modal.style.display = 'flex';

  try {
    const data = await api.getNginxConfig(APP_ID);
    pathEl.textContent = data.path;
    badge.textContent  = data.active ? '● Active' : data.exists ? '○ Inactive' : '○ Not created';
    badge.style.color  = data.active ? 'var(--green)' : 'var(--text-muted)';
    textarea.value = data.content || '# No config yet — fill in domain/port in Settings and save to generate one';
  } catch (e) {
    textarea.value = `Error: ${e.message}`;
  }

  const saveBtn = document.getElementById('nginx-save');
  saveBtn.onclick = async () => {
    saveBtn.disabled = true;
    msgEl.style.display = 'none';
    try {
      const res = await api.saveNginxConfig(APP_ID, textarea.value);
      msgEl.textContent = res.ok ? 'Saved & nginx reloaded successfully.' : `Error: ${res.message}`;
      msgEl.style.display = 'block';
      msgEl.style.color = res.ok ? 'var(--green)' : 'var(--red)';
      if (res.ok) { badge.textContent = '● Active'; badge.style.color = 'var(--green)'; }
    } catch (e) {
      msgEl.textContent = e.message; msgEl.style.display = 'block'; msgEl.style.color = 'var(--red)';
    } finally {
      saveBtn.disabled = false;
    }
  };

  document.getElementById('nginx-close').onclick = () => { modal.style.display = 'none'; };
  modal.addEventListener('click', e => { if (e.target === modal) modal.style.display = 'none'; });
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
