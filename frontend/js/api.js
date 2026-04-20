const BASE = '/api';

async function request(method, path, body) {
  const opts = { method, headers: {} };
  if (body) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(BASE + path, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
  return data;
}

export const api = {
  health:   ()         => request('GET',    '/health'),
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
