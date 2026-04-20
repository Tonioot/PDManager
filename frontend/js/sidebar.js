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
        showMsg(msg, `Nginx configured — PDManager reachable at ${cert ? 'https' : 'http'}://${domain}`, true);
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
          <div class="dialog-title">Install systemd Service</div>
          <div class="dialog-body" style="font-size:13px;line-height:1.6">
            <p style="margin:0 0 10px">Run these commands to make PDManager start automatically on boot:</p>
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
        `# 1. Create the service file`,
        `sudo tee /etc/systemd/system/pdmanager.service << 'EOF'`,
        data.content.trim(),
        `EOF`,
        ``,
        `# 2. Enable and start`,
        `sudo systemctl daemon-reload`,
        `sudo systemctl enable pdmanager`,
        `sudo systemctl start pdmanager`,
      ].join('\n');
    } catch (e) {
      pre.textContent = `Error: ${e.message}`;
    }
  });
}
