import { useState, useEffect, useCallback } from 'react';
import {
  Key,
  Plus,
  Copy,
  Check,
  X,
} from 'lucide-react';
import { apiFetch, absoluteApiBase } from '../../lib/api';
import { useAuth } from '../../lib/auth';
import { describeError } from '../../lib/errors';
import ConfirmDialog from '../../components/ConfirmDialog';
import ErrorBanner from '../../components/ErrorBanner';
import Loading from '../../components/Loading';
import EmptyState from '../../components/EmptyState';
import Button from '../../components/ui/Button';
import Input from '../../components/ui/Input';
import Badge from '../../components/ui/Badge';

function OneTimeKeyDialog({ apiKey, onClose }) {
  const [copied, setCopied] = useState(false);

  function handleCopy() {
    navigator.clipboard.writeText(apiKey).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="bg-white border border-[#E7E5E4] rounded-[12px] w-full max-w-md shadow-xl p-6 space-y-4">
        <div className="flex items-start gap-3">
          <div className="w-8 h-8 rounded-full bg-[#FEFCE8] border border-[#FEF08A] flex items-center justify-center text-[#A16207] shrink-0 mt-0.5">
            <Key className="w-4 h-4" strokeWidth={1.5} />
          </div>
          <div>
            <h2 className="text-base font-semibold text-[#1C1917]">
              Save your API key
            </h2>
            <p className="text-xs text-[#78716C] mt-0.5">
              This secret key is only shown once. Store it in a secure environment variable.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <code className="flex-1 text-xs font-mono text-[#1C1917] bg-[#FAFAF9] border border-[#E7E5E4] px-3 py-2 rounded-[6px] break-all select-all">
            {apiKey}
          </code>
          <Button
            variant="secondary"
            size="sm"
            onClick={handleCopy}
            icon={copied ? Check : Copy}
          >
            {copied ? 'Copied' : 'Copy'}
          </Button>
        </div>

        <Button
          variant="primary"
          size="sm"
          className="w-full"
          onClick={onClose}
        >
          I have stored this key
        </Button>
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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="bg-white border border-[#E7E5E4] rounded-[12px] w-full max-w-sm shadow-xl p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold text-[#1C1917]">
            Generate API Key
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded text-[#78716C] hover:text-[#1C1917]"
          >
            <X className="w-4 h-4" strokeWidth={1.5} />
          </button>
        </div>

        {error && (
          <div className="px-3.5 py-2.5 rounded-[6px] bg-[#FEF2F2] border border-[#FECACA] text-[#B91C1C] text-xs">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <Input
            id="key-name"
            label="Key Name *"
            type="text"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Production Backend"
            autoFocus
          />
          <Input
            id="key-rate-limit"
            label="Rate Limit per Minute"
            type="number"
            min="1"
            value={rateLimit}
            onChange={(e) => setRateLimit(e.target.value)}
            placeholder="60"
            helper="Default is 60 requests/minute per client key."
          />
          <div className="flex gap-2.5 pt-1">
            <Button
              variant="secondary"
              size="sm"
              className="flex-1"
              onClick={onClose}
              disabled={loading}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              variant="primary"
              size="sm"
              className="flex-1"
              loading={loading}
              disabled={!name.trim()}
            >
              Generate
            </Button>
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
      .then((d) => {
        setUsage(d);
        setLoading(false);
      })
      .catch((e) => {
        setError(e);
        setLoading(false);
      });
  }, [clientId]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="bg-white border border-[#E7E5E4] rounded-[12px] w-full max-w-sm shadow-xl p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold text-[#1C1917]">
            API Key Usage
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded text-[#78716C] hover:text-[#1C1917]"
          >
            <X className="w-4 h-4" strokeWidth={1.5} />
          </button>
        </div>

        {loading ? (
          <Loading text="Loading usage…" />
        ) : error ? (
          <ErrorBanner error={error} />
        ) : usage ? (
          <div className="space-y-3">
            <div className="flex justify-between py-1.5 border-b border-[#E7E5E4] text-xs">
              <span className="text-[#78716C]">Total Requests</span>
              <span className="font-semibold text-[#1C1917]">
                {usage.total?.toLocaleString() ?? 0}
              </span>
            </div>
            <div className="flex justify-between py-1.5 border-b border-[#E7E5E4] text-xs">
              <span className="text-[#78716C]">Last 24 Hours</span>
              <span className="font-semibold text-[#1C1917]">
                {usage.last_24_hours?.toLocaleString() ?? 0}
              </span>
            </div>
            {usage.by_status && Object.keys(usage.by_status).length > 0 && (
              <div className="pt-2 space-y-1.5">
                <p className="text-[11px] font-semibold text-[#78716C] uppercase tracking-wider">
                  By Status
                </p>
                {Object.entries(usage.by_status).map(([status, count]) => (
                  <div key={status} className="flex justify-between text-xs">
                    <span className="text-[#78716C] capitalize">{status}</span>
                    <span className="font-medium text-[#1C1917]">{count}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        ) : null}

        <Button
          variant="secondary"
          size="sm"
          className="w-full"
          onClick={onClose}
        >
          Close
        </Button>
      </div>
    </div>
  );
}

function CodeIntegrationSnippet() {
  const [activeTab, setActiveTab] = useState('curl');
  const [copied, setCopied] = useState(false);
  const API_BASE = absoluteApiBase();

  const snippets = {
    curl: `curl -X POST ${API_BASE}/notifications/email \\
  -H "X-API-Key: YOUR_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "recipient": "user@example.com",
    "subject": "Order Confirmed",
    "body": "Thank you for your order."
  }'`,
    node: `import fetch from 'node-fetch';

const res = await fetch('${API_BASE}/notifications/email', {
  method: 'POST',
  headers: {
    'X-API-Key': process.env.NOTIFY_API_KEY,
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    recipient: 'user@example.com',
    subject: 'Order Confirmed',
    body: 'Thank you for your order.',
  }),
});
const data = await res.json();
console.log(data);`,
    python: `import requests

res = requests.post(
    "${API_BASE}/notifications/email",
    headers={
        "X-API-Key": "YOUR_API_KEY",
        "Content-Type": "application/json",
    },
    json={
        "recipient": "user@example.com",
        "subject": "Order Confirmed",
        "body": "Thank you for your order.",
    },
)
print(res.json())`,
  };

  const code = snippets[activeTab];

  function handleCopy() {
    navigator.clipboard.writeText(code).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  return (
    <div className="bg-[#18181B] border border-[#27272A] rounded-[8px] overflow-hidden text-xs">
      {/* Header with tabs */}
      <div className="flex items-center justify-between px-3 py-2 bg-[#27272A]/50 border-b border-[#27272A]">
        <div className="flex items-center gap-1">
          {['curl', 'node', 'python'].map((tab) => (
            <button
              key={tab}
              type="button"
              onClick={() => setActiveTab(tab)}
              className={`px-2.5 py-1 rounded-[4px] font-mono text-[11px] font-medium transition-colors cursor-pointer ${
                activeTab === tab
                  ? 'bg-[#3F3F46] text-white'
                  : 'text-[#A1A1AA] hover:text-[#D4D4D8] hover:bg-[#27272A]'
              }`}
            >
              {tab === 'curl' ? 'cURL' : tab === 'node' ? 'Node.js' : 'Python'}
            </button>
          ))}
        </div>
        <button
          type="button"
          onClick={handleCopy}
          className="flex items-center gap-1.5 px-2 py-1 rounded-[4px] bg-[#27272A] hover:bg-[#3F3F46] text-[#D4D4D8] transition-colors text-[11px]"
        >
          {copied ? (
            <>
              <Check className="w-3.5 h-3.5 text-emerald-400" strokeWidth={2} />
              <span className="text-emerald-400">Copied</span>
            </>
          ) : (
            <>
              <Copy className="w-3.5 h-3.5" strokeWidth={1.5} />
              <span>Copy</span>
            </>
          )}
        </button>
      </div>

      <div className="p-4 overflow-x-auto font-mono text-[#E4E4E7] leading-relaxed">
        <pre className="whitespace-pre">{code}</pre>
      </div>
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
  const [rotateConfirm, setRotateConfirm] = useState({
    open: false,
    client: null,
  });
  const [rotateLoading, setRotateLoading] = useState(false);
  const [revokeConfirm, setRevokeConfirm] = useState({
    open: false,
    client: null,
  });
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

  useEffect(() => {
    load();
  }, [load]);

  function handleCreated(res) {
    setShowCreate(false);
    setOneTimeKey(res.api_key);
    load();
  }

  async function handleRotate() {
    const id = rotateConfirm.client?.id;
    setRotateLoading(true);
    try {
      const res = await apiFetch(`/admin/clients/${id}/rotate`, {
        method: 'POST',
      });
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
      {/* Header */}
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-[#1C1917]">API Keys</h2>
          <p className="text-xs text-[#78716C] mt-0.5">
            Authenticate programmatic dispatch via the REST API.
          </p>
        </div>
        {isAdmin && (
          <Button
            variant="primary"
            size="sm"
            onClick={() => setShowCreate(true)}
            icon={Plus}
          >
            Generate Key
          </Button>
        )}
      </div>

      {error && <ErrorBanner error={error} onRetry={load} />}

      {loading ? (
        <Loading text="Loading keys…" />
      ) : clients.length === 0 ? (
        <EmptyState
          icon={Key}
          title="No API keys"
          message="Generate an API key to authenticate requests from your backend microservices."
          action={
            isAdmin && (
              <Button
                variant="primary"
                size="sm"
                onClick={() => setShowCreate(true)}
                icon={Plus}
              >
                Generate First Key
              </Button>
            )
          }
        />
      ) : (
        <div className="bg-white border border-[#E7E5E4] rounded-[8px] overflow-hidden shadow-xs">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs min-w-[700px]">
              <thead className="bg-[#FAFAF9] border-b border-[#E7E5E4] text-[11px] font-semibold text-[#78716C] uppercase tracking-wider">
                <tr>
                  <th className="px-5 py-3">Name</th>
                  <th className="px-5 py-3">Prefix</th>
                  <th className="px-5 py-3">Status</th>
                  <th className="px-5 py-3">Rate Limit</th>
                  <th className="px-5 py-3">Last Used</th>
                  <th className="px-5 py-3">Created</th>
                  {isAdmin && <th className="px-5 py-3 text-right">Actions</th>}
                </tr>
              </thead>
              <tbody className="divide-y divide-[#E7E5E4]">
                {clients.map((client) => (
                  <tr
                    key={client.id}
                    className="hover:bg-[#FAFAF9]/60 transition-colors h-[44px]"
                  >
                    <td className="px-5 py-3 font-medium text-[#1C1917]">
                      {client.name}
                    </td>
                    <td className="px-5 py-3 font-mono text-[11px] text-[#78716C]">
                      <span className="bg-[#F5F5F4] px-1.5 py-0.5 rounded border border-[#E7E5E4]">
                        {client.key_prefix}••••
                      </span>
                    </td>
                    <td className="px-5 py-3">
                      <Badge
                        variant={client.is_active ? 'success' : 'error'}
                        dot
                        size="sm"
                      >
                        {client.is_active ? 'Active' : 'Revoked'}
                      </Badge>
                    </td>
                    <td className="px-5 py-3 text-[#78716C]">
                      {client.rate_limit_per_minute
                        ? `${client.rate_limit_per_minute}/min`
                        : 'Default'}
                    </td>
                    <td className="px-5 py-3 text-[#78716C]">
                      {client.last_used_at
                        ? new Date(client.last_used_at).toLocaleDateString()
                        : 'Never'}
                    </td>
                    <td className="px-5 py-3 text-[#78716C]">
                      {new Date(client.created_at).toLocaleDateString()}
                    </td>
                    {isAdmin && (
                      <td className="px-5 py-3 text-right">
                        <div className="flex items-center justify-end gap-1.5">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() =>
                              setUsageModal({ open: true, clientId: client.id })
                            }
                          >
                            Usage
                          </Button>
                          {client.is_active && (
                            <>
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() =>
                                  setRotateConfirm({ open: true, client })
                                }
                              >
                                Rotate
                              </Button>
                              <Button
                                variant="ghost"
                                size="sm"
                                className="text-[#B91C1C] hover:text-[#991B1B] hover:bg-[#FEF2F2]"
                                onClick={() =>
                                  setRevokeConfirm({ open: true, client })
                                }
                              >
                                Revoke
                              </Button>
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
        </div>
      )}

      {/* Integration Code Snippet Card */}
      <div className="space-y-2">
        <h3 className="text-sm font-semibold text-[#1C1917]">
          Quickstart Code Examples
        </h3>
        <p className="text-xs text-[#78716C]">
          Dispatch notifications directly through standard HTTP clients or your preferred programming language.
        </p>
        <CodeIntegrationSnippet />
      </div>

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
        destructive
        title="Rotate API key?"
        message={`A new key will be generated for "${rotateConfirm.client?.name}". The existing secret stops working immediately.`}
        confirmLabel="Rotate"
        loading={rotateLoading}
        onConfirm={handleRotate}
        onCancel={() => setRotateConfirm({ open: false, client: null })}
      />

      <ConfirmDialog
        open={revokeConfirm.open}
        destructive
        title="Revoke API key?"
        message={`"${revokeConfirm.client?.name}" will be permanently deactivated. Any backend calls using it will fail.`}
        confirmLabel="Revoke Key"
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
