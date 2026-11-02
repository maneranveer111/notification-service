import { useState, useEffect, useCallback } from 'react';
import { Navigate } from 'react-router-dom';
import { apiFetchWithCount, apiFetch } from '../lib/api';
import { useAuth } from '../lib/auth';
import ConfirmDialog from '../components/ConfirmDialog';
import ErrorBanner from '../components/ErrorBanner';
import Loading from '../components/Loading';
import EmptyState from '../components/EmptyState';
import Pagination from '../components/Pagination';

const PLANS = ['free', 'pro', 'unlimited'];

export default function PlatformPage() {
  const { isSuperadmin } = useAuth();

  if (!isSuperadmin) {
    return <Navigate to="/" replace />;
  }

  return <PlatformContent />;
}

function PlatformContent() {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(25);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Plan confirm
  const [planConfirm, setPlanConfirm] = useState({ open: false, ws: null, newPlan: null });
  const [planLoading, setPlanLoading] = useState(false);

  // Provider toggle confirm
  const [providerConfirm, setProviderConfirm] = useState({ open: false, ws: null, newValue: null });
  const [providerLoading, setProviderLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const offset = (page - 1) * pageSize;
      const { data, total: t } = await apiFetchWithCount(`/admin/workspaces?limit=${pageSize}&offset=${offset}`);
      setItems(data);
      setTotal(t);
      setError(null);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, [page, pageSize]);

  useEffect(() => { load(); }, [load]);

  async function handlePlanChange() {
    const { ws, newPlan } = planConfirm;
    setPlanLoading(true);
    try {
      const updated = await apiFetch(`/admin/workspaces/${ws.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ plan: newPlan }),
      });
      setItems((prev) => prev.map((w) => w.id === ws.id ? { ...w, plan: updated.plan } : w));
      setPlanConfirm({ open: false, ws: null, newPlan: null });
    } catch (e) {
      setError(e);
      setPlanConfirm({ open: false, ws: null, newPlan: null });
    } finally {
      setPlanLoading(false);
    }
  }

  async function handleProviderToggle() {
    const { ws, newValue } = providerConfirm;
    setProviderLoading(true);
    try {
      const updated = await apiFetch(`/admin/workspaces/${ws.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ use_platform_providers: newValue }),
      });
      setItems((prev) => prev.map((w) => w.id === ws.id ? { ...w, use_platform_providers: updated.use_platform_providers } : w));
      setProviderConfirm({ open: false, ws: null, newValue: null });
    } catch (e) {
      setError(e);
      setProviderConfirm({ open: false, ws: null, newValue: null });
    } finally {
      setProviderLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-bold text-white">Platform Admin</h1>

      {error && <ErrorBanner error={error} onRetry={load} />}

      {loading ? (
        <Loading text="Loading workspaces…" />
      ) : items.length === 0 ? (
        <EmptyState message="No workspaces found." />
      ) : (
        <div className="space-y-4">
          <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[800px]">
              <thead>
                <tr className="text-left text-xs text-gray-400 uppercase tracking-wide border-b border-gray-800">
                  <th className="pb-3 pr-4">Name</th>
                  <th className="pb-3 pr-4">Slug</th>
                  <th className="pb-3 pr-4">Plan</th>
                  <th className="pb-3 pr-4">Members</th>
                  <th className="pb-3 pr-4">Platform providers</th>
                  <th className="pb-3">Created</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800">
                {items.map((ws) => (
                  <tr key={ws.id} className="text-gray-300">
                    <td className="py-3 pr-4 text-white font-medium">{ws.name}</td>
                    <td className="py-3 pr-4 text-gray-400 font-mono text-xs">{ws.slug}</td>
                    <td className="py-3 pr-4">
                      <select
                        value={ws.plan}
                        onChange={(e) => setPlanConfirm({ open: true, ws, newPlan: e.target.value })}
                        className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-sm text-gray-200 focus:outline-none focus:border-blue-500"
                        aria-label={`Plan for ${ws.name}`}
                      >
                        {PLANS.map((p) => (
                          <option key={p} value={p}>{p}</option>
                        ))}
                      </select>
                    </td>
                    <td className="py-3 pr-4">{ws.member_count}</td>
                    <td className="py-3 pr-4">
                      <input
                        type="checkbox"
                        checked={ws.use_platform_providers}
                        onChange={(e) => setProviderConfirm({ open: true, ws, newValue: e.target.checked })}
                        className="rounded border-gray-600 bg-gray-800 text-blue-500 cursor-pointer"
                        aria-label={`Platform providers for ${ws.name}`}
                      />
                    </td>
                    <td className="py-3 text-gray-400">
                      {new Date(ws.created_at).toLocaleDateString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <Pagination
            total={total}
            page={page}
            pageSize={pageSize}
            onPageChange={(p) => setPage(p)}
            onPageSizeChange={() => {}}
          />
        </div>
      )}

      <ConfirmDialog
        open={planConfirm.open}
        title={`Change plan for "${planConfirm.ws?.name}"?`}
        message={`Set plan to "${planConfirm.newPlan}"?`}
        confirmLabel="Change plan"
        loading={planLoading}
        onConfirm={handlePlanChange}
        onCancel={() => setPlanConfirm({ open: false, ws: null, newPlan: null })}
      />

      <ConfirmDialog
        open={providerConfirm.open}
        title={`${providerConfirm.newValue ? 'Enable' : 'Disable'} platform providers?`}
        message={
          providerConfirm.newValue
            ? `"${providerConfirm.ws?.name}" will send through your platform provider accounts and at your cost.`
            : `"${providerConfirm.ws?.name}" will use its own provider accounts.`
        }
        confirmLabel="Confirm"
        loading={providerLoading}
        onConfirm={handleProviderToggle}
        onCancel={() => setProviderConfirm({ open: false, ws: null, newValue: null })}
      />
    </div>
  );
}
