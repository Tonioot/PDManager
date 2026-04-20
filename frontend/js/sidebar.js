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

export function initSidebar() {
  loadSidebarApps();
  setInterval(loadSidebarApps, 8000);
  wireServiceButton();
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
