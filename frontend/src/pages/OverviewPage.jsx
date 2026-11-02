import { useState, useCallback, useEffect } from 'react';
import { useLocation, Link } from 'react-router-dom';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend,
} from 'recharts';
import { usePolling } from '../lib/usePolling';
import { getStatsOverview, getStatsTimeseries, apiFetch, apiFetchWithCount } from '../lib/api';
import { POLL_INTERVAL_MS } from '../lib/constants';
import { useAuth } from '../lib/auth';
import ErrorBanner from '../components/ErrorBanner';
import Loading from '../components/Loading';

const WINDOWS = [
  { label: '6 h', hours: 6, bucketHours: 1 },
  { label: '24 h', hours: 24, bucketHours: 1 },
  { label: '7 d', hours: 168, bucketHours: 24 },
];

function StatCard({ label, value, sub, color = 'blue' }) {
  const colors = {
    blue: 'text-blue-400', green: 'text-emerald-400', red: 'text-red-400', yellow: 'text-yellow-400',
  };
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
      <p className="text-xs text-gray-400 uppercase tracking-wide mb-1">{label}</p>
      <p className={`text-3xl font-bold ${colors[color] || colors.blue}`}>{value ?? '—'}</p>
      {sub && <p className="text-xs text-gray-500 mt-1">{sub}</p>}
    </div>
  );
}

