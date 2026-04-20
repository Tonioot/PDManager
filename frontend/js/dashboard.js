import { api, wsSystemStats } from './api.js';
import { icon, typeIcon, badge, toast, confirm, spinner, setBtn } from './utils.js';
import { openDeployModal } from './modal.js';

let appsData = [];
let sysWs = null;

/* ─── Init ──────────────────────────────────────────────────────────────── */
export async function initDashboard() {
  document.getElementById('btn-deploy').addEventListener('click', () => {
    openDeployModal(app => {
      toast(`"${app.name}" deployed successfully`);
      window.location.href = `app.html?id=${app.id}`;
    });
  });

  await loadApps();
  setInterval(loadApps, 6000);

  sysWs = wsSystemStats(updateSysStats);
}

/* ─── Load apps ─────────────────────────────────────────────────────────── */
async function loadApps() {
  try {
    appsData = await api.listApps();
    renderStats();
    renderApps();
  } catch (e) {
    console.error('Failed to load apps:', e);
  }
}

/* ─── Stat strip ────────────────────────────────────────────────────────── */
function renderStats() {
  const total    = appsData.length;
  const running  = appsData.filter(a => a.status === 'running').length;
  const stopped  = appsData.filter(a => a.status === 'stopped').length;
  const errors   = appsData.filter(a => a.status === 'error').length;

  document.getElementById('stat-total').textContent   = total;
  document.getElementById('stat-running').textContent = running;
  document.getElementById('stat-stopped').textContent = stopped;
  document.getElementById('stat-errors').textContent  = errors;
}

/* ─── Apps grid ─────────────────────────────────────────────────────────── */
function renderApps() {
  const grid = document.getElementById('apps-grid');

  if (appsData.length === 0) {
    grid.innerHTML = `
      <div class="empty-state" style="grid-column:1/-1">
        <div class="empty-icon">${icon.server}</div>
        <div class="empty-title">No applications deployed</div>
        <div class="empty-sub">Deploy your first application from a GitHub repository to get started.</div>
        <button class="btn btn-primary" id="empty-deploy-btn">${icon.plus} Deploy Application</button>
      </div>`;
    document.getElementById('empty-deploy-btn')?.addEventListener('click', () => {
      openDeployModal(app => { window.location.href = `app.html?id=${app.id}`; });
    });
    return;
  }

  grid.innerHTML = appsData.map(app => appCardHTML(app)).join('');

  appsData.forEach(app => {
    const card = document.getElementById(`card-${app.id}`);
    if (!card) return;

    // Whole card navigates to detail
    card.addEventListener('click', () => {
      window.location.href = `app.html?id=${app.id}`;
    });

    // Action buttons must not trigger card navigation
    card.querySelector('.btn-start')?.addEventListener('click', e => {
      e.stopPropagation();
      appAction(app.id, 'start', card);
    });

    card.querySelector('.btn-stop')?.addEventListener('click', e => {
      e.stopPropagation();
      appAction(app.id, 'stop', card);
    });

    card.querySelector('.btn-restart')?.addEventListener('click', e => {
      e.stopPropagation();
      appAction(app.id, 'restart', card);
    });
  });
}

function appCardHTML(app) {
  const busy = app.status === 'deploying';
  const isRunning = app.status === 'running';
  const primaryBtn = `
    <button class="btn btn-success btn-sm btn-start"
      ${isRunning || busy ? 'disabled' : ''}
      style="opacity:${isRunning ? '.4' : '1'}">${icon.play} Start</button>
    <button class="btn btn-danger btn-sm btn-stop"
      ${!isRunning || busy ? 'disabled' : ''}
      style="opacity:${!isRunning ? '.4' : '1'}">${icon.stop} Stop</button>`;

  const repoShort = (app.repo_url || '').replace('https://github.com/', '');

  return `
    <div class="card app-card" id="card-${app.id}">
      <div class="app-card-top">
        <div class="app-card-identity">
          <div class="app-type-icon">${typeIcon[app.app_type] || typeIcon.unknown}</div>
          <div>
            <div class="app-name">${app.name}</div>
            <div class="app-type-label">${app.app_type || 'unknown'}</div>
          </div>
        </div>
        ${badge(app.status)}
      </div>

      <div class="app-card-meta">
        ${app.domain ? `<div class="app-meta-row">${icon.globe}<span>${app.domain}</span></div>` : ''}
        ${app.port   ? `<div class="app-meta-row">${icon.terminal}<span>Port ${app.port}</span></div>` : ''}
        <div class="app-meta-row">${icon.link}<span>${repoShort}</span></div>
      </div>

      <div class="app-card-actions">
        ${primaryBtn}
        <button class="btn btn-secondary btn-sm btn-icon btn-restart" title="Restart">${icon.restart}</button>
      </div>
    </div>`;
}

/* ─── Quick actions ─────────────────────────────────────────────────────── */
async function appAction(id, action, card) {
  const btnEl = card.querySelector(`.btn-${action === 'start' ? 'start' : action === 'stop' ? 'stop' : 'restart'}`);
  if (btnEl) btnEl.disabled = true;

  try {
    const fns = { start: api.start, stop: api.stop, restart: api.restart };
    await fns[action](id);
    await loadApps();
    toast(`${action.charAt(0).toUpperCase() + action.slice(1)} successful`);
  } catch (e) {
    toast(e.message, 'error');
    if (btnEl) btnEl.disabled = false;
  }
}

/* ─── System stats (sidebar) ────────────────────────────────────────────── */
function updateSysStats(data) {
  setBar('bar-cpu',  data.cpu_percent,            `${data.cpu_percent?.toFixed(0)}%`);
  setBar('bar-ram',  data.memory_percent,          `${data.memory_percent?.toFixed(0)}%`);
  setBar('bar-disk', data.disk_percent,            `${data.disk_percent?.toFixed(0)}%`);
}

function setBar(id, pct, label) {
  const wrap = document.getElementById(id);
  if (!wrap) return;
  wrap.querySelector('.mini-bar-fill').style.width = `${Math.min(pct || 0, 100)}%`;
  wrap.querySelector('.val').textContent = label;
}
