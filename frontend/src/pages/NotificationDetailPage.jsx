import { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, Link } from 'react-router-dom';
import {
  ArrowLeft,
  Copy,
  Check,
  RotateCw,
  XCircle,
  AlertCircle,
} from 'lucide-react';
import {
  getNotification,
  getNotificationTimeline,
  retryNotification,
  cancelNotification,
  ApiError,
} from '../lib/api';
import { useAuth } from '../lib/auth';
import { IN_PROGRESS_STATUSES } from '../lib/constants';
import StatusBadge from '../components/StatusBadge';
import ConfirmDialog from '../components/ConfirmDialog';
import ErrorBanner from '../components/ErrorBanner';
import Loading from '../components/Loading';
import Button from '../components/ui/Button';
import Card from '../components/ui/Card';

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
  const [dialogConfig, setDialogConfig] = useState(null);

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

  if (loading && !notification)
    return <Loading text="Loading notification details…" />;

  if (error) {
    if (error instanceof ApiError && error.status === 404) {
      return (
        <div className="space-y-4">
          <Link
            to="/notifications"
            className="text-xs text-[#4F46E5] hover:underline flex items-center gap-1 font-medium"
          >
            <ArrowLeft className="w-3.5 h-3.5" /> Back to Notifications
          </Link>
          <div className="bg-white border border-[#E7E5E4] rounded-[8px] p-8 text-center">
            <h2 className="text-base font-semibold text-[#1C1917]">
              Notification not found
            </h2>
            <p className="text-xs text-[#78716C] mt-1">
              The requested notification record does not exist or was deleted.
            </p>
          </div>
        </div>
      );
    }
    return (
      <div className="space-y-4">
        <Link
          to="/notifications"
          className="text-xs text-[#4F46E5] hover:underline flex items-center gap-1 font-medium"
        >
          <ArrowLeft className="w-3.5 h-3.5" /> Back to Notifications
        </Link>
        <ErrorBanner error={error} onRetry={fetchData} />
      </div>
    );
  }

  if (!notification) return null;

  return (
    <div className="space-y-6 max-w-[840px]">
      {/* Top back link */}
      <div>
        <Link
          to="/notifications"
          className="text-xs text-[#4F46E5] hover:underline flex items-center gap-1.5 font-medium"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          <span>Back to Notifications</span>
        </Link>
      </div>

      {actionError && <ErrorBanner error={actionError} />}

      {/* Header card */}
      <div className="bg-white border border-[#E7E5E4] rounded-[8px] p-5 shadow-xs flex flex-wrap items-center justify-between gap-4">
        <div className="flex flex-wrap items-center gap-3">
          <StatusBadge status={notification.status} />
          <span className="font-mono text-xs sm:text-sm text-[#1C1917] font-medium">
            {notification.id}
          </span>
          <Button
            variant="secondary"
            size="sm"
            onClick={handleCopyId}
            icon={copied ? Check : Copy}
          >
            {copied ? 'Copied' : 'Copy ID'}
          </Button>
        </div>

        {/* Actions */}
        {canWrite && (
          <div className="flex items-center gap-2">
            {notification.status === 'failed' && (
              <Button
                variant="primary"
                size="sm"
                onClick={() =>
                  setDialogConfig({
                    type: 'retry',
                    title: 'Retry Notification',
                    message:
                      'Are you sure you want to retry sending this notification?',
                  })
                }
                icon={RotateCw}
              >
                Retry Dispatch
              </Button>
            )}
            {notification.status === 'scheduled' && (
              <Button
                variant="destructive"
                size="sm"
                onClick={() =>
                  setDialogConfig({
                    type: 'cancel',
                    title: 'Cancel Notification',
                    message:
                      'Are you sure you want to cancel this scheduled notification?',
                  })
                }
                icon={XCircle}
              >
                Cancel Schedule
              </Button>
            )}
          </div>
        )}
      </div>

      {/* Error alert if failure occurred */}
      {notification.error_message && (
        <div className="bg-[#FEF2F2] border border-[#FECACA] rounded-[8px] p-4 text-xs text-[#B91C1C]">
          <p className="font-semibold uppercase tracking-wider mb-1 flex items-center gap-1.5">
            <AlertCircle className="w-4 h-4" /> Dispatch Failure
          </p>
          <p className="font-mono break-all">{notification.error_message}</p>
        </div>
      )}

      {/* Details Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Destination */}
        <div className="bg-white border border-[#E7E5E4] rounded-[8px] p-4 space-y-3">
          <h3 className="text-[11px] font-semibold text-[#78716C] uppercase tracking-wider">
            Destination
          </h3>
          <div>
            <span className="text-[11px] text-[#78716C] block">Channel</span>
            <span className="text-xs font-medium text-[#1C1917] capitalize">
              {notification.channel}
            </span>
          </div>
          <div>
            <span className="text-[11px] text-[#78716C] block">Recipient</span>
            <span className="text-xs font-mono text-[#1C1917] break-all">
              {notification.recipient}
            </span>
          </div>
          {notification.subject && (
            <div>
              <span className="text-[11px] text-[#78716C] block">Subject</span>
              <span className="text-xs font-medium text-[#1C1917]">
                {notification.subject}
              </span>
            </div>
          )}
        </div>

        {/* Delivery Details */}
        <div className="bg-white border border-[#E7E5E4] rounded-[8px] p-4 space-y-3">
          <h3 className="text-[11px] font-semibold text-[#78716C] uppercase tracking-wider">
            Delivery Details
          </h3>
          <div>
            <span className="text-[11px] text-[#78716C] block">Provider</span>
            <span className="text-xs font-medium text-[#1C1917] capitalize">
              {notification.provider || '—'}
            </span>
          </div>
          <div>
            <span className="text-[11px] text-[#78716C] block">
              Provider Message ID
            </span>
            <span className="text-xs font-mono text-[#1C1917] break-all">
              {notification.provider_message_id || '—'}
            </span>
          </div>
          <div>
            <span className="text-[11px] text-[#78716C] block">Attempts</span>
            <span className="text-xs font-medium text-[#1C1917]">
              {notification.attempt_count} / {notification.max_attempts}
            </span>
          </div>
          <div>
            <span className="text-[11px] text-[#78716C] block">
              Priority / Category
            </span>
            <span className="text-xs font-medium text-[#1C1917] capitalize">
              {notification.priority ?? 'normal'} /{' '}
              {notification.category || 'transactional'}
            </span>
          </div>
          {notification.batch_id && (
            <div>
              <span className="text-[11px] text-[#78716C] block">Batch ID</span>
              <Link
                to={`/notifications?batch_id=${encodeURIComponent(
                  notification.batch_id
                )}`}
                className="text-xs font-mono text-[#4F46E5] hover:underline"
              >
                {notification.batch_id}
              </Link>
            </div>
          )}
        </div>

        {/* Timestamps */}
        <div className="bg-white border border-[#E7E5E4] rounded-[8px] p-4 space-y-3">
          <h3 className="text-[11px] font-semibold text-[#78716C] uppercase tracking-wider">
            Timestamps
          </h3>
          <div>
            <span className="text-[11px] text-[#78716C] block">Created</span>
            <span className="text-xs text-[#1C1917]">
              {fmt(notification.created_at)}
            </span>
          </div>
          <div>
            <span className="text-[11px] text-[#78716C] block">Scheduled</span>
            <span className="text-xs text-[#1C1917]">
              {fmt(notification.scheduled_at)}
            </span>
          </div>
          <div>
            <span className="text-[11px] text-[#78716C] block">Sent</span>
            <span className="text-xs text-[#1C1917]">
              {fmt(notification.sent_at)}
            </span>
          </div>
          <div>
            <span className="text-[11px] text-[#78716C] block">Delivered</span>
            <span className="text-xs text-[#1C1917]">
              {fmt(notification.delivered_at)}
            </span>
          </div>
          <div>
            <span className="text-[11px] text-[#78716C] block">Last Updated</span>
            <span className="text-xs text-[#1C1917]">
              {fmt(notification.updated_at)}
            </span>
          </div>
        </div>
      </div>

      {/* Message Body */}
      {notification.body && (
        <Card title="Message Content">
          <pre className="bg-[#FAFAF9] border border-[#E7E5E4] p-4 rounded-[6px] text-xs font-mono text-[#1C1917] overflow-x-auto whitespace-pre-wrap max-h-80">
            {notification.body}
          </pre>
        </Card>
      )}

      {/* Delivery Timeline */}
      <div className="bg-white border border-[#E7E5E4] rounded-[8px] p-5 shadow-xs">
        <h3 className="text-sm font-semibold text-[#1C1917] mb-4">
          Delivery Timeline
        </h3>
        {timeline.length === 0 ? (
          <p className="text-xs text-[#78716C]">
            No delivery attempt records registered yet.
          </p>
        ) : (
          <div className="space-y-4">
            {timeline.map((item, index) => {
              const isSuccess =
                item.outcome === 'success' ||
                item.status === 'delivered' ||
                item.status === 'sent';
              const isFailure =
                item.outcome === 'failure' ||
                item.status === 'failed' ||
                item.status === 'bounced';
              const dotColor = isSuccess
                ? 'bg-[#15803D]'
                : isFailure
                ? 'bg-[#B91C1C]'
                : 'bg-[#A16207]';

              return (
                <div
                  key={item.id || index}
                  className="flex items-start gap-3 border-l-2 border-[#E7E5E4] pl-4 py-1 relative"
                >
                  <span
                    className={`absolute -left-[5px] top-2 h-2 w-2 rounded-full ${dotColor}`}
                  />
                  <div className="flex-1 space-y-1">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="text-xs font-semibold text-[#1C1917] capitalize">
                        Attempt #{item.attempt_number ?? index + 1}:{' '}
                        {item.outcome || item.status}
                      </span>
                      <span className="text-[11px] text-[#78716C]">
                        {fmt(item.created_at || item.attempted_at)}
                      </span>
                    </div>
                    <div className="flex flex-wrap gap-4 text-xs text-[#78716C]">
                      {item.provider && (
                        <span>
                          Provider:{' '}
                          <strong className="text-[#1C1917] font-medium capitalize">
                            {item.provider}
                          </strong>
                        </span>
                      )}
                      {item.duration_ms !== undefined &&
                        item.duration_ms !== null && (
                          <span>Duration: {item.duration_ms} ms</span>
                        )}
                      {item.status_code && (
                        <span>Status code: {item.status_code}</span>
                      )}
                    </div>
                    {item.error_message && (
                      <p className="text-xs text-[#B91C1C] font-mono mt-1 break-all bg-[#FEF2F2] p-2 rounded-[4px] border border-[#FECACA]">
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

      <ConfirmDialog
        open={Boolean(dialogConfig)}
        destructive={dialogConfig?.type === 'cancel'}
        title={dialogConfig?.title || ''}
        message={dialogConfig?.message || ''}
        onConfirm={handleConfirmAction}
        onCancel={() => setDialogConfig(null)}
        loading={actionLoading}
        confirmLabel={
          dialogConfig?.type === 'retry' ? 'Retry Dispatch' : 'Cancel Delivery'
        }
      />
    </div>
  );
}
