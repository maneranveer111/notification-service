import { useState, useEffect, useCallback } from 'react';
import {
  Ban,
  Plus,
} from 'lucide-react';
import { apiFetchWithCount, apiFetch } from '../../lib/api';
import { useAuth } from '../../lib/auth';
import ConfirmDialog from '../../components/ConfirmDialog';
import ErrorBanner from '../../components/ErrorBanner';
import Loading from '../../components/Loading';
import EmptyState from '../../components/EmptyState';
import Pagination from '../../components/Pagination';
import Button from '../../components/ui/Button';
import Input from '../../components/ui/Input';
import Select from '../../components/ui/Select';
import { EXAMPLE_PHONE } from '../../lib/examples';
import Card from '../../components/ui/Card';
import Badge from '../../components/ui/Badge';

const REASON_OPTIONS = [
  { value: 'opt_out', label: 'Opt-out (Unsubscribe)' },
  { value: 'bounce', label: 'Hard Bounce' },
];

export default function SuppressionsPage() {
  const { isAdmin } = useAuth();

  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [channelFilter, setChannelFilter] = useState('all');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [deleteConfirm, setDeleteConfirm] = useState({
    open: false,
    item: null,
  });
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
      const { data, total: t } = await apiFetchWithCount(
        `/suppressions?${qs.toString()}`
      );
      setItems(data);
      setTotal(t);
      setError(null);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, channelFilter]);

  useEffect(() => {
    load();
  }, [load]);

  function handleChannelFilterChange(val) {
    setChannelFilter(val);
    setPage(1);
  }

  function handlePageChange(p) {
    setPage(p);
  }
  function handlePageSizeChange(s) {
    setPageSize(s);
    setPage(1);
  }

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
      {/* Header with filter */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-base font-semibold text-[#1C1917]">
            Suppressions
          </h2>
          <p className="text-xs text-[#78716C] mt-0.5">
            Recipients blocked from receiving notifications due to opt-outs or delivery bounces.
          </p>
        </div>

        {/* Channel filter */}
        <div className="flex items-center gap-2">
          <span className="text-xs text-[#78716C]">Filter by:</span>
          <select
            id="channel-filter"
            value={channelFilter}
            onChange={(e) => handleChannelFilterChange(e.target.value)}
            className="bg-white border border-[#E7E5E4] rounded-[6px] px-2.5 py-1 text-xs text-[#1C1917] focus:outline-none focus:border-[#4F46E5]"
          >
            <option value="all">All Channels</option>
            <option value="email">Email</option>
            <option value="sms">SMS</option>
          </select>
        </div>
      </div>

      {/* Add form (admin only) */}
      {isAdmin && (
        <Card
          title="Add recipient to suppression list"
          subtitle="Manually suppress messages to a specific recipient address or phone number."
        >
          <form
            onSubmit={handleAdd}
            className="flex flex-col sm:flex-row items-stretch sm:items-end gap-3"
          >
            <div className="w-full sm:w-32">
              <Select
                id="add-channel"
                label="Channel"
                value={addChannel}
                onChange={(e) => setAddChannel(e.target.value)}
              >
                <option value="email">Email</option>
                <option value="sms">SMS</option>
              </Select>
            </div>
            <div className="flex-1 min-w-[200px]">
              <Input
                id="add-recipient"
                label="Recipient *"
                type="text"
                required
                value={addRecipient}
                onChange={(e) => setAddRecipient(e.target.value)}
                placeholder={
                  addChannel === 'email' ? 'user@example.com' : EXAMPLE_PHONE
                }
              />
            </div>
            <div className="w-full sm:w-44">
              <Select
                id="add-reason"
                label="Reason *"
                value={addReason}
                onChange={(e) => setAddReason(e.target.value)}
              >
                {REASON_OPTIONS.map((r) => (
                  <option key={r.value} value={r.value}>
                    {r.label}
                  </option>
                ))}
              </Select>
            </div>
            <Button
              type="submit"
              variant="primary"
              size="md"
              loading={addLoading}
              disabled={!addRecipient.trim()}
              icon={Plus}
            >
              Add
            </Button>
          </form>
          {addError && (
            <p className="text-xs text-[#B91C1C] mt-2">{addError}</p>
          )}
        </Card>
      )}

      {error && <ErrorBanner error={error} onRetry={load} />}

      {loading ? (
        <Loading text="Loading suppressions…" />
      ) : items.length === 0 ? (
        <EmptyState
          icon={Ban}
          title="No suppressions found"
          message="No addresses or numbers are currently suppressed in this workspace."
        />
      ) : (
        <div className="bg-white border border-[#E7E5E4] rounded-[8px] overflow-hidden shadow-xs">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs min-w-[600px]">
              <thead className="bg-[#FAFAF9] border-b border-[#E7E5E4] text-[11px] font-semibold text-[#78716C] uppercase tracking-wider">
                <tr>
                  <th className="px-5 py-3">Channel</th>
                  <th className="px-5 py-3">Recipient</th>
                  <th className="px-5 py-3">Reason</th>
                  <th className="px-5 py-3">Source</th>
                  <th className="px-5 py-3">Created</th>
                  {isAdmin && <th className="px-5 py-3 text-right">Actions</th>}
                </tr>
              </thead>
              <tbody className="divide-y divide-[#E7E5E4]">
                {items.map((item) => (
                  <tr
                    key={item.id}
                    className="hover:bg-[#FAFAF9]/60 transition-colors h-[44px]"
                  >
                    <td className="px-5 py-3">
                      <Badge variant="neutral" size="sm">
                        <span className="capitalize">{item.channel}</span>
                      </Badge>
                    </td>
                    <td className="px-5 py-3 font-mono text-[12px] text-[#1C1917]">
                      {item.recipient}
                    </td>
                    <td className="px-5 py-3">
                      <Badge
                        variant={item.reason === 'bounce' ? 'error' : 'warning'}
                        dot
                        size="sm"
                      >
                        {item.reason === 'opt_out' ? 'Opt-out' : item.reason}
                      </Badge>
                    </td>
                    <td className="px-5 py-3 capitalize text-[#78716C]">
                      {item.source || 'system'}
                    </td>
                    <td className="px-5 py-3 text-[#78716C]">
                      {new Date(item.created_at).toLocaleDateString()}
                    </td>
                    {isAdmin && (
                      <td className="px-5 py-3 text-right">
                        <Button
                          variant="ghost"
                          size="sm"
                          className="text-[#B91C1C] hover:text-[#991B1B] hover:bg-[#FEF2F2]"
                          onClick={() =>
                            setDeleteConfirm({ open: true, item })
                          }
                        >
                          Remove
                        </Button>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="p-3 bg-white">
            <Pagination
              total={total}
              page={page}
              pageSize={pageSize}
              onPageChange={handlePageChange}
              onPageSizeChange={handlePageSizeChange}
            />
          </div>
        </div>
      )}

      {/* Delete Confirmation */}
      <ConfirmDialog
        open={deleteConfirm.open}
        destructive
        title="Remove suppression?"
        message={`Remove suppression for "${deleteConfirm.item?.recipient}"? They will be eligible to receive notifications again.`}
        confirmLabel="Remove"
        loading={deleteLoading}
        onConfirm={handleDelete}
        onCancel={() => setDeleteConfirm({ open: false, item: null })}
      />
    </div>
  );
}
