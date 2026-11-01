const BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '');

export class ApiError extends Error {
  constructor(status, message, detail) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

function getToken() {
  return sessionStorage.getItem('token');
}

function formatDetail(detail) {
  if (!detail) return null;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((e) => {
        const field = e.loc ? e.loc.slice(1).join('.') : '';
        return field ? `${field}: ${e.msg}` : e.msg;
      })
      .join('; ');
  }
  return String(detail);
}

async function request(path, options = {}) {
  const token = getToken();
  const headers = { 'Content-Type': 'application/json', ...options.headers };
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const res = await fetch(`${BASE_URL}${path}`, { ...options, headers });

  if (res.status === 401 && path !== '/auth/login') {
    sessionStorage.removeItem('token');
    sessionStorage.removeItem('user');
    window.location.replace('/login');
    throw new ApiError(401, 'Session expired', null);
  }

  if (!res.ok) {
    let body = null;
    try { body = await res.json(); } catch (_) {}
    const detail = body?.detail;
    const message = formatDetail(detail) || body?.message || res.statusText;
    throw new ApiError(res.status, message, detail);
  }

  return res;
}

export async function login(email, password) {
  const res = await request('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  });
  return res.json();
}

export async function getMe() {
  const res = await request('/auth/me');
  return res.json();
}

export async function listNotifications(params = {}) {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') qs.set(k, v);
  }
  const res = await request(`/notifications?${qs.toString()}`);
  const data = await res.json();
  const total = parseInt(res.headers.get('X-Total-Count') || '0', 10);
  return { data, total };
}

export async function getNotification(id) {
  const res = await request(`/notifications/${id}`);
  return res.json();
}

export async function getNotificationTimeline(id) {
  const res = await request(`/notifications/${id}/timeline`);
  return res.json();
}

export async function retryNotification(id) {
  const res = await request(`/notifications/${id}/retry`, { method: 'POST', body: '{}' });
  return res.json();
}

export async function cancelNotification(id) {
  const res = await request(`/notifications/${id}/cancel`, { method: 'POST', body: '{}' });
  return res.json();
}

export async function getStatsOverview(windowHours = 24) {
  const res = await request(`/stats/overview?window_hours=${windowHours}`);
  return res.json();
}

export async function getStatsTimeseries(windowHours = 24, bucketHours = 1) {
  const res = await request(`/stats/timeseries?window_hours=${windowHours}&bucket_hours=${bucketHours}`);
  return res.json();
}

export async function sendEmail(payload, idempotencyKey = null) {
  const headers = {};
  if (idempotencyKey) headers['Idempotency-Key'] = idempotencyKey;
  const res = await request('/notifications/email', {
    method: 'POST',
    headers,
    body: JSON.stringify(payload),
  });
  return res.json();
}

export async function sendSMS(payload, idempotencyKey = null) {
  const headers = {};
  if (idempotencyKey) headers['Idempotency-Key'] = idempotencyKey;
  const res = await request('/notifications/sms', {
    method: 'POST',
    headers,
    body: JSON.stringify(payload),
  });
  return res.json();
}

export async function sendWebhook(payload, idempotencyKey = null) {
  const headers = {};
  if (idempotencyKey) headers['Idempotency-Key'] = idempotencyKey;
  const res = await request('/notifications/webhook', {
    method: 'POST',
    headers,
    body: JSON.stringify(payload),
  });
  return res.json();
}

export async function sendBulk(payload, idempotencyKey = null) {
  const headers = {};
  if (idempotencyKey) headers['Idempotency-Key'] = idempotencyKey;
  const res = await request('/notifications/bulk', {
    method: 'POST',
    headers,
    body: JSON.stringify(payload),
  });
  return res.json();
}

export async function getBatchStatus(batchId) {
  const res = await request(`/notifications/batches/${batchId}`);
  return res.json();
}

export async function listTemplates(params = {}) {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') qs.set(k, v);
  }
  const res = await request(`/templates?${qs.toString()}`);
  const data = await res.json();
  const total = parseInt(res.headers.get('X-Total-Count') || '0', 10);
  return { data, total };
}

export async function getTemplate(id) {
  const res = await request(`/templates/${id}`);
  return res.json();
}

export async function createTemplate(payload) {
  const res = await request('/templates', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  return res.json();
}

export async function updateTemplate(id, payload) {
  const res = await request(`/templates/${id}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
  return res.json();
}

export async function deleteTemplate(id) {
  await request(`/templates/${id}`, {
    method: 'DELETE',
  });
  return true;
}
