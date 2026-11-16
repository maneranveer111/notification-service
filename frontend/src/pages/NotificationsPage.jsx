import { useState, useCallback, useEffect, useRef } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import {
  Bell,
  RotateCw,
  Search,
  X,
} from 'lucide-react';
import { listNotifications } from '../lib/api';
import { STATUSES, CHANNELS } from '../lib/constants';
import StatusBadge from '../components/StatusBadge';
import Pagination from '../components/Pagination';
import ErrorBanner from '../components/ErrorBanner';
import Loading from '../components/Loading';
import EmptyState from '../components/EmptyState';
import Button from '../components/ui/Button';
import Badge from '../components/ui/Badge';

function useDebounce(value, ms) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return debounced;
}

function fmt(d) {
  if (!d) return '—';
  return new Date(d).toLocaleString();
}

export default function NotificationsPage() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();

  const getParam = (k, def = '') => params.get(k) || def;

  const [status, setStatus] = useState(getParam('status'));
  const [channel, setChannel] = useState(getParam('channel'));
  const [recipientRaw, setRecipientRaw] = useState(getParam('recipient'));
  const batchId = getParam('batch_id');
  const [page, setPage] = useState(Number(getParam('page', '1')));
  const [pageSize, setPageSize] = useState(Number(getParam('limit', '25')));
  const [autoRefresh, setAutoRefresh] = useState(true);

  const recipient = useDebounce(recipientRaw, 400);

  const [data, setData] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const reqId = useRef(0);
  const intervalRef = useRef(null);

  const fetchData = useCallback(async () => {
    const id = ++reqId.current;
    try {
      const result = await listNotifications({
        status: status || undefined,
        channel: channel || undefined,
        recipient: recipient || undefined,
        batch_id: batchId || undefined,
        limit: pageSize,
        offset: (page - 1) * pageSize,
      });
      if (id !== reqId.current) return;
      setData(result.data);
      setTotal(result.total);
      setError(null);
    } catch (e) {
      if (id !== reqId.current) return;
      setError(e);
    } finally {
      if (id === reqId.current) setLoading(false);
    }
  }, [status, channel, recipient, batchId, page, pageSize]);

  useEffect(() => {
    setLoading(true);
    fetchData();
  }, [fetchData]);

  useEffect(() => {
    if (!autoRefresh) {
      clearInterval(intervalRef.current);
      return;
    }
    clearInterval(intervalRef.current);
    intervalRef.current = setInterval(() => {
      if (!document.hidden) fetchData();
    }, 5000);
    return () => clearInterval(intervalRef.current);
  }, [autoRefresh, fetchData]);

  // Sync URL params
  useEffect(() => {
    const next = new URLSearchParams();
    if (status) next.set('status', status);
    if (channel) next.set('channel', channel);
    if (recipient) next.set('recipient', recipient);
    if (batchId) next.set('batch_id', batchId);
    if (page > 1) next.set('page', page);
    if (pageSize !== 25) next.set('limit', pageSize);
    setParams(next, { replace: true });
  }, [status, channel, recipient, batchId, page, pageSize, setParams]);

  function resetPage() {
    setPage(1);
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-xl sm:text-2xl font-semibold text-[#1C1917] tracking-tight">
            Notifications
          </h1>
          <p className="text-xs sm:text-sm text-[#78716C] mt-0.5">
            Log of dispatched, scheduled, and retried messages across all channels.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-xs text-[#78716C] cursor-pointer select-none">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
              className="rounded border-[#E7E5E4] text-[#4F46E5] focus:ring-0"
            />
            Auto-refresh
          </label>
          <Button
            variant="secondary"
            size="sm"
            onClick={fetchData}
            icon={RotateCw}
          >
            Refresh
          </Button>
        </div>
      </div>

      {/* Batch filter active badge */}
      {batchId && (
        <div className="flex items-center gap-2">
          <Badge variant="accent" size="sm">
            <span>Batch: {batchId}</span>
            <button
              onClick={() => {
                setParams({});
                setPage(1);
              }}
              className="ml-1 hover:text-[#1C1917]"
              title="Clear batch filter"
            >
              <X className="w-3 h-3" />
            </button>
          </Badge>
        </div>
      )}

      {/* Filter Controls Row */}
      <div className="flex flex-wrap items-center gap-3 bg-white p-3 rounded-[8px] border border-[#E7E5E4] shadow-xs">
        <div className="w-40">
          <select
            value={status}
            onChange={(e) => {
              setStatus(e.target.value);
              resetPage();
            }}
            className="w-full bg-[#FAFAF9] border border-[#E7E5E4] rounded-[6px] px-2.5 py-1.5 text-xs text-[#1C1917] focus:outline-none focus:border-[#4F46E5] capitalize"
          >
            <option value="">All Statuses</option>
            {STATUSES.map((s) => (
              <option key={s} value={s} className="capitalize">
                {s}
              </option>
            ))}
          </select>
        </div>

        <div className="w-40">
          <select
            value={channel}
            onChange={(e) => {
              setChannel(e.target.value);
              resetPage();
            }}
            className="w-full bg-[#FAFAF9] border border-[#E7E5E4] rounded-[6px] px-2.5 py-1.5 text-xs text-[#1C1917] focus:outline-none focus:border-[#4F46E5] capitalize"
          >
            <option value="">All Channels</option>
            {CHANNELS.map((c) => (
              <option key={c} value={c} className="capitalize">
                {c}
              </option>
            ))}
          </select>
        </div>

        <div className="flex-1 min-w-[200px] relative">
          <input
            type="text"
            value={recipientRaw}
            onChange={(e) => {
              setRecipientRaw(e.target.value);
              resetPage();
            }}
            placeholder="Search recipient address or phone…"
            className="w-full bg-[#FAFAF9] border border-[#E7E5E4] rounded-[6px] pl-8 pr-3 py-1.5 text-xs text-[#1C1917] placeholder:text-[#A8A29E] focus:outline-none focus:border-[#4F46E5]"
          />
          <Search className="w-3.5 h-3.5 text-[#78716C] absolute left-2.5 top-1/2 -translate-y-1/2" />
        </div>
      </div>

      {error && <ErrorBanner error={error} onRetry={fetchData} />}

      {loading && data.length === 0 ? (
        <Loading text="Loading notifications…" />
      ) : data.length === 0 ? (
        <EmptyState
          icon={Bell}
          title="No notifications match"
          message="No notification events found for the selected criteria."
        />
      ) : (
        <div className="bg-white border border-[#E7E5E4] rounded-[8px] overflow-hidden shadow-xs">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs min-w-[700px]">
              <thead className="bg-[#FAFAF9] border-b border-[#E7E5E4] text-[11px] font-semibold text-[#78716C] uppercase tracking-wider">
                <tr>
                  <th className="px-5 py-3">Created</th>
                  <th className="px-5 py-3">Channel</th>
                  <th className="px-5 py-3">Recipient</th>
                  <th className="px-5 py-3">Status</th>
                  <th className="px-5 py-3">Attempts</th>
                  <th className="px-5 py-3">Provider</th>
                  <th className="px-5 py-3">Priority</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#E7E5E4]">
                {data.map((n) => (
                  <tr
                    key={n.id}
                    onClick={() => navigate(`/notifications/${n.id}`)}
                    className="hover:bg-[#FAFAF9]/60 cursor-pointer transition-colors h-[44px]"
                  >
                    <td className="px-5 py-3 text-[#78716C] whitespace-nowrap">
                      {fmt(n.created_at)}
                    </td>
                    <td className="px-5 py-3">
                      <Badge variant="neutral" size="sm">
                        <span className="capitalize">{n.channel}</span>
                      </Badge>
                    </td>
                    <td
                      className="px-5 py-3 font-medium text-[#1C1917] max-w-[180px] truncate"
                      title={n.recipient}
                    >
                      {n.recipient}
                    </td>
                    <td className="px-5 py-3">
                      <StatusBadge status={n.status} />
                    </td>
                    <td className="px-5 py-3 text-[#78716C]">
                      {n.attempt_count}/{n.max_attempts}
                    </td>
                    <td className="px-5 py-3 text-[#78716C] capitalize">
                      {n.provider || '—'}
                    </td>
                    <td className="px-5 py-3 text-[#78716C] capitalize">
                      {n.priority ?? 'normal'}
                    </td>
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
              onPageChange={setPage}
              onPageSizeChange={(s) => {
                setPageSize(s);
                setPage(1);
              }}
            />
          </div>
        </div>
      )}
    </div>
  );
}
