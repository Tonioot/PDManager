import { api } from './api.js';
import { toast } from './utils.js';

const STATUS_DOT = {
  running:  'var(--green)',
  stopped:  'var(--text-muted)',
  error:    'var(--red)',
  deploying:'var(--yellow)',
  starting: 'var(--yellow)',
  stopping: 'var(--yellow)',
};

// ── Helper: set a cert filename display + hidden input ───────────────────────
function setCertDisplay(modal, nameId, hiddenId, path) {
  modal.querySelector(hiddenId).value = path || '';
  const nameEl = modal.querySelector(nameId);
  if (path) {
    nameEl.textContent = path.split('/').pop();
    nameEl.classList.add('has-value');
  } else {
    nameEl.textContent = 'No file selected';
    nameEl.classList.remove('has-value');
  }
}

export function initSidebar() {
  loadSidebarApps();
  setInterval(loadSidebarApps, 8000);
  wireServiceButton();
  wirePDManagerNginxButton();
  initSessionTimer();
  wireGitHubTokensButton();
}

async function loadSidebarApps() {
  const container = document.getElementById('sidebar-apps');
  if (!container) return;

  try {
    const apps = await api.listApps();
    const currentId = parseInt(new URLSearchParams(location.search).get('id'));

    if (apps.length === 0) {
      container.innerHTML = `<div class="sidebar-apps-empty">No apps deployed</div>`;
      return;
    }

    container.innerHTML = apps.map(app => {
      const dot   = STATUS_DOT[app.status] || 'var(--text-muted)';
      const active = app.id === currentId ? ' active' : '';
      return `
        <a href="/app.html?id=${app.id}" class="sidebar-app-item${active}">
          <span class="sidebar-app-dot" style="background:${dot}"></span>
          <span class="sidebar-app-name">${app.name}</span>
        </a>`;
    }).join('');
  } catch {}
}

function wirePDManagerNginxButton() {
  const btn   = document.getElementById('btn-pdm-nginx');
  const modal = document.getElementById('pdm-nginx-modal');
  if (!btn || !modal) return;

  btn.addEventListener('click', async () => {
    modal.style.display = 'flex';
    const msg = modal.querySelector('#pdm-nginx-msg');
    msg.style.display = 'none';

    // Pre-fill existing config domain if present
    try {
      const data = await api.getPDManagerNginx();
      if (data.exists && data.content) {
        const m = data.content.match(/server_name\s+([^\s;]+)/);
        if (m) modal.querySelector('#pdm-domain').value = m[1];
        const c = data.content.match(/ssl_certificate\s+([^\s;]+)/);
        if (c) setCertDisplay(modal, '#pdm-cert-name', '#pdm-cert', c[1]);
        const k = data.content.match(/ssl_certificate_key\s+([^\s;]+)/);
        if (k) setCertDisplay(modal, '#pdm-key-name', '#pdm-key', k[1]);
      }
    } catch {}
  });

  modal.querySelector('#pdm-nginx-close').onclick = () => { modal.style.display = 'none'; };
  modal.addEventListener('click', e => { if (e.target === modal) modal.style.display = 'none'; });

  // Upload buttons
  modal.querySelector('#pdm-upload-cert').addEventListener('click', () => modal.querySelector('#pdm-cert-file').click());
  modal.querySelector('#pdm-cert-file').addEventListener('change', async e => {
    const file = e.target.files[0];
    if (!file) return;
    modal.querySelector('#pdm-upload-cert').disabled = true;
    try {
      const res = await api.uploadSystemCert(file);
      setCertDisplay(modal, '#pdm-cert-name', '#pdm-cert', res.path);
    } catch (err) { toast(err.message, 'error'); }
    finally { modal.querySelector('#pdm-upload-cert').disabled = false; e.target.value = ''; }
  });

  modal.querySelector('#pdm-upload-key').addEventListener('click', () => modal.querySelector('#pdm-key-file').click());
  modal.querySelector('#pdm-key-file').addEventListener('change', async e => {
    const file = e.target.files[0];
    if (!file) return;
    modal.querySelector('#pdm-upload-key').disabled = true;
    try {
      const res = await api.uploadSystemCert(file);
      setCertDisplay(modal, '#pdm-key-name', '#pdm-key', res.path);
    } catch (err) { toast(err.message, 'error'); }
    finally { modal.querySelector('#pdm-upload-key').disabled = false; e.target.value = ''; }
  });

  modal.querySelector('#pdm-nginx-apply').addEventListener('click', async () => {
    const domain = modal.querySelector('#pdm-domain').value.trim();
    const cert   = modal.querySelector('#pdm-cert').value.trim() || null;
    const key    = modal.querySelector('#pdm-key').value.trim()  || null;
    const msg    = modal.querySelector('#pdm-nginx-msg');

    if (!domain) { showMsg(msg, 'Domain is required', false); return; }

    const applyBtn = modal.querySelector('#pdm-nginx-apply');
    applyBtn.disabled = true;

    try {
      const res = await api.applyPDManagerNginx({ domain, ssl_cert_path: cert, ssl_key_path: key });
      if (res.ok) {
        showMsg(msg, `Nginx configured — Cloudbase reachable at ${cert ? 'https' : 'http'}://${domain}`, true);
      } else {
        showMsg(msg, res.message, false);
      }
    } catch (e) {
      showMsg(msg, e.message, false);
    } finally {
      applyBtn.disabled = false;
    }
  });
}

