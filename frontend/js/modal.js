import { api } from './api.js';
import { icon, spinner, toast } from './utils.js';

export function openDeployModal(onSuccess) {
  const backdrop = document.createElement('div');
  backdrop.className = 'modal-backdrop';
  backdrop.innerHTML = modalHTML();
  document.body.appendChild(backdrop);

  const modal = backdrop.querySelector('.modal');
  const form  = modal.querySelector('#deploy-form');
  let envCount = 0;

  // Close
  const close = () => backdrop.remove();
  backdrop.addEventListener('click', e => { if (e.target === backdrop) close(); });
  modal.querySelector('#modal-close').addEventListener('click', close);
  modal.querySelector('#modal-cancel').addEventListener('click', close);

  // Add env var row
  modal.querySelector('#add-env').addEventListener('click', () => addEnvRow(modal, ++envCount));

  // Submit
  form.addEventListener('submit', async e => {
    e.preventDefault();
    await handleDeploy(modal, form, onSuccess, close);
  });
}

function modalHTML() {
  return `
    <div class="modal">
      <div class="modal-header">
        <div>
          <div class="modal-title">Deploy Application</div>
          <div class="modal-sub">Configure and deploy a new application from GitHub</div>
        </div>
        <button class="modal-close" id="modal-close">${icon.x}</button>
      </div>

      <form id="deploy-form" novalidate>
        <div class="modal-body">

          <!-- Basic -->
          <div class="modal-section">
            <div class="section-title">${icon.terminal} Basic Configuration</div>

            <div class="field">
              <label class="field-label">Application Name <span class="req">*</span></label>
              <input class="input" id="f-name" placeholder="my-app" required autocomplete="off" />
            </div>

            <div class="field">
              <label class="field-label">GitHub Repository URL <span class="req">*</span></label>
              <div class="input-icon-wrap">
                <span class="icon">${icon.github}</span>
                <input class="input" id="f-repo" placeholder="https://github.com/user/repo" required />
              </div>
            </div>

            <div class="field">
              <label class="field-label">GitHub Token <span class="hint">(optional, for private repos)</span></label>
              <div class="input-icon-wrap">
                <span class="icon">${icon.lock}</span>
                <input class="input input-mono" id="f-token" type="password" placeholder="ghp_..." />
              </div>
            </div>
          </div>

          <!-- Domain & SSL -->
          <div class="modal-section">
            <div class="section-title">${icon.globe} Domain &amp; SSL</div>

            <div class="field">
              <label class="field-label">Domain Name <span class="hint">(optional)</span></label>
              <div class="input-icon-wrap">
                <span class="icon">${icon.globe}</span>
                <input class="input" id="f-domain" placeholder="myapp.example.com" />
              </div>
            </div>

            <div class="grid-2">
              <div class="field">
                <label class="field-label">SSL Certificate Path</label>
                <input class="input" id="f-cert" placeholder="/etc/ssl/certs/cert.pem" />
              </div>
              <div class="field">
                <label class="field-label">SSL Key Path</label>
                <input class="input" id="f-key" placeholder="/etc/ssl/private/key.pem" />
              </div>
            </div>
          </div>

          <!-- Process -->
          <div class="modal-section">
            <div class="section-title">${icon.settings} Process</div>
            <div class="grid-3-1">
              <div class="field">
                <label class="field-label">Start Command <span class="hint">(auto-detected if empty)</span></label>
                <input class="input input-mono" id="f-cmd" placeholder="npm start" />
              </div>
              <div class="field">
                <label class="field-label">Port</label>
                <input class="input" id="f-port" type="number" placeholder="3000" />
              </div>
            </div>
          </div>

          <!-- Env vars -->
          <div class="modal-section">
            <div class="section-title">${icon.lock} Environment Variables</div>
            <div id="env-rows"></div>
            <button type="button" class="add-env-btn" id="add-env">${icon.plus} Add variable</button>
          </div>

          <div id="modal-error" class="modal-error" style="display:none"></div>
        </div>

        <div class="modal-footer">
          <button type="button" class="btn btn-secondary" id="modal-cancel">Cancel</button>
          <button type="submit" class="btn btn-primary" id="modal-submit">${icon.play} Deploy Application</button>
        </div>
      </form>
    </div>`;
}

function addEnvRow(modal, idx) {
  const row = document.createElement('div');
  row.className = 'env-row';
  row.id = `env-row-${idx}`;
  row.innerHTML = `
    <input class="input input-mono" placeholder="KEY" data-env-key />
    <input class="input input-mono" placeholder="value" data-env-val />
    <button type="button" class="btn-remove" onclick="this.closest('.env-row').remove()">${icon.trash}</button>`;
  modal.querySelector('#env-rows').appendChild(row);
}

async function handleDeploy(modal, form, onSuccess, close) {
  const errEl  = modal.querySelector('#modal-error');
  const submit = modal.querySelector('#modal-submit');

  errEl.style.display = 'none';
  submit.disabled = true;
  submit.innerHTML = `${spinner} Deploying…`;

  const env_vars = {};
  modal.querySelectorAll('.env-row').forEach(row => {
    const k = row.querySelector('[data-env-key]').value.trim();
    const v = row.querySelector('[data-env-val]').value;
    if (k) env_vars[k] = v;
  });

  const payload = {
    name:         modal.querySelector('#f-name').value.trim(),
    repo_url:     modal.querySelector('#f-repo').value.trim(),
    github_token: modal.querySelector('#f-token').value.trim() || null,
    domain:       modal.querySelector('#f-domain').value.trim() || null,
    ssl_cert_path:modal.querySelector('#f-cert').value.trim() || null,
    ssl_key_path: modal.querySelector('#f-key').value.trim() || null,
    start_command:modal.querySelector('#f-cmd').value.trim() || null,
    port:         parseInt(modal.querySelector('#f-port').value) || null,
    env_vars,
  };

  if (!payload.name || !payload.repo_url) {
    errEl.textContent = 'Name and repository URL are required.';
    errEl.style.display = 'block';
    submit.disabled = false;
    submit.innerHTML = `${icon.play} Deploy Application`;
    return;
  }

  try {
    const app = await api.deploy(payload);
    close();
    onSuccess(app);
  } catch (err) {
    errEl.textContent = err.message;
    errEl.style.display = 'block';
    submit.disabled = false;
    submit.innerHTML = `${icon.play} Deploy Application`;
  }
}

