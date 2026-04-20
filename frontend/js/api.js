const BASE = '/api';

function redirectToLogin() {
  const next = encodeURIComponent(location.pathname + location.search);
  location.href = `/login.html?next=${next}`;
}

async function request(method, path, body) {
  const opts = { method, headers: {}, credentials: 'same-origin' };
  if (body) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(BASE + path, opts);
  if (res.status === 401) { redirectToLogin(); return; }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
  return data;
}

export const api = {
  health:        ()          => request('GET',    '/health'),
  checkAuth:     ()          => request('GET',    '/auth/check'),
  logout:        ()          => request('POST',   '/auth/logout'),
  changePassword:(newPwd)    => request('POST',   '/auth/change-password', { password: newPwd }),
  listApps: ()         => request('GET',    '/apps'),
  getApp:   (id)       => request('GET',    `/apps/${id}`),
  deploy:   (payload)  => request('POST',   '/apps', payload),
  updateApp:(id, data) => request('PUT',    `/apps/${id}`, data),
  deleteApp:(id)       => request('DELETE', `/apps/${id}`),
  start:    (id)       => request('POST',   `/apps/${id}/start`),
  stop:     (id)       => request('POST',   `/apps/${id}/stop`),
  restart:  (id)       => request('POST',   `/apps/${id}/restart`),
  pull:     (id)       => request('POST',   `/apps/${id}/pull`),
  installDeps:(id)     => request('POST',   `/apps/${id}/install-deps`),
  getStats: (id)       => request('GET',    `/apps/${id}/stats`),
  listFiles:(id, path) => request('GET',    `/apps/${id}/files?path=${encodeURIComponent(path || '')}`),
  fileContent:(id, p)  => request('GET',    `/apps/${id}/files/content?path=${encodeURIComponent(p)}`),
  serviceFile:()       => request('GET',    '/apps/system/service-file'),
  discoverCerts:()     => request('GET',    '/apps/system/certs'),
  discoverAppCerts:(id)=> request('GET',    `/apps/${id}/certs`),
  uploadSystemCert: (file) => {
    const fd = new FormData(); fd.append('file', file);
    return fetch(BASE + '/system/certs/upload', { method: 'POST', body: fd, credentials: 'same-origin' })
      .then(r => { if (r.status === 401) { redirectToLogin(); return; } return r.json().then(d => { if (!r.ok) throw new Error(d.detail || `HTTP ${r.status}`); return d; }); });
  },
  uploadAppCert: (id, file) => {
    const fd = new FormData(); fd.append('file', file);
    return fetch(BASE + `/apps/${id}/certs/upload`, { method: 'POST', body: fd, credentials: 'same-origin' })
      .then(r => { if (r.status === 401) { redirectToLogin(); return; } return r.json().then(d => { if (!r.ok) throw new Error(d.detail || `HTTP ${r.status}`); return d; }); });
  },
  getNginxConfig: (id) => request('GET',    `/apps/${id}/nginx-config`),
  saveNginxConfig:(id, content) => request('PUT', `/apps/${id}/nginx-config`, { content }),
  getPDManagerNginx: () => request('GET',  '/system/nginx-config'),
  applyPDManagerNginx:(data)    => request('POST', '/system/nginx-config', data),
};

export function wsLogs(appId, onLine) {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const ws = new WebSocket(`${proto}//${location.host}/ws/apps/${appId}/logs`);
  ws.onmessage = e => onLine(e.data);
  return ws;
}

export function wsStats(appId, onData) {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const ws = new WebSocket(`${proto}//${location.host}/ws/apps/${appId}/stats`);
  ws.onmessage = e => onData(JSON.parse(e.data));
  return ws;
}

export function wsSystemStats(onData) {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const ws = new WebSocket(`${proto}//${location.host}/ws/system/stats`);
  ws.onmessage = e => onData(JSON.parse(e.data));
  return ws;
}
