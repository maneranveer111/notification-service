// ---------------------------------------------------------------------------
// Runtime config helper — reads window.__APP_CONFIG__ first so the base URL
// can be overridden at deploy time without rebuilding the bundle.
// ---------------------------------------------------------------------------
export function absoluteApiBase() {
  return (window.__APP_CONFIG__?.API_BASE_URL || import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '');
}

function _base() { return absoluteApiBase(); }

// ---------------------------------------------------------------------------
// ApiError
// ---------------------------------------------------------------------------
export class ApiError extends Error {
  constructor(message, status, body) {
    super(message);
    this.status = status;
    this.code = body?.code ?? null;
    this.detail = body?.detail ?? null;
  }
}

// ---------------------------------------------------------------------------
// Module-level config cache
// ---------------------------------------------------------------------------
let _configCache = null;

// ---------------------------------------------------------------------------
// Auth-exempt paths — no auto-logout on 401
// ---------------------------------------------------------------------------
const AUTH_EXEMPT = [
  'login',
  'signup',
  'verify-email',
  'resend-verification',
  'forgot-password',
  'reset-password',
  'accept-invitation',
];

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------
function _autoLogout() {
  sessionStorage.removeItem('token');
  sessionStorage.removeItem('user');
  sessionStorage.removeItem('workspace');
  sessionStorage.removeItem('workspaces');
  sessionStorage.removeItem('isSuperadmin');
  window.location = '/login';
}

// ---------------------------------------------------------------------------
// Core fetch wrapper
// ---------------------------------------------------------------------------
export async function apiFetch(path, options = {}) {
  const { _raw, ...opts } = options;
  const token = sessionStorage.getItem('token');
  const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const url = `${_base()}${path}`;

  let response;
  try {
    response = await fetch(url, { ...opts, headers });
  } catch (e) {
    throw new ApiError('Network error', null, null);
  }

  if (response.status === 401) {
    const exempt = AUTH_EXEMPT.some(p => path.includes(p));
    if (!exempt) {
      _autoLogout();
      throw new ApiError('Unauthorized', 401, null);
    }
  }

  let body = null;
  try { body = await response.json(); } catch (_) {}

  if (!response.ok) {
    const msg = body?.detail
      ? (Array.isArray(body.detail) ? JSON.stringify(body.detail) : body.detail)
      : response.statusText;
    throw new ApiError(msg, response.status, body);
  }

  if (_raw) return { data: body, response };
  return body;
}

// ---------------------------------------------------------------------------
// Fetch wrapper that also returns X-Total-Count
// ---------------------------------------------------------------------------
export async function apiFetchWithCount(path, options = {}) {
  const { data, response } = await apiFetch(path, { ...options, _raw: true });
  const total = parseInt(response.headers.get('X-Total-Count') || '0', 10);
  return { data, total };
}

// ---------------------------------------------------------------------------
// Public config (fresh or in-memory cached)
// ---------------------------------------------------------------------------
export async function getPublicConfig(forceFresh = false) {
  if (_configCache && !forceFresh) return _configCache;
  const cfg = await apiFetch('/public/config');
  _configCache = cfg;
  return cfg;
}

// ---------------------------------------------------------------------------
// Legacy helpers (kept for backward compatibility)
// ---------------------------------------------------------------------------
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

/**
 * Internal legacy request helper — wraps apiFetch and returns the raw Response
 * so that the existing callers that do `res.json()` or `res.headers.get(...)` continue to work.
 */
async function request(path, options = {}) {
  const { _raw, ...opts } = options;
  const token = sessionStorage.getItem('token');
  const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const url = `${_base()}${path}`;

  let res;
  try {
    res = await fetch(url, { ...opts, headers });
  } catch (e) {
    throw new ApiError('Network error', null, null);
  }

  if (res.status === 401) {
    const exempt = AUTH_EXEMPT.some(p => path.includes(p));
    if (!exempt) {
      _autoLogout();
      throw new ApiError('Unauthorized', 401, null);
    }
  }

  if (!res.ok) {
    let body = null;
    try { body = await res.clone().json(); } catch (_) {}
    const detail = body?.detail;
    const message = formatDetail(detail) || body?.message || res.statusText;
    throw new ApiError(message, res.status, body);
  }

  return res;
}

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------
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

// ---------------------------------------------------------------------------
// Notifications
// ---------------------------------------------------------------------------
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

// ---------------------------------------------------------------------------
// Stats
// ---------------------------------------------------------------------------
export async function getStatsOverview(windowHours = 24) {
  const res = await request(`/stats/overview?window_hours=${windowHours}`);
  return res.json();
}

export async function getStatsTimeseries(windowHours = 24, bucketHours = 1) {
  const res = await request(`/stats/timeseries?window_hours=${windowHours}&bucket_hours=${bucketHours}`);
  return res.json();
}

// ---------------------------------------------------------------------------
// Send helpers
// ---------------------------------------------------------------------------
export async function sendEmail(payload, idempotencyKey = null) {
  const headers = {};
  if (idempotencyKey) headers['Idempotency-Key'] = idempotencyKey;
  const res = await request('/notifications/email', { method: 'POST', headers, body: JSON.stringify(payload) });
  return res.json();
}

export async function sendSMS(payload, idempotencyKey = null) {
  const headers = {};
  if (idempotencyKey) headers['Idempotency-Key'] = idempotencyKey;
  const res = await request('/notifications/sms', { method: 'POST', headers, body: JSON.stringify(payload) });
  return res.json();
}

export async function sendWebhook(payload, idempotencyKey = null) {
  const headers = {};
  if (idempotencyKey) headers['Idempotency-Key'] = idempotencyKey;
  const res = await request('/notifications/webhook', { method: 'POST', headers, body: JSON.stringify(payload) });
  return res.json();
}

export async function sendBulk(payload, idempotencyKey = null) {
  const headers = {};
  if (idempotencyKey) headers['Idempotency-Key'] = idempotencyKey;
  const res = await request('/notifications/bulk', { method: 'POST', headers, body: JSON.stringify(payload) });
  return res.json();
}

export async function getBatchStatus(batchId) {
  const res = await request(`/notifications/batches/${batchId}`);
  return res.json();
}

// ---------------------------------------------------------------------------
// Templates
// ---------------------------------------------------------------------------
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
  const res = await request('/templates', { method: 'POST', body: JSON.stringify(payload) });
  return res.json();
}

export async function updateTemplate(id, payload) {
  const res = await request(`/templates/${id}`, { method: 'PUT', body: JSON.stringify(payload) });
  return res.json();
}

export async function deleteTemplate(id) {
  await request(`/templates/${id}`, { method: 'DELETE' });
  return true;
}
