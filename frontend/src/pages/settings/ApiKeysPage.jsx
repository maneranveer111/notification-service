import { useState, useEffect, useCallback } from 'react';
import { apiFetch } from '../../lib/api';
import { useAuth } from '../../lib/auth';
import { describeError } from '../../lib/errors';
import ConfirmDialog from '../../components/ConfirmDialog';
import ErrorBanner from '../../components/ErrorBanner';
import Loading from '../../components/Loading';
import EmptyState from '../../components/EmptyState';

const API_BASE = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '');

function OneTimeKeyDialog({ apiKey, onClose }) {
  const [copied, setCopied] = useState(false);

  function handleCopy() {
    navigator.clipboard.writeText(apiKey).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="bg-gray-900 border border-yellow-700 rounded-xl w-full max-w-md shadow-2xl p-6 space-y-4">
        <h2 className="text-lg font-semibold text-white">Save your API key</h2>

        <div className="px-4 py-3 rounded-lg bg-yellow-900/30 border border-yellow-700 text-yellow-300 text-sm">
          ⚠ This key will only be shown once. Copy it now and store it safely.
        </div>

        <div className="flex items-center gap-2">
          <code className="flex-1 text-sm text-green-300 bg-gray-800 px-3 py-2 rounded-lg font-mono break-all">
            {apiKey}
          </code>
          <button
            type="button"
            onClick={handleCopy}
            className="shrink-0 px-3 py-1.5 text-xs rounded-lg bg-gray-700 hover:bg-gray-600 text-gray-300 font-medium"
          >
            {copied ? 'Copied!' : 'Copy'}
          </button>
        </div>

        <button
          type="button"
          onClick={onClose}
          className="w-full px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium"
        >
          I saved the key
        </button>
      </div>
    </div>
  );
}

