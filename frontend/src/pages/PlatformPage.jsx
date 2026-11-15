import { useState, useEffect, useCallback } from 'react';
import { Navigate } from 'react-router-dom';
import { apiFetchWithCount, apiFetch } from '../lib/api';
import { useAuth } from '../lib/auth';
import ConfirmDialog from '../components/ConfirmDialog';
import ErrorBanner from '../components/ErrorBanner';
import Loading from '../components/Loading';
import EmptyState from '../components/EmptyState';
import Pagination from '../components/Pagination';
import Card from '../components/ui/Card';
import PageHeader from '../components/ui/PageHeader';
import { ShieldCheck } from 'lucide-react';

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

  useEffect(() => {
    load();
  }, [load]);

  async function handlePlanChange() {
    const { ws, newPlan } = planConfirm;
    setPlanLoading(true);
    try {
      const updated = await apiFetch(`/admin/workspaces/${ws.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ plan: newPlan }),
      });
      setItems((prev) => (prev.map((w) => (w.id === ws.id ? { ...w, plan: updated.plan } : w))));
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
      setItems((prev) => (prev.map((w) => (w.id === ws.id ? { ...w, use_platform_providers: updated.use_platform_providers } : w))));
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
      <PageHeader
        title="Platform Admin"
        subtitle="Manage all tenant workspaces, subscription tiers, and provider routing across the instance."
      />

      {error && <ErrorBanner error={error} onRetry={load} />}

      {loading ? (
        <Loading text="Loading workspaces…" />
      ) : items.length === 0 ? (
        <EmptyState icon={ShieldCheck} title="No workspaces found" description="No tenant workspaces have been registered yet." />
      ) : (
        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-[#F5F5F4] text-[#78716C] border-b border-[#E7E5E4]">
                  <th className="px-4 py-3 text-left font-semibold text-[11px] uppercase tracking-wider">Name</th>
                  <th className="px-4 py-3 text-left font-semibold text-[11px] uppercase tracking-wider">Slug</th>
                  <th className="px-4 py-3 text-left font-semibold text-[11px] uppercase tracking-wider">Plan</th>
                  <th className="px-4 py-3 text-left font-semibold text-[11px] uppercase tracking-wider">Members</th>
                  <th className="px-4 py-3 text-left font-semibold text-[11px] uppercase tracking-wider">Platform Providers</th>
                  <th className="px-4 py-3 text-left font-semibold text-[11px] uppercase tracking-wider">Created</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#E7E5E4] bg-white">
                {items.map((ws) => (
                  <tr key={ws.id} className="hover:bg-[#FAFAF9] transition-colors">
                    <td className="px-4 py-3 text-[#1C1917] font-medium">{ws.name}</td>
                    <td className="px-4 py-3 text-[#78716C] font-mono text-[11px]">{ws.slug}</td>
                    <td className="px-4 py-3">
                      <select
                        value={ws.plan}
                        onChange={(e) => setPlanConfirm({ open: true, ws, newPlan: e.target.value })}
                        className="rounded-[6px] border border-[#E7E5E4] bg-white px-2.5 py-1 text-xs text-[#1C1917] focus:border-[#4F46E5] focus:outline-none"
                        aria-label={`Plan for ${ws.name}`}
                      >
                        {PLANS.map((p) => (
                          <option key={p} value={p}>
                            {p.charAt(0).toUpperCase() + p.slice(1)}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="px-4 py-3 text-[#44403C]">{ws.member_count}</td>
                    <td className="px-4 py-3">
                      <input
                        type="checkbox"
                        checked={ws.use_platform_providers}
                        onChange={(e) => setProviderConfirm({ open: true, ws, newValue: e.target.checked })}
                        className="rounded border-[#D6D3D1] text-[#4F46E5] focus:ring-[#4F46E5] cursor-pointer"
                        aria-label={`Platform providers for ${ws.name}`}
                      />
                    </td>
                    <td className="px-4 py-3 text-[#78716C]">
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
        </Card>
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