function showMsg(el, text, success) {
  el.textContent = text;
  el.style.display = 'block';
  el.style.background = success ? 'var(--green-bg)'  : 'var(--red-bg)';
  el.style.color      = success ? 'var(--green)'     : 'var(--red)';
  el.style.border     = `1px solid ${success ? 'var(--green-border)' : 'var(--red-border)'}`;
}

function wireServiceButton() {
  const btn = document.getElementById('btn-install-service');
  if (!btn) return;

  btn.addEventListener('click', async () => {
    let modal = document.getElementById('service-modal-global');
    if (!modal) {
      modal = document.createElement('div');
      modal.id = 'service-modal-global';
      modal.className = 'dialog-backdrop';
      modal.innerHTML = `
        <div class="dialog" style="max-width:560px;width:90%">
          <div class="dialog-title">Enable Cloudbase Auto Start</div>
          <div class="dialog-body" style="font-size:13px;line-height:1.6">
            <p style="margin:0 0 10px">Run this command to make Cloudbase start automatically on boot:</p>
            <pre id="service-pre-global" style="background:var(--bg-muted);border:1px solid var(--border);border-radius:6px;padding:12px;font-size:12px;overflow-x:auto;white-space:pre;margin:0 0 12px">Loading…</pre>
            <p style="margin:0;color:var(--text-muted);font-size:12px">Requires <code>sudo</code>. Run once on your Linux server.</p>
          </div>
          <div class="dialog-actions">
            <button class="btn btn-secondary" id="service-copy-global">Copy Commands</button>
            <button class="btn btn-primary" id="service-close-global">Close</button>
          </div>
        </div>`;
      document.body.appendChild(modal);

      modal.querySelector('#service-close-global').onclick = () => { modal.style.display = 'none'; };
      modal.querySelector('#service-copy-global').onclick  = () => {
        navigator.clipboard.writeText(modal.querySelector('#service-pre-global').textContent);
        toast('Copied to clipboard');
      };
      modal.addEventListener('click', e => { if (e.target === modal) modal.style.display = 'none'; });
    }

    modal.style.display = 'flex';
    const pre = modal.querySelector('#service-pre-global');
    pre.textContent = 'Loading…';

    try {
      const data = await api.serviceFile();
      pre.textContent = [
        `# Fastest option`,
        `cloudbase enable`,
        ``,
        `# Manual systemd setup`,
        `sudo tee ${data.path} << 'EOF'`,
        data.content.trim(),
        `EOF`,
        ``,
        `sudo systemctl daemon-reload`,
        `sudo systemctl enable --now cloudbase`,
      ].join('\n');
    } catch (e) {
      pre.textContent = `Error: ${e.message}`;
    }
  });
}

