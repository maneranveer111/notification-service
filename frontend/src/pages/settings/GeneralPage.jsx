import { useState, useEffect, useCallback, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import { apiFetch } from '../../lib/api';
import { usePolling } from '../../lib/usePolling';
import { useAuth } from '../../lib/auth';
import ErrorBanner from '../../components/ErrorBanner';
import Loading from '../../components/Loading';

function planColor(plan) {
  if (plan === 'pro') return 'bg-blue-700 text-blue-100';
  if (plan === 'unlimited') return 'bg-purple-700 text-purple-100';
  return 'bg-gray-700 text-gray-300';
}

function UsageBar({ label, used, limit, resetsAt }) {
  const pct = limit ? Math.min(100, Math.round((used / limit) * 100)) : 0;
  const barColor =
    limit === null ? 'bg-green-500' :
    pct >= 100 ? 'bg-red-500' :
    pct >= 80 ? 'bg-amber-500' : 'bg-green-500';

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between text-sm">
        <span className="text-gray-300 font-medium">{label}</span>
        <span className="text-gray-400">
          {limit === null ? (
            <span className="text-green-400 font-medium">Unlimited</span>
          ) : (
            <span className={pct >= 100 ? 'text-red-400 font-medium' : pct >= 80 ? 'text-amber-400 font-medium' : 'text-gray-400'}>
              {used} / {limit}
            </span>
          )}
        </span>
      </div>
      <div className="h-2 bg-gray-700 rounded-full overflow-hidden">
        {limit !== null && (
          <div
            className={`h-2 rounded-full transition-all ${barColor}`}
            style={{ width: `${pct}%` }}
          />
        )}
      </div>
      {resetsAt && (
        <p className="text-xs text-gray-500">
          Resets {new Date(resetsAt).toLocaleString()}
        </p>
      )}
    </div>
  );
}

export default function GeneralPage() {
  const { isAdmin, refreshWorkspaces } = useAuth();
  const location = useLocation();
  const flash = location.state?.flash;

  const [workspace, setWorkspace] = useState(null);
  const [wsLoading, setWsLoading] = useState(true);
  const [wsError, setWsError] = useState(null);

  const [editing, setEditing] = useState(false);
  const [nameInput, setNameInput] = useState('');
  const [saveLoading, setSaveLoading] = useState(false);
  const [saveError, setSaveError] = useState(null);
  const inputRef = useRef(null);

  const usageFetch = useCallback(() => apiFetch('/usage'), []);
  const { data: usage, error: usageError, loading: usageLoading } = usePolling(usageFetch, { intervalMs: 30000 });

  useEffect(() => {
    setWsLoading(true);
    apiFetch('/workspaces/current')
      .then((d) => { setWorkspace(d); setWsLoading(false); })
      .catch((e) => { setWsError(e); setWsLoading(false); });
  }, []);

  useEffect(() => {
    if (editing && inputRef.current) inputRef.current.focus();
  }, [editing]);

  function startEdit() {
    setNameInput(workspace?.name ?? '');
    setSaveError(null);
    setEditing(true);
  }

  function cancelEdit() {
    setEditing(false);
    setSaveError(null);
  }

  async function saveName(e) {
    e.preventDefault();
    if (!nameInput.trim()) return;
    setSaveLoading(true);
    setSaveError(null);
    try {
      const updated = await apiFetch('/workspaces/current', {
        method: 'PATCH',
        body: JSON.stringify({ name: nameInput.trim() }),
      });
      setWorkspace(updated);
      setEditing(false);
      await refreshWorkspaces();
    } catch (err) {
      setSaveError(err?.detail || err?.message || 'Failed to save.');
    } finally {
      setSaveLoading(false);
    }
  }

  return (
    <div className="space-y-6 max-w-2xl">
      {flash && (
        <div className="px-4 py-3 rounded-lg bg-amber-900/30 border border-amber-700 text-amber-300 text-sm">
          ⚠ {flash}
        </div>
      )}

      {/* Workspace name */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 space-y-4">
        <h2 className="text-base font-semibold text-white">Workspace</h2>

        {wsLoading ? (
          <Loading text="Loading workspace…" />
        ) : wsError ? (
          <ErrorBanner error={wsError} />
        ) : editing ? (
          <form onSubmit={saveName} className="space-y-3">
            <div>
              <label htmlFor="ws-name-input" className="block text-sm font-medium text-gray-300 mb-1">
                Workspace name
              </label>
              <input
                id="ws-name-input"
                ref={inputRef}
                type="text"
                required
                value={nameInput}
                onChange={(e) => setNameInput(e.target.value)}
                className="w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 text-sm"
              />
            </div>
            {saveError && <p className="text-sm text-red-400">{saveError}</p>}
            <div className="flex gap-2">
              <button
                type="submit"
                disabled={saveLoading || !nameInput.trim()}
                className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm font-medium transition-colors"
              >
                {saveLoading ? 'Saving…' : 'Save'}
              </button>
              <button
                type="button"
                onClick={cancelEdit}
                disabled={saveLoading}
                className="px-4 py-2 rounded-lg bg-gray-700 hover:bg-gray-600 text-gray-300 text-sm font-medium transition-colors"
              >
                Cancel
              </button>
            </div>
          </form>
        ) : (
          <div className="flex items-center justify-between gap-3">
            <p className="text-white text-sm font-medium">{workspace?.name}</p>
            {isAdmin && (
              <button
                type="button"
                onClick={startEdit}
                className="px-3 py-1.5 text-xs rounded-lg bg-gray-700 hover:bg-gray-600 text-gray-300 transition-colors"
              >
                Edit
              </button>
            )}
          </div>
        )}
      </div>

      {/* Usage */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold text-white">Plan &amp; Usage</h2>
          {usage?.plan && (
            <span className={`text-xs px-2.5 py-1 rounded-full font-semibold uppercase tracking-wide ${planColor(usage.plan)}`}>
              {usage.plan}
            </span>
          )}
        </div>

        {usageLoading && !usage ? (
          <Loading text="Loading usage…" />
        ) : usageError ? (
          <ErrorBanner error={usageError} />
        ) : usage ? (
          <div className="space-y-5">
            <UsageBar
              label="Daily Sends"
              used={usage.daily?.used ?? 0}
              limit={usage.daily?.limit ?? null}
              resetsAt={usage.daily?.resets_at}
            />
            <UsageBar
              label="Monthly Sends"
              used={usage.monthly?.used ?? 0}
              limit={usage.monthly?.limit ?? null}
              resetsAt={usage.monthly?.resets_at}
            />
            <UsageBar
              label="API Keys"
              used={usage.api_keys?.used ?? 0}
              limit={usage.api_keys?.limit ?? null}
            />
            <UsageBar
              label="Members"
              used={usage.members?.used ?? 0}
              limit={usage.members?.limit ?? null}
            />
          </div>
        ) : null}

        <p className="text-xs text-gray-500 pt-1">
          Plans and limits are set by the service operator.
        </p>
      </div>
    </div>
  );
}