function fmt(d) {
  if (!d) return '';
  const date = new Date(d);
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

export default function OverviewPage() {
  const location = useLocation();
  const flash = location.state?.flash;
  const [winIdx, setWinIdx] = useState(1);
  const win = WINDOWS[winIdx];

  // ── Onboarding checklist ─────────────────────────────────────────────────
  const { workspace, isAdmin } = useAuth();
  const dismissedKey = `onboarding_dismissed:${workspace?.id}`;
  const [dismissed, setDismissed] = useState(() => localStorage.getItem(dismissedKey) === '1');
  const [checks, setChecks] = useState({ provider: false, notification: false, apiKey: false });
  const [expanded, setExpanded] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!isAdmin || dismissed) return;
    Promise.allSettled([
      apiFetch('/providers').then((d) => d.length > 0),
      apiFetchWithCount('/notifications?limit=1').then(({ total }) => total > 0),
      apiFetch('/admin/clients').then((d) => d.length > 0),
    ]).then(([p, n, a]) => {
      setChecks({
        provider: p.status === 'fulfilled' && p.value,
        notification: n.status === 'fulfilled' && n.value,
        apiKey: a.status === 'fulfilled' && a.value,
      });
    });
  }, [workspace?.id, isAdmin, dismissed]);

  const allDone = checks.provider && checks.notification && checks.apiKey;
  const completedCount = Object.values(checks).filter(Boolean).length;

  const apiBase = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '');
  const curlExample = `curl -X POST ${apiBase}/notifications/email \\
  -H "Authorization: Bearer YOUR_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{"recipient":"user@example.com","subject":"Hello","body":"World"}'`;

  function handleCopy() {
    navigator.clipboard.writeText(curlExample).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  const STEPS = [
    {
      label: 'Connect an email provider',
      done: checks.provider,
      link: '/settings/providers',
      linkLabel: 'Go to Providers',
    },
    {
      label: 'Send a test email',
      done: checks.notification,
      link: '/send',
      linkLabel: 'Send a notification',
    },
    {
      label: 'Create an API key',
      done: checks.apiKey,
      link: '/settings/api-keys',
      linkLabel: 'Go to API Keys',
    },
  ];
  // ── End onboarding checklist ─────────────────────────────────────────────

  const fetchOverview = useCallback(() => getStatsOverview(win.hours), [win.hours]);
  const fetchTimeseries = useCallback(
    () => getStatsTimeseries(win.hours, win.bucketHours),
    [win.hours, win.bucketHours],
  );

  const { data: stats, error: statsErr, loading: statsLoading, refresh: refreshStats, lastUpdated } =
    usePolling(fetchOverview, { intervalMs: POLL_INTERVAL_MS });
  const { data: series, error: seriesErr, refresh: refreshSeries } =
    usePolling(fetchTimeseries, { intervalMs: POLL_INTERVAL_MS });

  function refresh() { refreshStats(); refreshSeries(); }

  const total = stats?.total ?? 0;
  const byStatus = stats?.totals_by_status || {};
  const successRate = stats?.success_rate ?? 0;
  const avgAttempts = stats?.avg_attempts ?? 0;
  const failed = (byStatus.failed || 0) + (byStatus.bounced || 0) + (byStatus.undelivered || 0);
  const inProgress = (byStatus.pending || 0) + (byStatus.processing || 0) +
    (byStatus.retrying || 0) + (byStatus.scheduled || 0);
  const sentDelivered = (byStatus.sent || 0) + (byStatus.delivered || 0);

  const chartData = (series || []).map((b) => ({
    time: fmt(b.bucket),
    ok: b.ok,
    failed: b.failed,
    other: b.other,
  }));

  const queues = stats?.queues || {};
  const hasQueues = Object.keys(queues).length > 0;
  const topErrors = stats?.top_errors || [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-bold">Overview</h1>
        <div className="flex items-center gap-2">
          <div className="flex rounded-lg overflow-hidden border border-gray-700">
            {WINDOWS.map((w, i) => (
              <button
                key={w.hours}
                onClick={() => setWinIdx(i)}
                className={`px-3 py-1.5 text-sm font-medium transition-colors ${
                  i === winIdx ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-300 hover:bg-gray-700'
                }`}
              >
                {w.label}
              </button>
            ))}
          </div>
          <button
            onClick={refresh}
            className="px-3 py-1.5 text-sm rounded-lg bg-gray-800 hover:bg-gray-700 border border-gray-700 text-gray-300"
          >
            Refresh
          </button>
        </div>
      </div>

      {flash && (
        <div className="px-4 py-3 rounded-lg bg-amber-900/30 border border-amber-700 text-amber-300 text-sm flex items-center justify-between">
          <span>⚠ {flash}</span>
        </div>
      )}

      {/* Onboarding checklist */}
      {isAdmin && !dismissed && !allDone && (
        <div className="bg-white border border-gray-200 rounded-xl p-6 mb-6 text-gray-900">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-base font-semibold">Get started with Notify</h2>
            <button
              type="button"
              onClick={() => { localStorage.setItem(dismissedKey, '1'); setDismissed(true); }}
              className="text-xs text-gray-400 hover:text-gray-600 transition-colors"
            >
              Dismiss
            </button>
          </div>
          {/* Progress bar */}
          <div className="h-2 rounded-full bg-gray-200 mb-5 overflow-hidden">
            <div
              className="h-2 rounded-full bg-indigo-500 transition-all"
              style={{ width: `${(completedCount / 3) * 100}%` }}
            />
          </div>
          <ul className="space-y-3">
            {STEPS.map((step) => (
              <li key={step.label} className="flex items-center gap-3">
                <span
                  className={`flex-shrink-0 w-5 h-5 rounded-full flex items-center justify-center text-xs font-bold ${
                    step.done
                      ? 'bg-indigo-500 text-white'
                      : 'bg-gray-200 text-gray-400'
                  }`}
                >
                  {step.done ? '✓' : ''}
                </span>
                <span className={`flex-1 text-sm ${step.done ? 'line-through text-gray-400' : 'text-gray-800'}`}>
                  {step.label}
                </span>
                {!step.done && (
                  <Link
                    to={step.link}
                    className="text-xs text-indigo-600 hover:text-indigo-800 font-medium shrink-0"
                  >
                    {step.linkLabel} →
                  </Link>
                )}
              </li>
            ))}
            {/* Step 4: Make your first API call */}
            <li className="flex items-start gap-3">
              <span className="flex-shrink-0 w-5 h-5 rounded-full flex items-center justify-center text-xs font-bold bg-gray-200 text-gray-400 mt-0.5">
              </span>
              <div className="flex-1">
                <button
                  type="button"
                  onClick={() => setExpanded((v) => !v)}
                  className="text-sm text-gray-800 flex items-center gap-1 hover:text-indigo-700 transition-colors"
                >
                  Make your first API call
                  <svg
                    className={`w-3.5 h-3.5 transition-transform ${expanded ? 'rotate-180' : ''}`}
                    fill="none" stroke="currentColor" viewBox="0 0 24 24"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                  </svg>
                </button>
                {expanded && (
                  <div className="mt-2 relative">
                    <pre className="bg-gray-900 text-green-300 text-xs rounded-lg p-3 overflow-x-auto whitespace-pre-wrap break-all">
                      {curlExample}
                    </pre>
                    <button
                      type="button"
                      onClick={handleCopy}
                      className="absolute top-2 right-2 px-2 py-1 rounded bg-gray-700 hover:bg-gray-600 text-gray-200 text-xs transition-colors"
                    >
                      {copied ? 'Copied!' : 'Copy'}
                    </button>
                  </div>
                )}
              </div>
            </li>
          </ul>
        </div>
      )}

      {lastUpdated && (
        <p className="text-xs text-gray-500">
          Last updated: {lastUpdated.toLocaleTimeString()}
        </p>
      )}

      {(statsErr || seriesErr) && (
        <ErrorBanner error={statsErr || seriesErr} onRetry={refresh} />
      )}

      {statsLoading && !stats ? (
        <Loading />
      ) : (
        <>
          {/* Stat Cards */}
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
            <StatCard label="Total" value={total} />
            <StatCard label="Sent / Delivered" value={sentDelivered} color="green" />
            <StatCard label="Failed" value={failed} color="red" />
            <StatCard label="In Progress" value={inProgress} color="yellow" />
            <StatCard label="Success Rate" value={`${successRate.toFixed(1)}%`} color="green"
              sub={`Avg ${avgAttempts.toFixed(2)} attempts`} />
          </div>

          {/* Chart */}
          {chartData.length > 0 && (
            <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
              <h2 className="text-sm font-medium text-gray-300 mb-4">Delivery over time</h2>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={chartData} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
                  <XAxis dataKey="time" tick={{ fill: '#9ca3af', fontSize: 11 }} />
                  <YAxis tick={{ fill: '#9ca3af', fontSize: 11 }} allowDecimals={false} />
                  <Tooltip
                    contentStyle={{ background: '#111827', border: '1px solid #374151', borderRadius: 8 }}
                    labelStyle={{ color: '#d1d5db' }}
                  />
                  <Legend wrapperStyle={{ color: '#9ca3af', fontSize: 12 }} />
                  <Bar dataKey="ok" name="OK" fill="#34d399" stackId="a" radius={[0, 0, 0, 0]} />
                  <Bar dataKey="failed" name="Failed" fill="#f87171" stackId="a" />
                  <Bar dataKey="other" name="Other" fill="#6b7280" stackId="a" radius={[3, 3, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* By Channel + By Provider */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
              <h2 className="text-sm font-medium text-gray-300 mb-3">By Channel</h2>
              {Object.keys(stats?.by_channel || {}).length === 0 ? (
                <p className="text-xs text-gray-500">No data</p>
              ) : (
                <ul className="space-y-1">
                  {Object.entries(stats.by_channel).map(([ch, n]) => (
                    <li key={ch} className="flex justify-between text-sm">
                      <span className="text-gray-400 capitalize">{ch}</span>
                      <span className="font-medium">{n}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
              <h2 className="text-sm font-medium text-gray-300 mb-3">By Provider</h2>
              {Object.keys(stats?.by_provider || {}).length === 0 ? (
                <p className="text-xs text-gray-500">No data</p>
              ) : (
                <ul className="space-y-1">
                  {Object.entries(stats.by_provider).map(([p, n]) => (
                    <li key={p} className="flex justify-between text-sm">
                      <span className="text-gray-400 capitalize">{p}</span>
                      <span className="font-medium">{n}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>

          {/* Top Errors + Queues */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
              <h2 className="text-sm font-medium text-gray-300 mb-3">Top Errors</h2>
              {topErrors.length === 0 ? (
                <p className="text-xs text-gray-500">No errors in this window 🎉</p>
              ) : (
                <ul className="space-y-2">
                  {topErrors.map((e, i) => (
                    <li key={i} className="flex justify-between text-xs gap-2">
                      <span className="text-gray-400 truncate">{e.error || e[0]}</span>
                      <span className="shrink-0 font-medium text-red-400">{e.count ?? e[1]}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            {hasQueues && (
              <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
                <h2 className="text-sm font-medium text-gray-300 mb-3">Queue Depths</h2>
                <div className="flex flex-wrap gap-2">
                  {Object.entries(queues).map(([q, depth]) => (
                    <span
                      key={q}
                      className={`px-3 py-1 rounded-full text-xs font-medium border ${
                        depth > 50
                          ? 'bg-red-900/30 text-red-300 border-red-700'
                          : 'bg-gray-800 text-gray-300 border-gray-700'
                      }`}
                    >
                      {q}: {depth}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}