// ── Session timer ─────────────────────────────────────────────────────────────
function fmtSeconds(s) {
  if (s <= 0) return 'Expired';
  const m = Math.floor(s / 60);
  const sec = s % 60;
  return `${m}:${String(sec).padStart(2, '0')}`;
}

async function initSessionTimer() {
  const bar = document.getElementById('session-timer-bar');
  if (!bar) return;

  const fill  = bar.querySelector('.session-timer-fill');
  const label = bar.querySelector('.session-timer-label');

  let remaining = 3600; // fallback
  try {
    const data = await api.getSession();
    remaining = data.expires_in;
  } catch { return; }

  const total = 3600; // fixed token lifetime — percentage relative to full session

  function tick() {
    if (remaining <= 0) {
      label.textContent = 'Session expired — please log in again';
      fill.style.width  = '0%';
      fill.style.background = 'var(--red)';
      return;
    }

    label.textContent = `Session: ${fmtSeconds(remaining)} remaining`;
    const pct = Math.max(0, (remaining / total) * 100);
    fill.style.width = `${pct}%`;

    if (pct < 15) {
      fill.style.background = 'var(--red)';
    } else if (pct < 35) {
      fill.style.background = 'var(--yellow)';
    } else {
      fill.style.background = 'var(--accent)';
    }

    remaining--;
  }

  tick();
  setInterval(tick, 1000);
}

// ── GitHub token vault ────────────────────────────────────────────────────────
function wireGitHubTokensButton() {
  const btn = document.getElementById('btn-github-tokens');
  if (!btn) return;

  btn.addEventListener('click', () => openGitHubTokensModal());
}

function openGitHubTokensModal() {
  let modal = document.getElementById('github-tokens-modal-global');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'github-tokens-modal-global';
    modal.className = 'dialog-backdrop';
    modal.innerHTML = `
      <div class="dialog" style="max-width:480px;width:90%">
        <div class="dialog-title">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" style="margin-right:6px;vertical-align:-2px"><path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z"/></svg>
          GitHub Tokens
        </div>
        <div class="dialog-body">
          <p style="font-size:12px;color:var(--text-muted);margin:0 0 12px">
            Save tokens here so you can quickly pick them when deploying apps.
          </p>
          <div id="gh-tokens-list" style="margin-bottom:12px"></div>
          <div style="display:flex;gap:8px;margin-bottom:8px">
            <input class="input" id="gh-token-label" placeholder="Label (e.g. my-org)" style="flex:1;min-width:0" />
            <input class="input input-mono" id="gh-token-value" type="password" placeholder="ghp_..." style="flex:2;min-width:0" />
          </div>
          <div id="gh-token-err" style="display:none;color:var(--red);font-size:12px;margin-bottom:8px"></div>
        </div>
        <div class="dialog-actions">
          <button class="btn btn-secondary" id="gh-tokens-close">Close</button>
          <button class="btn btn-primary" id="gh-token-add">Save Token</button>
        </div>
      </div>`;
    document.body.appendChild(modal);

    modal.querySelector('#gh-tokens-close').onclick = () => { modal.style.display = 'none'; };
    modal.addEventListener('click', e => { if (e.target === modal) modal.style.display = 'none'; });

    modal.querySelector('#gh-token-add').addEventListener('click', async () => {
      const label = modal.querySelector('#gh-token-label').value.trim();
      const token = modal.querySelector('#gh-token-value').value.trim();
      const err   = modal.querySelector('#gh-token-err');
      err.style.display = 'none';
      if (!label) { err.textContent = 'Label is required'; err.style.display = 'block'; return; }
      if (!token) { err.textContent = 'Token is required'; err.style.display = 'block'; return; }
      try {
        await api.saveGitHubToken(label, token);
        modal.querySelector('#gh-token-label').value = '';
        modal.querySelector('#gh-token-value').value = '';
        await renderTokenList(modal);
        toast(`Token "${label}" saved`);
      } catch (e) {
        err.textContent = e.message;
        err.style.display = 'block';
      }
    });
  }

  modal.style.display = 'flex';
  renderTokenList(modal);
}

