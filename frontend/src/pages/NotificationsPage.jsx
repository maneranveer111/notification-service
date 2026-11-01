import { useState, useCallback, useEffect, useRef } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { listNotifications } from '../lib/api';
import { STATUSES, CHANNELS } from '../lib/constants';
import StatusBadge from '../components/StatusBadge';
import Pagination from '../components/Pagination';
import ErrorBanner from '../components/ErrorBanner';
import Loading from '../components/Loading';
import EmptyState from '../components/EmptyState';

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
  const [lastUpdated, setLastUpdated] = useState(null);
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
      setLastUpdated(new Date());
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
    if (!autoRefresh) { clearInterval(intervalRef.current); return; }
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

  function resetPage() { setPage(1); }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-bold">Notifications</h1>
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-1.5 text-sm text-gray-400">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
              className="rounded"
            />
            Auto-refresh
          </label>
          <button
            onClick={fetchData}
            className="px-3 py-1.5 text-sm rounded-lg bg-gray-800 hover:bg-gray-700 border border-gray-700 text-gray-300"
          >
            Refresh
          </button>
        </div>
      </div>

      {lastUpdated && (
        <p className="text-xs text-gray-500">Last updated: {lastUpdated.toLocaleTimeString()}</p>
      )}

      {/* Batch chip */}
      {batchId && (
        <div className="flex items-center gap-2">
          <span className="text-xs bg-blue-900/30 border border-blue-700 text-blue-300 px-3 py-1 rounded-full">
            Batch: {batchId}
          </span>
          <button
            onClick={() => { setParams({}); setPage(1); }}
            className="text-xs text-gray-500 hover:text-gray-300"
          >
            ✕ Clear
          </button>
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <select
          value={status}
          onChange={(e) => { setStatus(e.target.value); resetPage(); }}
          className="bg-gray-800 border border-gray-600 rounded-lg px-3 py-1.5 text-sm text-gray-200"
        >
          <option value="">All statuses</option>
          {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <select
          value={channel}
          onChange={(e) => { setChannel(e.target.value); resetPage(); }}
          className="bg-gray-800 border border-gray-600 rounded-lg px-3 py-1.5 text-sm text-gray-200"
        >
          <option value="">All channels</option>
          {CHANNELS.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
        <input
          type="text"
          value={recipientRaw}
          onChange={(e) => { setRecipientRaw(e.target.value); resetPage(); }}
          placeholder="Filter by recipient…"
          className="bg-gray-800 border border-gray-600 rounded-lg px-3 py-1.5 text-sm text-gray-200 min-w-48"
        />
      </div>

      <ErrorBanner error={error} onRetry={fetchData} />

      {loading && data.length === 0 ? (
        <Loading />
      ) : data.length === 0 ? (
        <EmptyState message="No notifications match your filters." />
      ) : (
        <>
          <div className="overflow-x-auto rounded-xl border border-gray-800">
            <table className="w-full text-sm">
              <thead className="bg-gray-900 text-gray-400 text-left">
                <tr>
                  {['Created', 'Channel', 'Recipient', 'Status', 'Attempts', 'Provider', 'Priority'].map((h) => (
                    <th key={h} className="px-4 py-3 font-medium whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800">
                {data.map((n) => (
                  <tr
                    key={n.id}
                    onClick={() => navigate(`/notifications/${n.id}`)}
                    className="bg-gray-950 hover:bg-gray-900 cursor-pointer transition-colors"
                  >
                    <td className="px-4 py-3 whitespace-nowrap text-gray-400 text-xs">{fmt(n.created_at)}</td>
                    <td className="px-4 py-3 capitalize">{n.channel}</td>
                    <td className="px-4 py-3 max-w-[160px] truncate text-gray-300" title={n.recipient}>{n.recipient}</td>
                    <td className="px-4 py-3"><StatusBadge status={n.status} /></td>
                    <td className="px-4 py-3 text-gray-400">{n.attempt_count}/{n.max_attempts}</td>
                    <td className="px-4 py-3 text-gray-400">{n.provider || '—'}</td>
                    <td className="px-4 py-3 text-gray-400">{n.priority ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination
            total={total}
            page={page}
            pageSize={pageSize}
            onPageChange={setPage}
            onPageSizeChange={(s) => { setPageSize(s); setPage(1); }}
          />
        </>
      )}
    </div>
  );
}

