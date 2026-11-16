import { useState, useCallback, useEffect } from 'react';
import { useLocation, Link } from 'react-router-dom';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from 'recharts';
import {
  RotateCw,
  Send,
  CheckCircle2,
  Circle,
  ChevronRight,
  X,
  Radio,
  Layers,
  Sparkles,
} from 'lucide-react';
import { usePolling } from '../lib/usePolling';
import {
  getStatsOverview,
  getStatsTimeseries,
  apiFetch,
  apiFetchWithCount,
  absoluteApiBase,
} from '../lib/api';
import { POLL_INTERVAL_MS } from '../lib/constants';
import { useAuth } from '../lib/auth';
import ErrorBanner from '../components/ErrorBanner';
import Loading from '../components/Loading';
import Button from '../components/ui/Button';
import Card from '../components/ui/Card';
import CodeBlock from '../components/ui/CodeBlock';

function DailyUsageStrip({ usageData }) {
  if (!usageData?.daily) return null;
  const { used = 0, limit = null, resets_at } = usageData.daily;
  const isUnlimited = limit === null;
  const pct = isUnlimited ? 0 : Math.min(100, Math.round((used / limit) * 100));

  const resetStr = resets_at
    ? `Quota resets ${new Date(resets_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`
    : '';

  return (
    <div className="bg-white border border-[#E7E5E4] rounded-[8px] px-4 py-2.5 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
      <div className="flex items-center gap-3">
        <div className="w-5 h-5 rounded-[4px] bg-[#EEF2FF] flex items-center justify-center text-[#4F46E5]">
          <Layers className="w-3.5 h-3.5" strokeWidth={1.5} />
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[#1C1917] font-medium">Daily sends:</span>
          <span className="text-[#1C1917] font-semibold">
            {used.toLocaleString()}{' '}
            <span className="text-[#78716C] font-normal">
              {isUnlimited ? '(Unlimited)' : `of ${limit.toLocaleString()}`}
            </span>
          </span>
          {!isUnlimited && (
            <div className="w-20 h-1.5 bg-[#F5F5F4] rounded-full overflow-hidden ml-1">
              <div
                className={`h-full rounded-full ${
                  pct >= 100 ? 'bg-[#B91C1C]' : pct >= 80 ? 'bg-[#A16207]' : 'bg-[#4F46E5]'
                }`}
                style={{ width: `${pct}%` }}
              />
            </div>
          )}
        </div>
        {resetStr && (
          <span className="text-[#A8A29E] hidden md:inline">• {resetStr}</span>
        )}
      </div>
      <Link
        to="/settings/general"
        className="text-[#4F46E5] hover:text-[#4338CA] font-medium flex items-center gap-1 shrink-0"
      >
        View usage & tier limits
        <ChevronRight className="w-3.5 h-3.5" strokeWidth={1.5} />
      </Link>
    </div>
  );
}

const WINDOWS = [
  { label: '6h', hours: 6, bucketHours: 1 },
  { label: '24h', hours: 24, bucketHours: 1 },
  { label: '7d', hours: 168, bucketHours: 24 },
];

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
  const [dismissed, setDismissed] = useState(
    () => localStorage.getItem(dismissedKey) === '1'
  );
  const [checks, setChecks] = useState({
    provider: false,
    notification: false,
    apiKey: false,
  });
  const [expandedSnippet, setExpandedSnippet] = useState(false);

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
  const completedCount =
    (checks.provider ? 1 : 0) +
    (checks.notification ? 1 : 0) +
    (checks.apiKey ? 1 : 0);

  const apiBase = absoluteApiBase();
  const curlExample = `curl -X POST ${apiBase}/notifications/email \\
  -H "X-API-Key: YOUR_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "recipient": "user@example.com",
    "subject": "Hello from Notify",
    "body": "Welcome to your notification infrastructure."
  }'`;

  const fetchOverview = useCallback(
    () => getStatsOverview(win.hours),
    [win.hours]
  );
  const fetchTimeseries = useCallback(
    () => getStatsTimeseries(win.hours, win.bucketHours),
    [win.hours, win.bucketHours]
  );

  const [usageData, setUsageData] = useState(null);
  useEffect(() => {
    apiFetch('/usage')
      .then((d) => setUsageData(d))
      .catch(() => {});
  }, []);

  const {
    data: stats,
    error: statsErr,
    loading: statsLoading,
    refresh: refreshStats,
  } = usePolling(fetchOverview, { intervalMs: POLL_INTERVAL_MS });

  const {
    data: series,
    error: seriesErr,
    refresh: refreshSeries,
  } = usePolling(fetchTimeseries, { intervalMs: POLL_INTERVAL_MS });

  function refresh() {
    refreshStats();
    refreshSeries();
  }

  const total = stats?.total ?? 0;
  const byStatus = stats?.totals_by_status || {};
  const successRate = stats?.success_rate ?? 0;
  const failed =
    (byStatus.failed || 0) + (byStatus.bounced || 0) + (byStatus.undelivered || 0);
  const inProgress =
    (byStatus.pending || 0) +
    (byStatus.processing || 0) +
    (byStatus.retrying || 0) +
    (byStatus.scheduled || 0);
  const delivered =
    (byStatus.delivered || 0) + (byStatus.sent || 0);

  const chartData = (series || []).map((b) => ({
    time: fmt(b.bucket),
    delivered: b.ok || 0,
    failed: b.failed || 0,
  }));

  const byChannel = stats?.by_channel || {};
  const byProvider = stats?.by_provider || {};
  const topErrors = stats?.top_errors || [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-1">
        <div>
          <h1 className="text-xl sm:text-2xl font-semibold text-[#1C1917] tracking-tight">
            Overview
          </h1>
          <p className="text-xs sm:text-sm text-[#78716C] mt-0.5">
            Real-time delivery status and notification dispatch volume across all channels.
          </p>
        </div>

        <div className="flex items-center gap-2">
          {/* Time range selector */}
          <div className="inline-flex rounded-[6px] border border-[#E7E5E4] bg-white p-0.5 shadow-xs">
            {WINDOWS.map((w, i) => (
              <button
                key={w.hours}
                onClick={() => setWinIdx(i)}
                className={`px-2.5 py-1 text-xs font-medium rounded-[4px] transition-colors cursor-pointer ${
                  i === winIdx
                    ? 'bg-[#F5F5F4] text-[#1C1917]'
                    : 'text-[#78716C] hover:text-[#1C1917]'
                }`}
              >
                {w.label}
              </button>
            ))}
          </div>

          <Button
            variant="secondary"
            size="sm"
            onClick={refresh}
            icon={RotateCw}
          >
            Refresh
          </Button>

          {isAdmin && (
            <Link to="/send">
              <Button
                variant="primary"
                size="sm"
                icon={Send}
              >
                Send Test Notification
              </Button>
            </Link>
          )}
        </div>
      </div>

      {flash && (
        <div className="px-3.5 py-2.5 rounded-[6px] bg-[#FEFCE8] border border-[#FEF08A] text-[#A16207] text-xs">
          {flash}
        </div>
      )}

      {/* Daily Usage Strip */}
      <DailyUsageStrip usageData={usageData} />

      {/* Setup Checklist (Card in app's own light theme) */}
      {isAdmin && !dismissed && !allDone && (
        <div className="bg-white border border-[#E7E5E4] rounded-[8px] p-5 shadow-xs relative">
          <div className="flex items-start justify-between gap-4 mb-4">
            <div>
              <div className="flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-[#4F46E5]" strokeWidth={1.5} />
                <h2 className="text-sm font-semibold text-[#1C1917]">
                  Setup checklist
                </h2>
                <span className="text-xs text-[#78716C] font-normal">
                  {completedCount} of 3 completed
                </span>
              </div>
              <p className="text-xs text-[#78716C] mt-0.5">
                Complete these foundational steps to unlock production traffic across high-throughput relays.
              </p>
            </div>
            <button
              type="button"
              onClick={() => {
                localStorage.setItem(dismissedKey, '1');
                setDismissed(true);
              }}
              className="text-[#A8A29E] hover:text-[#1C1917] p-1 rounded transition-colors"
              title="Dismiss checklist"
            >
              <X className="w-4 h-4" strokeWidth={1.5} />
            </button>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            {/* Step 1: Provider */}
            <div className="border border-[#E7E5E4] rounded-[6px] p-3.5 flex flex-col justify-between bg-[#FAFAF9]/50">
              <div>
                <div className="flex items-center gap-2 mb-1.5">
                  {checks.provider ? (
                    <CheckCircle2
                      className="w-4 h-4 text-[#15803D]"
                      strokeWidth={1.5}
                    />
                  ) : (
                    <Circle
                      className="w-4 h-4 text-[#A8A29E]"
                      strokeWidth={1.5}
                    />
                  )}
                  <h4 className="text-xs font-semibold text-[#1C1917]">
                    Connect an email provider
                  </h4>
                </div>
                <p className="text-[11px] text-[#78716C]">
                  Configure Brevo or SMTP credentials in Settings.
                </p>
              </div>
              <div className="mt-3 pt-2 border-t border-[#E7E5E4]">
                <Link
                  to="/settings/providers"
                  className="text-xs font-medium text-[#4F46E5] hover:text-[#4338CA] flex items-center gap-1"
                >
                  Manage providers <ChevronRight className="w-3.5 h-3.5" />
                </Link>
              </div>
            </div>

            {/* Step 2: Test send */}
            <div className="border border-[#E7E5E4] rounded-[6px] p-3.5 flex flex-col justify-between bg-[#FAFAF9]/50">
              <div>
                <div className="flex items-center gap-2 mb-1.5">
                  {checks.notification ? (
                    <CheckCircle2
                      className="w-4 h-4 text-[#15803D]"
                      strokeWidth={1.5}
                    />
                  ) : (
                    <Circle
                      className="w-4 h-4 text-[#A8A29E]"
                      strokeWidth={1.5}
                    />
                  )}
                  <h4 className="text-xs font-semibold text-[#1C1917]">
                    Send a test email
                  </h4>
                </div>
                <p className="text-[11px] text-[#78716C]">
                  Verify template engine & delivery dispatch.
                </p>
              </div>
              <div className="mt-3 pt-2 border-t border-[#E7E5E4]">
                <Link
                  to="/send"
                  className="text-xs font-medium text-[#4F46E5] hover:text-[#4338CA] flex items-center gap-1"
                >
                  Send test <ChevronRight className="w-3.5 h-3.5" />
                </Link>
              </div>
            </div>

            {/* Step 3: API Key */}
            <div className="border border-[#E7E5E4] rounded-[6px] p-3.5 flex flex-col justify-between bg-[#FAFAF9]/50">
              <div>
                <div className="flex items-center gap-2 mb-1.5">
                  {checks.apiKey ? (
                    <CheckCircle2
                      className="w-4 h-4 text-[#15803D]"
                      strokeWidth={1.5}
                    />
                  ) : (
                    <Circle
                      className="w-4 h-4 text-[#A8A29E]"
                      strokeWidth={1.5}
                    />
                  )}
                  <h4 className="text-xs font-semibold text-[#1C1917]">
                    Create an API key
                  </h4>
                </div>
                <p className="text-[11px] text-[#78716C]">
                  Authenticate your backend microservices.
                </p>
              </div>
              <div className="mt-3 pt-2 border-t border-[#E7E5E4]">
                <Link
                  to="/settings/api-keys"
                  className="text-xs font-medium text-[#4F46E5] hover:text-[#4338CA] flex items-center gap-1"
                >
                  Generate key <ChevronRight className="w-3.5 h-3.5" />
                </Link>
              </div>
            </div>

            {/* Step 4: Snippets */}
            <div className="border border-[#E7E5E4] rounded-[6px] p-3.5 flex flex-col justify-between bg-[#FAFAF9]/50">
              <div>
                <div className="flex items-center gap-2 mb-1.5">
                  <Circle className="w-4 h-4 text-[#A8A29E]" strokeWidth={1.5} />
                  <h4 className="text-xs font-semibold text-[#1C1917]">
                    Make your first API call
                  </h4>
                </div>
                <p className="text-[11px] text-[#78716C]">
                  cURL, Node.js, or Python snippets.
                </p>
              </div>
              <div className="mt-3 pt-2 border-t border-[#E7E5E4]">
                <button
                  type="button"
                  onClick={() => setExpandedSnippet((o) => !o)}
                  className="text-xs font-medium text-[#4F46E5] hover:text-[#4338CA] flex items-center gap-1 cursor-pointer"
                >
                  {expandedSnippet ? 'Hide snippet' : 'View snippet'}{' '}
                  <ChevronRight className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          </div>

          {expandedSnippet && (
            <div className="mt-4">
              <CodeBlock code={curlExample} language="bash" title="cURL Example" />
            </div>
          )}
        </div>
      )}

      {(statsErr || seriesErr) && (
        <ErrorBanner error={statsErr || seriesErr} onRetry={refresh} />
      )}

      {statsLoading && !stats ? (
        <Loading />
      ) : (
        <>
          {/* Single 5-stat container divided by hairlines */}
          <div className="bg-white border border-[#E7E5E4] rounded-[8px] divide-y sm:divide-y-0 sm:divide-x divide-[#E7E5E4] grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 shadow-xs overflow-hidden">
            {/* Stat 1: Total */}
            <div className="p-4 sm:p-5 flex flex-col justify-between">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-semibold text-[#78716C] uppercase tracking-wider">
                  Total Sends
                </span>
                <Radio className="w-3.5 h-3.5 text-[#A8A29E]" strokeWidth={1.5} />
              </div>
              <div className="mt-2">
                <div className="text-2xl sm:text-3xl font-semibold text-[#1C1917] tracking-tight">
                  {total.toLocaleString()}
                </div>
                <div className="text-[11px] text-[#78716C] mt-1">
                  In selected window
                </div>
              </div>
            </div>

            {/* Stat 2: Delivered */}
            <div className="p-4 sm:p-5 flex flex-col justify-between">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-semibold text-[#78716C] uppercase tracking-wider">
                  Delivered
                </span>
                <span className="w-2 h-2 rounded-full bg-[#15803D]" />
              </div>
              <div className="mt-2">
                <div className="text-2xl sm:text-3xl font-semibold text-[#1C1917] tracking-tight">
                  {delivered.toLocaleString()}
                </div>
                <div className="text-[11px] text-[#15803D] mt-1 font-medium">
                  {total > 0 ? `${((delivered / total) * 100).toFixed(1)}%` : '0%'} delivered
                </div>
              </div>
            </div>

            {/* Stat 3: Failed */}
            <div className="p-4 sm:p-5 flex flex-col justify-between">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-semibold text-[#78716C] uppercase tracking-wider">
                  Failed
                </span>
                <span className="w-2 h-2 rounded-full bg-[#B91C1C]" />
              </div>
              <div className="mt-2">
                <div className="text-2xl sm:text-3xl font-semibold text-[#1C1917] tracking-tight">
                  {failed.toLocaleString()}
                </div>
                <div className="text-[11px] text-[#B91C1C] mt-1">
                  {total > 0 ? `${((failed / total) * 100).toFixed(1)}% failed` : '0%'}
                </div>
              </div>
            </div>

            {/* Stat 4: In Progress */}
            <div className="p-4 sm:p-5 flex flex-col justify-between">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-semibold text-[#78716C] uppercase tracking-wider">
                  In Progress
                </span>
                <span className="w-2 h-2 rounded-full bg-[#A16207]" />
              </div>
              <div className="mt-2">
                <div className="text-2xl sm:text-3xl font-semibold text-[#1C1917] tracking-tight">
                  {inProgress.toLocaleString()}
                </div>
                <div className="text-[11px] text-[#78716C] mt-1">
                  Queued & retrying
                </div>
              </div>
            </div>

            {/* Stat 5: Success Rate */}
            <div className="p-4 sm:p-5 flex flex-col justify-between col-span-2 sm:col-span-1">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-semibold text-[#78716C] uppercase tracking-wider">
                  Success Rate
                </span>
                <CheckCircle2
                  className="w-3.5 h-3.5 text-[#15803D]"
                  strokeWidth={1.5}
                />
              </div>
              <div className="mt-2">
                <div className="text-2xl sm:text-3xl font-semibold text-[#1C1917] tracking-tight">
                  {successRate.toFixed(1)}%
                </div>
                <div className="text-[11px] text-[#78716C] mt-1">
                  Overall delivery rate
                </div>
              </div>
            </div>
          </div>

          {/* Delivery over time Line Chart */}
          <div className="bg-white border border-[#E7E5E4] rounded-[8px] p-5 shadow-xs">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-4">
              <div>
                <h3 className="text-sm font-semibold text-[#1C1917]">
                  Delivery over time
                </h3>
                <p className="text-xs text-[#78716C] mt-0.5">
                  Hourly volume and delivery outcome breakdown.
                </p>
              </div>
              <div className="flex items-center gap-4 text-xs">
                <div className="flex items-center gap-1.5">
                  <span className="w-2.5 h-2.5 rounded-full bg-[#4F46E5]" />
                  <span className="text-[#1C1917] font-medium">Delivered</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="w-2.5 h-2.5 rounded-full bg-[#EF4444]" />
                  <span className="text-[#1C1917] font-medium">Failed</span>
                </div>
              </div>
            </div>

            {chartData.length > 0 ? (
              <div className="h-56 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart
                    data={chartData}
                    margin={{ top: 10, right: 10, left: -20, bottom: 0 }}
                  >
                    <CartesianGrid
                      strokeDasharray="3 3"
                      stroke="#F5F5F4"
                      vertical={false}
                    />
                    <XAxis
                      dataKey="time"
                      tick={{ fill: '#78716C', fontSize: 11 }}
                      stroke="#E7E5E4"
                      tickLine={false}
                    />
                    <YAxis
                      tick={{ fill: '#78716C', fontSize: 11 }}
                      stroke="#E7E5E4"
                      tickLine={false}
                      allowDecimals={false}
                    />
                    <Tooltip
                      contentStyle={{
                        background: '#FFFFFF',
                        border: '1px solid #E7E5E4',
                        borderRadius: 6,
                        boxShadow: '0 2px 4px rgba(0,0,0,0.04)',
                        fontSize: 12,
                      }}
                      labelStyle={{ color: '#1C1917', fontWeight: 600 }}
                    />
                    <Line
                      type="monotone"
                      dataKey="delivered"
                      name="Delivered"
                      stroke="#4F46E5"
                      strokeWidth={2}
                      dot={false}
                      activeDot={{ r: 4, stroke: '#4F46E5', strokeWidth: 1 }}
                    />
                    <Line
                      type="monotone"
                      dataKey="failed"
                      name="Failed"
                      stroke="#EF4444"
                      strokeWidth={1.5}
                      dot={false}
                      activeDot={{ r: 4, stroke: '#EF4444', strokeWidth: 1 }}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <div className="h-44 flex items-center justify-center text-xs text-[#78716C]">
                No timeseries data in this window.
              </div>
            )}
          </div>

          {/* By Channel + By Provider Cards */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* By Channel */}
            <Card
              title="By channel"
              subtitle="Volume distribution and status"
              action={
                <Link
                  to="/templates"
                  className="text-xs text-[#4F46E5] hover:text-[#4338CA] font-medium"
                >
                  Configure templates →
                </Link>
              }
            >
              {Object.keys(byChannel).length === 0 ? (
                <p className="text-xs text-[#78716C] py-4 text-center">
                  No channel traffic recorded yet.
                </p>
              ) : (
                <div className="space-y-3">
                  {Object.entries(byChannel).map(([ch, count]) => {
                    const pctCh = total > 0 ? Math.round((count / total) * 100) : 0;
                    return (
                      <div key={ch} className="space-y-1">
                        <div className="flex items-center justify-between text-xs">
                          <span className="font-medium text-[#1C1917] capitalize">
                            {ch}
                          </span>
                          <span className="text-[#78716C]">
                            <strong className="text-[#1C1917]">
                              {count.toLocaleString()}
                            </strong>{' '}
                            ({pctCh}%)
                          </span>
                        </div>
                        <div className="h-1.5 w-full bg-[#F5F5F4] rounded-full overflow-hidden">
                          <div
                            className="h-full bg-[#4F46E5] rounded-full"
                            style={{ width: `${pctCh}%` }}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </Card>

            {/* By Provider */}
            <Card
              title="By provider"
              subtitle="Real-time gateway connectivity"
              action={
                <Link
                  to="/settings/providers"
                  className="text-xs text-[#4F46E5] hover:text-[#4338CA] font-medium"
                >
                  Manage providers →
                </Link>
              }
            >
              {Object.keys(byProvider).length === 0 ? (
                <p className="text-xs text-[#78716C] py-4 text-center">
                  No provider delivery data recorded yet.
                </p>
              ) : (
                <div className="divide-y divide-[#E7E5E4]">
                  {Object.entries(byProvider).map(([p, count]) => (
                    <div
                      key={p}
                      className="py-2.5 first:pt-0 last:pb-0 flex items-center justify-between text-xs"
                    >
                      <div className="flex items-center gap-2">
                        <span className="w-2 h-2 rounded-full bg-[#15803D]" />
                        <span className="font-medium text-[#1C1917] capitalize">
                          {p}
                        </span>
                      </div>
                      <span className="text-[#78716C]">
                        <strong className="text-[#1C1917]">
                          {count.toLocaleString()}
                        </strong>{' '}
                        dispatched
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </Card>
          </div>

          {/* Top Errors Table */}
          <div className="bg-white border border-[#E7E5E4] rounded-[8px] overflow-hidden shadow-xs">
            <div className="px-5 py-4 border-b border-[#E7E5E4] flex items-center justify-between">
              <div>
                <h3 className="text-sm font-semibold text-[#1C1917]">
                  Top errors & incidents
                </h3>
                <p className="text-xs text-[#78716C] mt-0.5">
                  Recent dispatch failures and rate limits.
                </p>
              </div>
              <span className="text-xs font-medium px-2 py-0.5 rounded-[4px] bg-[#F5F5F4] text-[#78716C] border border-[#E7E5E4]">
                {topErrors.length} {topErrors.length === 1 ? 'type' : 'types'}
              </span>
            </div>

            {topErrors.length === 0 ? (
              <div className="p-8 text-center text-xs text-[#78716C]">
                No errors recorded in this time window. Everything is operating normally.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-[#FAFAF9] border-b border-[#E7E5E4] text-[11px] font-semibold text-[#78716C] uppercase tracking-wider">
                    <tr>
                      <th className="px-5 py-3">Error & Reason</th>
                      <th className="px-5 py-3 text-right">Count</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#E7E5E4]">
                    {topErrors.map((e, i) => {
                      const errName = e.error || e[0] || 'Unknown Error';
                      const count = e.count ?? e[1] ?? 1;
                      return (
                        <tr
                          key={i}
                          className="hover:bg-[#FAFAF9]/60 transition-colors"
                        >
                          <td className="px-5 py-3 font-mono text-[12px] text-[#B91C1C]">
                            {errName}
                          </td>
                          <td className="px-5 py-3 text-right font-medium text-[#1C1917]">
                            {count.toLocaleString()}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