async function renderTokenList(modal) {
  const list = modal.querySelector('#gh-tokens-list');
  list.innerHTML = '<div style="color:var(--text-muted);font-size:12px">Loading…</div>';
  try {
    const tokens = await api.listGitHubTokens();
    if (tokens.length === 0) {
      list.innerHTML = '<div style="color:var(--text-muted);font-size:12px">No saved tokens yet.</div>';
      return;
    }
    list.innerHTML = tokens.map(t => `
      <div class="gh-token-row" data-id="${t.id}" style="display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid var(--border-muted)">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" style="color:var(--text-muted);flex-shrink:0"><path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z"/></svg>
        <span style="flex:1;font-size:13px;font-weight:500">${t.label}</span>
        <span style="font-size:11px;color:var(--text-muted);font-family:monospace">••••${t.token_hint}</span>
        <button class="btn btn-danger btn-sm gh-token-delete" style="padding:3px 8px;font-size:11px">Delete</button>
      </div>`).join('');

    list.querySelectorAll('.gh-token-delete').forEach(btn => {
      btn.addEventListener('click', async () => {
        const id = btn.closest('[data-id]').dataset.id;
        await api.deleteGitHubToken(id);
        await renderTokenList(modal);
        toast('Token deleted');
      });
    });
  } catch (e) {
    list.innerHTML = `<div style="color:var(--red);font-size:12px">${e.message}</div>`;
  }
}

// Exported so the deploy modal and settings page can call it.
// tokenInput    – the visible password <input> (used for display only when a vault token is chosen)
// tokenIdInput  – a hidden <input> that stores the vault token ID (sent to backend instead of raw value)
export async function pickGitHubToken(tokenInput, tokenIdInput) {
  let tokens = [];
  try { tokens = await api.listGitHubTokens(); } catch { return; }
  if (!tokens.length) { toast('No saved tokens — save one via the GitHub Tokens button', 'warn'); return; }

  document.querySelectorAll('.gh-token-picker').forEach(p => p.remove());

  const picker = document.createElement('div');
  picker.className = 'gh-token-picker cert-picker';
  picker.style.cssText = `position:absolute;z-index:9999;background:#161b22;border:1px solid #30363d;
    border-radius:6px;max-height:200px;overflow-y:auto;min-width:260px;
    box-shadow:0 8px 24px rgba(0,0,0,.5);font-size:12px;`;

  tokens.forEach(t => {
    const row = document.createElement('div');
    row.style.cssText = 'padding:8px 12px;cursor:pointer;color:#e6edf3;display:flex;justify-content:space-between;gap:12px;';
    row.innerHTML = `<span style="font-weight:500">${t.label}</span><span style="color:#8b949e;font-family:monospace">••••${t.token_hint}</span>`;
    row.addEventListener('mouseenter', () => row.style.background = '#21262d');
    row.addEventListener('mouseleave', () => row.style.background = '');
    row.addEventListener('click', () => {
      picker.remove();
      // Store only the vault ID server-side; show a non-editable label in the input
      if (tokenIdInput) tokenIdInput.value = t.id;
      // Show the label as a visual indicator — placeholder style
      tokenInput.value = '';
      tokenInput.placeholder = `🔑 ${t.label} (••••${t.token_hint})`;
      tokenInput.dataset.vaultLabel = t.label;
      // Clear the vault selection when the user starts typing a new token manually
      const clearVault = () => {
        if (tokenIdInput) tokenIdInput.value = '';
        tokenInput.placeholder = tokenInput.dataset.origPlaceholder || '';
        delete tokenInput.dataset.vaultLabel;
        tokenInput.removeEventListener('input', clearVault);
      };
      tokenInput.addEventListener('input', clearVault);
    });
    picker.appendChild(row);
  });

  const rect = tokenInput.getBoundingClientRect();
  picker.style.top  = `${rect.bottom + window.scrollY + 4}px`;
  picker.style.left = `${rect.left + window.scrollX}px`;
  picker.style.width = `${Math.max(rect.width, 260)}px`;
  document.body.appendChild(picker);

  const close = e => { if (!picker.contains(e.target) && e.target !== tokenInput) { picker.remove(); document.removeEventListener('click', close, true); } };
  setTimeout(() => document.addEventListener('click', close, true), 0);
}