function CreateModal({ onClose, onCreated }) {
  const [name, setName] = useState('');
  const [rateLimit, setRateLimit] = useState('60');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!name.trim()) return;
    setLoading(true);
    setError(null);
    const body = { name: name.trim() };
    if (rateLimit !== '' && !isNaN(Number(rateLimit))) {
      body.rate_limit_per_minute = Number(rateLimit);
    }
    try {
      const res = await apiFetch('/admin/clients', {
        method: 'POST',
        body: JSON.stringify(body),
      });
      onCreated(res);
    } catch (err) {
      const desc = describeError(err);
      setError(desc.title + ': ' + desc.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="bg-gray-900 border border-gray-700 rounded-xl w-full max-w-sm shadow-2xl p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-white">Create API Key</h2>
          <button type="button" onClick={onClose} className="text-gray-400 hover:text-gray-200 text-xl" aria-label="Close">×</button>
        </div>

        {error && (
          <div className="px-4 py-3 rounded-lg bg-red-900/30 border border-red-700 text-red-300 text-sm">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="key-name" className="block text-sm font-medium text-gray-300 mb-1">
              Name *
            </label>
            <input
              id="key-name"
              type="text"
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 text-sm"
              placeholder="My integration"
              autoFocus
            />
          </div>
          <div>
            <label htmlFor="key-rate-limit" className="block text-sm font-medium text-gray-300 mb-1">
              Rate limit per minute (optional)
            </label>
            <input
              id="key-rate-limit"
              type="number"
              min="1"
              value={rateLimit}
              onChange={(e) => setRateLimit(e.target.value)}
              className="w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 text-sm"
              placeholder="60"
            />
          </div>
          <div className="flex gap-3 pt-1">
            <button type="button" onClick={onClose} disabled={loading} className="flex-1 px-4 py-2 rounded-lg bg-gray-700 hover:bg-gray-600 disabled:opacity-50 text-gray-300 text-sm font-medium">
              Cancel
            </button>
            <button type="submit" disabled={loading || !name.trim()} className="flex-1 px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm font-medium">
              {loading ? 'Creating…' : 'Create'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function UsageModal({ clientId, onClose }) {
  const [usage, setUsage] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    apiFetch(`/admin/clients/${clientId}/usage`)
      .then((d) => { setUsage(d); setLoading(false); })
      .catch((e) => { setError(e); setLoading(false); });
  }, [clientId]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="bg-gray-900 border border-gray-700 rounded-xl w-full max-w-sm shadow-2xl p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-white">Key Usage</h2>
          <button type="button" onClick={onClose} className="text-gray-400 hover:text-gray-200 text-xl" aria-label="Close">×</button>
        </div>

        {loading ? (
          <Loading text="Loading usage…" />
        ) : error ? (
          <ErrorBanner error={error} />
        ) : usage ? (
          <div className="space-y-3">
            <div className="flex justify-between text-sm">
              <span className="text-gray-400">Total requests</span>
              <span className="text-white font-medium">{usage.total}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-gray-400">Last 24 hours</span>
              <span className="text-white font-medium">{usage.last_24_hours}</span>
            </div>
            {usage.by_status && Object.keys(usage.by_status).length > 0 && (
              <div className="border-t border-gray-800 pt-3 space-y-1">
                <p className="text-xs text-gray-500 uppercase tracking-wide mb-2">By status</p>
                {Object.entries(usage.by_status).map(([status, count]) => (
                  <div key={status} className="flex justify-between text-sm">
                    <span className="text-gray-400 capitalize">{status}</span>
                    <span className="text-white">{count}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        ) : null}

        <button type="button" onClick={onClose} className="w-full px-4 py-2 rounded-lg bg-gray-700 hover:bg-gray-600 text-gray-300 text-sm font-medium">
          Close
        </button>
      </div>
    </div>
  );
}

const curlExample = `curl -X POST ${API_BASE}/notifications/email \\
  -H "X-API-Key: <your-key>" \\
  -H "Content-Type: application/json" \\
  -d '{"recipient":"user@example.com","subject":"Hello","body":"World"}'`;

const templateExample = `curl -X POST ${API_BASE}/notifications/email \\
  -H "X-API-Key: <your-key>" \\
  -H "Content-Type: application/json" \\
  -H "Idempotency-Key: unique-request-id" \\
  -d '{"recipient":"user@example.com","template_id":"tmpl_xxx","variables":{"name":"Alice"}}'`;

function HowToUseBox() {
  const [copiedCurl, setCopiedCurl] = useState(false);
  const [copiedTemplate, setCopiedTemplate] = useState(false);

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 space-y-4">
      <h3 className="font-semibold text-white">How to use</h3>

      <div className="space-y-2">
        <p className="text-sm text-gray-400">Basic email send:</p>
        <div className="relative">
          <pre className="bg-gray-800 text-green-300 text-xs rounded-lg p-3 overflow-x-auto whitespace-pre-wrap break-all">
            {curlExample}
          </pre>
          <button
            type="button"
            onClick={() => navigator.clipboard.writeText(curlExample).then(() => { setCopiedCurl(true); setTimeout(() => setCopiedCurl(false), 2000); })}
            className="absolute top-2 right-2 px-2 py-1 rounded bg-gray-700 hover:bg-gray-600 text-gray-300 text-xs"
          >
            {copiedCurl ? 'Copied!' : 'Copy'}
          </button>
        </div>
      </div>

      <div className="space-y-2">
        <p className="text-sm text-gray-400">With template + idempotency key:</p>
        <div className="relative">
          <pre className="bg-gray-800 text-green-300 text-xs rounded-lg p-3 overflow-x-auto whitespace-pre-wrap break-all">
            {templateExample}
          </pre>
          <button
            type="button"
            onClick={() => navigator.clipboard.writeText(templateExample).then(() => { setCopiedTemplate(true); setTimeout(() => setCopiedTemplate(false), 2000); })}
            className="absolute top-2 right-2 px-2 py-1 rounded bg-gray-700 hover:bg-gray-600 text-gray-300 text-xs"
          >
            {copiedTemplate ? 'Copied!' : 'Copy'}
          </button>
        </div>
      </div>

      <p className="text-xs text-gray-500">
        Add an <code className="text-gray-300">Idempotency-Key</code> header with a unique ID per request to safely retry without duplicates.
      </p>
    </div>
  );
}

export default function ApiKeysPage() {
  const { isAdmin } = useAuth();
  const [clients, setClients] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [showCreate, setShowCreate] = useState(false);
  const [oneTimeKey, setOneTimeKey] = useState(null);
  const [rotateConfirm, setRotateConfirm] = useState({ open: false, client: null });
  const [rotateLoading, setRotateLoading] = useState(false);
  const [revokeConfirm, setRevokeConfirm] = useState({ open: false, client: null });
  const [revokeLoading, setRevokeLoading] = useState(false);
  const [usageModal, setUsageModal] = useState({ open: false, clientId: null });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiFetch('/admin/clients');
      setClients(data);
      setError(null);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  function handleCreated(res) {
    setShowCreate(false);
    setOneTimeKey(res.api_key);
    load();
  }

  async function handleRotate() {
    const id = rotateConfirm.client?.id;
    setRotateLoading(true);
    try {
      const res = await apiFetch(`/admin/clients/${id}/rotate`, { method: 'POST' });
      setRotateConfirm({ open: false, client: null });
      setOneTimeKey(res.api_key);
      load();
    } catch (e) {
      setError(e);
    } finally {
      setRotateLoading(false);
    }
  }

  async function handleRevoke() {
    const id = revokeConfirm.client?.id;
    setRevokeLoading(true);
    try {
      await apiFetch(`/admin/clients/${id}/revoke`, { method: 'POST' });
      setRevokeConfirm({ open: false, client: null });
      load();
    } catch (e) {
      setError(e);
    } finally {
      setRevokeLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-base font-semibold text-white">API Keys</h2>
        {isAdmin && (
          <button
            type="button"
            onClick={() => setShowCreate(true)}
            className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium transition-colors"
          >
            + Create key
          </button>
        )}
      </div>

      {error && <ErrorBanner error={error} onRetry={load} />}

      {loading ? (
        <Loading text="Loading keys…" />
      ) : clients.length === 0 ? (
        <EmptyState message="No API keys yet. Create one to start integrating." />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm min-w-[700px]">
            <thead>
              <tr className="text-left text-xs text-gray-400 uppercase tracking-wide border-b border-gray-800">
                <th className="pb-3 pr-4">Name</th>
                <th className="pb-3 pr-4">Key Prefix</th>
                <th className="pb-3 pr-4">Status</th>
                <th className="pb-3 pr-4">Rate limit/min</th>
                <th className="pb-3 pr-4">Last used</th>
                <th className="pb-3 pr-4">Created</th>
                {isAdmin && <th className="pb-3">Actions</th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800">
              {clients.map((client) => (
                <tr key={client.id} className="text-gray-300">
                  <td className="py-3 pr-4 font-medium text-white">{client.name}</td>
                  <td className="py-3 pr-4">
                    <code className="text-xs bg-gray-800 px-2 py-0.5 rounded text-green-300">{client.key_prefix}…</code>
                  </td>
                  <td className="py-3 pr-4">
                    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                      client.is_active
                        ? 'bg-green-800 text-green-200'
                        : 'bg-red-900 text-red-300'
                    }`}>
                      {client.is_active ? 'Active' : 'Revoked'}
                    </span>
                  </td>
                  <td className="py-3 pr-4">{client.rate_limit_per_minute ?? '—'}</td>
                  <td className="py-3 pr-4 text-gray-400">
                    {client.last_used_at ? new Date(client.last_used_at).toLocaleString() : '—'}
                  </td>
                  <td className="py-3 pr-4 text-gray-400">
                    {new Date(client.created_at).toLocaleDateString()}
                  </td>
                  {isAdmin && (
                    <td className="py-3">
                      <div className="flex items-center gap-2 flex-wrap">
                        <button
                          type="button"
                          onClick={() => setUsageModal({ open: true, clientId: client.id })}
                          className="px-2 py-1 text-xs rounded bg-gray-700 hover:bg-gray-600 text-gray-300"
                        >
                          Usage
                        </button>
                        {client.is_active && (
                          <>
                            <button
                              type="button"
                              onClick={() => setRotateConfirm({ open: true, client })}
                              className="px-2 py-1 text-xs rounded bg-amber-800 hover:bg-amber-700 text-amber-200"
                            >
                              Rotate
                            </button>
                            <button
                              type="button"
                              onClick={() => setRevokeConfirm({ open: true, client })}
                              className="px-2 py-1 text-xs rounded bg-red-900 hover:bg-red-800 text-red-200"
                            >
                              Revoke
                            </button>
                          </>
                        )}
                      </div>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <HowToUseBox />

      {showCreate && (
        <CreateModal
          onClose={() => setShowCreate(false)}
          onCreated={handleCreated}
        />
      )}

      {oneTimeKey && (
        <OneTimeKeyDialog
          apiKey={oneTimeKey}
          onClose={() => setOneTimeKey(null)}
        />
      )}

      <ConfirmDialog
        open={rotateConfirm.open}
        title="Rotate API key?"
        message={`A new key will be issued for "${rotateConfirm.client?.name}". The existing key stops working immediately.`}
        confirmLabel="Rotate"
        loading={rotateLoading}
        onConfirm={handleRotate}
        onCancel={() => setRotateConfirm({ open: false, client: null })}
      />

      <ConfirmDialog
        open={revokeConfirm.open}
        title="Revoke API key?"
        message={`"${revokeConfirm.client?.name}" will be permanently revoked. This cannot be undone.`}
        confirmLabel="Revoke"
        loading={revokeLoading}
        onConfirm={handleRevoke}
        onCancel={() => setRevokeConfirm({ open: false, client: null })}
      />

      {usageModal.open && (
        <UsageModal
          clientId={usageModal.clientId}
          onClose={() => setUsageModal({ open: false, clientId: null })}
        />
      )}
    </div>
  );
}
