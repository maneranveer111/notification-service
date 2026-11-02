import { useState, useEffect, useCallback } from 'react';
import { apiFetchWithCount, apiFetch } from '../../lib/api';
import { useAuth } from '../../lib/auth';
import ConfirmDialog from '../../components/ConfirmDialog';
import ErrorBanner from '../../components/ErrorBanner';
import Loading from '../../components/Loading';
import EmptyState from '../../components/EmptyState';
import Pagination from '../../components/Pagination';

const REASON_OPTIONS = ['opt_out', 'bounce', 'complaint', 'manual'];

export default function SuppressionsPage() {
  const { isAdmin } = useAuth();

  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [channelFilter, setChannelFilter] = useState('all');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [deleteConfirm, setDeleteConfirm] = useState({ open: false, item: null });
  const [deleteLoading, setDeleteLoading] = useState(false);

  // Add form
  const [addChannel, setAddChannel] = useState('email');
  const [addRecipient, setAddRecipient] = useState('');
  const [addReason, setAddReason] = useState('opt_out');
  const [addLoading, setAddLoading] = useState(false);
  const [addError, setAddError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const qs = new URLSearchParams({
        limit: String(pageSize),
        offset: String((page - 1) * pageSize),
      });
      if (channelFilter !== 'all') qs.set('channel', channelFilter);
      const { data, total: t } = await apiFetchWithCount(`/suppressions?${qs.toString()}`);
      setItems(data);
      setTotal(t);
      setError(null);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, channelFilter]);

  useEffect(() => { load(); }, [load]);

  function handleChannelFilterChange(val) {
    setChannelFilter(val);
    setPage(1);
  }

  function handlePageChange(p) { setPage(p); }
  function handlePageSizeChange(s) { setPageSize(s); setPage(1); }

  async function handleDelete() {
    const item = deleteConfirm.item;
    setDeleteLoading(true);
    try {
      await apiFetch(`/suppressions/${item.id}`, { method: 'DELETE' });
      setDeleteConfirm({ open: false, item: null });
      load();
    } catch (e) {
      setError(e);
      setDeleteConfirm({ open: false, item: null });
    } finally {
      setDeleteLoading(false);
    }
  }

  async function handleAdd(e) {
    e.preventDefault();
    if (!addRecipient.trim()) return;
    setAddLoading(true);
    setAddError(null);
    try {
      await apiFetch('/suppressions', {
        method: 'POST',
        body: JSON.stringify({
          channel: addChannel,
          recipient: addRecipient.trim(),
          reason: addReason,
        }),
      });
      setAddRecipient('');
      setAddReason('opt_out');
      load();
    } catch (err) {
      setAddError(err?.detail || err?.message || 'Failed to add suppression.');
    } finally {
      setAddLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-base font-semibold text-white flex-1">Suppressions</h2>
        {/* Channel filter */}
        <div className="flex items-center gap-2">
          <label htmlFor="channel-filter" className="text-sm text-gray-400">Channel:</label>
          <select
            id="channel-filter"
            value={channelFilter}
            onChange={(e) => handleChannelFilterChange(e.target.value)}
            className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-gray-200 focus:outline-none focus:border-blue-500"
          >
            <option value="all">All</option>
            <option value="email">Email</option>
            <option value="sms">SMS</option>
          </select>
        </div>
      </div>

      {/* Add form (admin only) */}
      {isAdmin && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 space-y-3">
          <h3 className="text-sm font-medium text-gray-300">Add suppression</h3>
          <form onSubmit={handleAdd} className="flex flex-wrap gap-3 items-end">
            <div>
              <label htmlFor="add-channel" className="block text-xs text-gray-400 mb-1">Channel</label>
              <select
                id="add-channel"
                value={addChannel}
                onChange={(e) => setAddChannel(e.target.value)}
                className="px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 text-gray-200 text-sm focus:outline-none focus:border-blue-500"
              >
                <option value="email">Email</option>
                <option value="sms">SMS</option>
              </select>
            </div>
            <div className="flex-1 min-w-[180px]">
              <label htmlFor="add-recipient" className="block text-xs text-gray-400 mb-1">
                Recipient *
              </label>
              <input
                id="add-recipient"
                type="text"
                required
                value={addRecipient}
                onChange={(e) => setAddRecipient(e.target.value)}
                className="w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 text-sm"
                placeholder={addChannel === 'email' ? 'user@example.com' : '+12125550100'}
              />
            </div>
            <div>
              <label htmlFor="add-reason" className="block text-xs text-gray-400 mb-1">Reason *</label>
              <select
                id="add-reason"
                value={addReason}
                onChange={(e) => setAddReason(e.target.value)}
                className="px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 text-gray-200 text-sm focus:outline-none focus:border-blue-500"
              >
                {REASON_OPTIONS.map((r) => (
                  <option key={r} value={r}>{r}</option>
                ))}
              </select>
            </div>
            <button
              type="submit"
              disabled={addLoading || !addRecipient.trim()}
              className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm font-medium"
            >
              {addLoading ? 'Adding…' : 'Add'}
            </button>
          </form>
          {addError && <p className="text-sm text-red-400">{addError}</p>}
        </div>
      )}

      {error && <ErrorBanner error={error} onRetry={load} />}

      {loading ? (
        <Loading text="Loading suppressions…" />
      ) : items.length === 0 ? (
        <EmptyState message="No suppressions found." />
      ) : (
        <div className="space-y-4">
          <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[600px]">
              <thead>
                <tr className="text-left text-xs text-gray-400 uppercase tracking-wide border-b border-gray-800">
                  <th className="pb-3 pr-4">Channel</th>
                  <th className="pb-3 pr-4">Recipient</th>
                  <th className="pb-3 pr-4">Reason</th>
                  <th className="pb-3 pr-4">Source</th>
                  <th className="pb-3 pr-4">Created</th>
                  {isAdmin && <th className="pb-3">Actions</th>}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800">
                {items.map((item) => (
                  <tr key={item.id} className="text-gray-300">
                    <td className="py-3 pr-4 capitalize">{item.channel}</td>
                    <td className="py-3 pr-4">{item.recipient}</td>
                    <td className="py-3 pr-4 capitalize">{item.reason || '—'}</td>
                    <td className="py-3 pr-4 capitalize text-gray-400">{item.source || '—'}</td>
                    <td className="py-3 pr-4 text-gray-400">
                      {new Date(item.created_at).toLocaleString()}
                    </td>
                    {isAdmin && (
                      <td className="py-3">
                        <button
                          type="button"
                          onClick={() => setDeleteConfirm({ open: true, item })}
                          className="px-2 py-1 text-xs rounded bg-red-900 hover:bg-red-800 text-red-200"
                        >
                          Delete
                        </button>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <Pagination
            total={total}
            page={page}
            pageSize={pageSize}
            onPageChange={handlePageChange}
            onPageSizeChange={handlePageSizeChange}
          />
        </div>
      )}

      <p className="text-xs text-gray-500">
        Suppressions prevent messages from being sent to specific recipients. They are applied automatically on bounce or unsubscribe events, or can be added manually.
      </p>

      <ConfirmDialog
        open={deleteConfirm.open}
        title="Delete suppression?"
        message={`Remove suppression for "${deleteConfirm.item?.recipient}"? They may receive messages again.`}
        confirmLabel="Delete"
        loading={deleteLoading}
        onConfirm={handleDelete}
        onCancel={() => setDeleteConfirm({ open: false, item: null })}
      />
    </div>
  );
}
