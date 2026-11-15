import { useState, useEffect, useCallback, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import { apiFetch } from '../../lib/api';
import { usePolling } from '../../lib/usePolling';
import { useAuth } from '../../lib/auth';
import ErrorBanner from '../../components/ErrorBanner';
import Loading from '../../components/Loading';
import Button from '../../components/ui/Button';
import Input from '../../components/ui/Input';
import Card from '../../components/ui/Card';
import Badge from '../../components/ui/Badge';

function UsageRow({ label, used = 0, limit = null, resetsAt }) {
  const isUnlimited = limit === null;
  const pct = isUnlimited ? 0 : Math.min(100, Math.round((used / limit) * 100));

  return (
    <div className="space-y-1.5 py-3 first:pt-0 last:pb-0">
      <div className="flex items-center justify-between text-xs">
        <span className="font-medium text-[#1C1917]">{label}</span>
        <span className="text-[#78716C]">
          <strong className="text-[#1C1917]">{used.toLocaleString()}</strong>{' '}
          {isUnlimited ? (
            <span className="text-[#15803D] font-medium">(Unlimited)</span>
          ) : (
            `of ${limit.toLocaleString()}`
          )}
        </span>
      </div>
      {!isUnlimited && (
        <div className="h-1.5 w-full bg-[#F5F5F4] rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all ${
              pct >= 100 ? 'bg-[#B91C1C]' : pct >= 80 ? 'bg-[#A16207]' : 'bg-[#4F46E5]'
            }`}
            style={{ width: `${pct}%` }}
          />
        </div>
      )}
      {resetsAt && (
        <p className="text-[11px] text-[#A8A29E]">
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
  const {
    data: usage,
    error: usageError,
    loading: usageLoading,
  } = usePolling(usageFetch, { intervalMs: 30000 });

  useEffect(() => {
    setWsLoading(true);
    apiFetch('/workspaces/current')
      .then((d) => {
        setWorkspace(d);
        setNameInput(d.name || '');
        setWsLoading(false);
      })
      .catch((e) => {
        setWsError(e);
        setWsLoading(false);
      });
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
    <div className="space-y-6">
      {flash && (
        <div className="px-3.5 py-2.5 rounded-[6px] bg-[#FEFCE8] border border-[#FEF08A] text-[#A16207] text-xs">
          {flash}
        </div>
      )}

      {/* Workspace Profile Card */}
      <Card
        title="Workspace Profile"
        subtitle="General details and identification for this workspace."
      >
        {wsLoading ? (
          <Loading text="Loading workspace…" />
        ) : wsError ? (
          <ErrorBanner error={wsError} />
        ) : editing ? (
          <form onSubmit={saveName} className="space-y-4 max-w-md">
            <Input
              id="ws-name-input"
              ref={inputRef}
              label="Workspace Name"
              type="text"
              required
              value={nameInput}
              onChange={(e) => setNameInput(e.target.value)}
              placeholder="e.g. Acme Corp"
              error={saveError}
            />
            <div className="flex gap-2">
              <Button
                type="submit"
                variant="primary"
                size="sm"
                loading={saveLoading}
                disabled={!nameInput.trim()}
              >
                Save Changes
              </Button>
              <Button
                type="button"
                variant="secondary"
                size="sm"
                onClick={cancelEdit}
                disabled={saveLoading}
              >
                Cancel
              </Button>
            </div>
          </form>
        ) : (
          <div className="space-y-4">
            <div className="flex items-center justify-between py-2 border-b border-[#E7E5E4]">
              <div>
                <p className="text-xs text-[#78716C]">Workspace Name</p>
                <p className="text-sm font-semibold text-[#1C1917] mt-0.5">
                  {workspace?.name}
                </p>
              </div>
              {isAdmin && (
                <Button variant="secondary" size="sm" onClick={startEdit}>
                  Edit
                </Button>
              )}
            </div>

            {workspace?.slug && (
              <div className="flex items-center justify-between py-2">
                <div>
                  <p className="text-xs text-[#78716C]">Workspace Slug</p>
                  <p className="text-xs font-mono text-[#1C1917] mt-0.5">
                    {workspace.slug}
                  </p>
                </div>
              </div>
            )}
          </div>
        )}
      </Card>

      {/* Plan & Usage Card */}
      <Card
        title="Plan & Usage"
        subtitle="Resource consumption and limits for this workspace."
        action={
          usage?.plan && (
            <Badge
              variant={
                usage.plan === 'unlimited'
                  ? 'success'
                  : usage.plan === 'pro'
                  ? 'accent'
                  : 'neutral'
              }
              size="md"
            >
              {usage.plan.toUpperCase()}
            </Badge>
          )
        }
      >
        {usageLoading && !usage ? (
          <Loading text="Loading usage…" />
        ) : usageError ? (
          <ErrorBanner error={usageError} />
        ) : usage ? (
          <div className="divide-y divide-[#E7E5E4]">
            <UsageRow
              label="Daily Sends"
              used={usage.daily?.used ?? 0}
              limit={usage.daily?.limit ?? null}
              resetsAt={usage.daily?.resets_at}
            />
            <UsageRow
              label="Monthly Sends"
              used={usage.monthly?.used ?? 0}
              limit={usage.monthly?.limit ?? null}
              resetsAt={usage.monthly?.resets_at}
            />
            <UsageRow
              label="API Keys"
              used={usage.api_keys?.used ?? 0}
              limit={usage.api_keys?.limit ?? null}
            />
            <UsageRow
              label="Team Members"
              used={usage.members?.used ?? 0}
              limit={usage.members?.limit ?? null}
            />
          </div>
        ) : null}

        <p className="text-[11px] text-[#A8A29E] mt-4 pt-3 border-t border-[#E7E5E4]">
          Plans and quotas are managed by your service operator.
        </p>
      </Card>
    </div>
  );
}
