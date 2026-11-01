import { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, Link } from 'react-router-dom';
import { getNotification, getNotificationTimeline, retryNotification, cancelNotification, ApiError } from '../lib/api';
import { useAuth } from '../lib/auth';
import { IN_PROGRESS_STATUSES } from '../lib/constants';
import StatusBadge from '../components/StatusBadge';
import ConfirmDialog from '../components/ConfirmDialog';
import ErrorBanner from '../components/ErrorBanner';
import Loading from '../components/Loading';

function fmt(d) {
  if (!d) return '—';
  return new Date(d).toLocaleString();
}

export default function NotificationDetailPage() {
  const { id } = useParams();
  const { canWrite } = useAuth();

  const [notification, setNotification] = useState(null);
  const [timeline, setTimeline] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [actionError, setActionError] = useState(null);
  const [actionLoading, setActionLoading] = useState(false);
  const [copied, setCopied] = useState(false);

  // Dialog state
  const [dialogConfig, setDialogConfig] = useState(null); // { type: 'retry' | 'cancel', title, message }

  const reqId = useRef(0);
  const pollTimer = useRef(null);

  const fetchData = useCallback(async () => {
    const curId = ++reqId.current;
    try {
      const [n, t] = await Promise.all([
        getNotification(id),
        getNotificationTimeline(id).catch(() => []),
      ]);
      if (curId !== reqId.current) return;
      setNotification(n);
      setTimeline(t || []);
      setError(null);
    } catch (err) {
      if (curId !== reqId.current) return;
      setError(err);
    } finally {
      if (curId === reqId.current) setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    setLoading(true);
    fetchData();
  }, [fetchData]);

  // Polling while in-progress
  useEffect(() => {
    if (!notification || !IN_PROGRESS_STATUSES.has(notification.status)) {
      if (pollTimer.current) clearInterval(pollTimer.current);
      return;
    }

    pollTimer.current = setInterval(() => {
      if (!document.hidden) fetchData();
    }, 3000);

    return () => {
      if (pollTimer.current) clearInterval(pollTimer.current);
    };
  }, [notification, fetchData]);

  const handleCopyId = () => {
    if (!notification?.id) return;
    navigator.clipboard.writeText(notification.id);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleConfirmAction = async () => {
    if (!dialogConfig) return;
    setActionLoading(true);
    setActionError(null);
    try {
      if (dialogConfig.type === 'retry') {
        await retryNotification(id);
      } else if (dialogConfig.type === 'cancel') {
        await cancelNotification(id);
      }
      setDialogConfig(null);
      await fetchData();
    } catch (err) {
      setActionError(err);
      setDialogConfig(null);
    } finally {
      setActionLoading(false);
    }
  };

  if (loading && !notification) return <Loading text="Loading notification..." />;

  if (error) {
    if (error instanceof ApiError && error.status === 404) {
      return (
        <div className="space-y-4">
          <Link to="/notifications" className="text-sm text-blue-400 hover:underline">
            &larr; Back to Notifications
          </Link>
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-8 text-center">
            <h2 className="text-lg font-semibold text-gray-200">Notification not found</h2>
            <p className="text-sm text-gray-500 mt-2">The requested notification ID does not exist.</p>
          </div>
        </div>
      );
    }
    return (
      <div className="space-y-4">
        <Link to="/notifications" className="text-sm text-blue-400 hover:underline">
          &larr; Back to Notifications
        </Link>
        <ErrorBanner error={error} onRetry={fetchData} />
      </div>
    );
  }

  if (!notification) return null;

  return (
    <div className="space-y-6">
      {/* Top back link */}
      <div>
        <Link to="/notifications" className="text-sm text-blue-400 hover:underline">
          &larr; Back to Notifications
        </Link>
      </div>

      {actionError && <ErrorBanner error={actionError} />}

      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 bg-gray-900 border border-gray-800 rounded-xl p-4 md:p-6">
        <div className="flex flex-wrap items-center gap-3">
          <StatusBadge status={notification.status} />
          <span className="font-mono text-sm md:text-base text-gray-200">{notification.id}</span>
          <button
            onClick={handleCopyId}
            className="px-2 py-1 text-xs rounded bg-gray-800 hover:bg-gray-700 text-gray-300 border border-gray-700"
          >
            {copied ? 'Copied!' : 'Copy ID'}
          </button>
        </div>

        {/* Action buttons */}
        {canWrite && (
          <div className="flex items-center gap-2">
            {notification.status === 'failed' && (
              <button
                onClick={() =>
                  setDialogConfig({
                    type: 'retry',
                    title: 'Retry Notification',
                    message: 'Are you sure you want to retry sending this notification?',
                  })
                }
                className="px-3 py-1.5 text-sm font-medium rounded-lg bg-blue-600 hover:bg-blue-500 text-white"
              >
                Retry
              </button>
            )}
            {notification.status === 'scheduled' && (
              <button
                onClick={() =>
                  setDialogConfig({
                    type: 'cancel',
                    title: 'Cancel Notification',
                    message: 'Are you sure you want to cancel this scheduled notification?',
                  })
                }
                className="px-3 py-1.5 text-sm font-medium rounded-lg bg-red-600 hover:bg-red-500 text-white"
              >
                Cancel
              </button>
            )}
          </div>
        )}
      </div>

      {/* Error banner if notification has error */}
      {notification.error_message && (
        <div className="bg-red-950/40 border border-red-800 rounded-xl p-4 text-red-300 text-sm">
          <p className="font-semibold text-xs uppercase tracking-wider mb-1 text-red-400">Error</p>
          <p className="font-mono break-all">{notification.error_message}</p>
        </div>
      )}

      {/* Details Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 space-y-3">
          <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Destination</h3>
          <div>
            <span className="text-xs text-gray-500 block">Channel</span>
            <span className="text-sm font-medium capitalize">{notification.channel}</span>
          </div>
          <div>
            <span className="text-xs text-gray-500 block">Recipient</span>
            <span className="text-sm font-mono break-all">{notification.recipient}</span>
          </div>
          {notification.subject && (
            <div>
              <span className="text-xs text-gray-500 block">Subject</span>
              <span className="text-sm font-medium">{notification.subject}</span>
            </div>
          )}
        </div>

        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 space-y-3">
          <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Delivery Details</h3>
          <div>
            <span className="text-xs text-gray-500 block">Provider</span>
            <span className="text-sm font-medium">{notification.provider || '—'}</span>
          </div>
          <div>
            <span className="text-xs text-gray-500 block">Provider Message ID</span>
            <span className="text-sm font-mono break-all">{notification.provider_message_id || '—'}</span>
          </div>
          <div>
            <span className="text-xs text-gray-500 block">Attempts</span>
            <span className="text-sm font-medium">{notification.attempt_count} / {notification.max_attempts}</span>
          </div>
          <div>
            <span className="text-xs text-gray-500 block">Priority / Category</span>
            <span className="text-sm font-medium">{notification.priority ?? '—'} / {notification.category || '—'}</span>
          </div>
          {notification.batch_id && (
            <div>
              <span className="text-xs text-gray-500 block">Batch</span>
              <Link
                to={`/notifications?batch_id=${encodeURIComponent(notification.batch_id)}`}
                className="text-sm font-mono text-blue-400 hover:underline"
              >
                {notification.batch_id}
              </Link>
            </div>
          )}
        </div>

        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 space-y-3">
          <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Timestamps</h3>
          <div>
            <span className="text-xs text-gray-500 block">Created</span>
            <span className="text-sm">{fmt(notification.created_at)}</span>
          </div>
          <div>
            <span className="text-xs text-gray-500 block">Scheduled</span>
            <span className="text-sm">{fmt(notification.scheduled_at)}</span>
          </div>
          <div>
            <span className="text-xs text-gray-500 block">Sent</span>
            <span className="text-sm">{fmt(notification.sent_at)}</span>
          </div>
          <div>
            <span className="text-xs text-gray-500 block">Delivered</span>
            <span className="text-sm">{fmt(notification.delivered_at)}</span>
          </div>
          <div>
            <span className="text-xs text-gray-500 block">Updated</span>
            <span className="text-sm">{fmt(notification.updated_at)}</span>
          </div>
        </div>
      </div>

      {/* Body */}
      {notification.body && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
          <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">Message Body</h3>
          <pre className="bg-gray-950 p-4 rounded-lg text-sm font-mono text-gray-300 overflow-x-auto whitespace-pre-wrap max-h-80">
            {notification.body}
          </pre>
        </div>
      )}

      {/* Timeline */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 md:p-6">
        <h3 className="text-sm font-semibold text-gray-300 mb-4">Delivery Timeline</h3>
        {timeline.length === 0 ? (
          <p className="text-sm text-gray-500">No delivery attempts recorded yet.</p>
        ) : (
          <div className="space-y-4">
            {timeline.map((item, index) => {
              const isSuccess = item.outcome === 'success' || item.status === 'delivered' || item.status === 'sent';
              const isFailure = item.outcome === 'failure' || item.status === 'failed' || item.status === 'bounced';
              const dotColor = isSuccess ? 'bg-emerald-500' : isFailure ? 'bg-red-500' : 'bg-amber-500';

              return (
                <div key={item.id || index} className="flex items-start gap-3 border-l-2 border-gray-800 pl-4 py-1 relative">
                  <span className={`absolute -left-[5px] top-2.5 h-2 w-2 rounded-full ${dotColor}`} />
                  <div className="flex-1 space-y-1">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="text-sm font-medium capitalize text-gray-200">
                        Attempt #{item.attempt_number ?? (index + 1)}: {item.outcome || item.status}
                      </span>
                      <span className="text-xs text-gray-500">
                        {fmt(item.created_at || item.attempted_at)}
                      </span>
                    </div>
                    <div className="flex flex-wrap gap-4 text-xs text-gray-400">
                      {item.provider && <span>Provider: <strong className="text-gray-300">{item.provider}</strong></span>}
                      {item.duration_ms !== undefined && item.duration_ms !== null && (
                        <span>Duration: {item.duration_ms} ms</span>
                      )}
                      {item.status_code && <span>HTTP Status: {item.status_code}</span>}
                    </div>
                    {item.error_message && (
                      <p className="text-xs text-red-400 font-mono mt-1 break-all bg-red-950/20 p-2 rounded border border-red-900/30">
                        {item.error_message}
                      </p>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Confirmation Dialog */}
      <ConfirmDialog
        open={Boolean(dialogConfig)}
        title={dialogConfig?.title || ''}
        message={dialogConfig?.message || ''}
        onConfirm={handleConfirmAction}
        onCancel={() => setDialogConfig(null)}
        loading={actionLoading}
        confirmLabel={dialogConfig?.type === 'retry' ? 'Retry' : 'Cancel Notification'}
      />
    </div>
  );
}

