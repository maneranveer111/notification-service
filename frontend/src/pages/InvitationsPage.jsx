import { useState, useEffect, useCallback } from 'react';
import {
  Mail,
  Check,
  X,
  RotateCw,
} from 'lucide-react';
import { apiFetch } from '../lib/api';
import { useAuth } from '../lib/auth';
import { describeError } from '../lib/errors';
import Loading from '../components/Loading';
import ErrorBanner from '../components/ErrorBanner';
import EmptyState from '../components/EmptyState';
import Button from '../components/ui/Button';
import Badge from '../components/ui/Badge';

export default function InvitationsPage() {
  const { refreshWorkspaces } = useAuth();
  const [invitations, setInvitations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [actionLoading, setActionLoading] = useState({});
  const [feedback, setFeedback] = useState(null);

  const loadInvitations = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiFetch('/invitations');
      setInvitations(data);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadInvitations();
  }, [loadInvitations]);

  async function handleAccept(inv) {
    setActionLoading((prev) => ({ ...prev, [inv.id]: 'accept' }));
    setFeedback(null);
    try {
      await apiFetch(`/invitations/${inv.id}/accept`, { method: 'POST' });
      await refreshWorkspaces();
      setInvitations((prev) => prev.filter((i) => i.id !== inv.id));
      setFeedback({
        type: 'success',
        message: `Successfully joined "${inv.workspace_name}" as ${inv.role}! You can now switch to it from the workspace selector.`,
      });
    } catch (err) {
      const desc = describeError(err);
      setFeedback({
        type: 'error',
        message: desc.title + ': ' + desc.message,
      });
    } finally {
      setActionLoading((prev) => ({ ...prev, [inv.id]: null }));
    }
  }

  async function handleDecline(inv) {
    setActionLoading((prev) => ({ ...prev, [inv.id]: 'decline' }));
    setFeedback(null);
    try {
      await apiFetch(`/invitations/${inv.id}/decline`, { method: 'POST' });
      setInvitations((prev) => prev.filter((i) => i.id !== inv.id));
      setFeedback({
        type: 'success',
        message: `Declined invitation to "${inv.workspace_name}".`,
      });
    } catch (err) {
      const desc = describeError(err);
      setFeedback({
        type: 'error',
        message: desc.title + ': ' + desc.message,
      });
    } finally {
      setActionLoading((prev) => ({ ...prev, [inv.id]: null }));
    }
  }

  return (
    <div className="space-y-6 max-w-[760px]">
      <div>
        <h1 className="text-xl sm:text-2xl font-semibold text-[#1C1917] tracking-tight">
          Workspace Invitations
        </h1>
        <p className="text-xs sm:text-sm text-[#78716C] mt-0.5">
          Review and respond to pending invitations to collaborate in other workspaces.
        </p>
      </div>

      {feedback && (
        <div
          className={`p-3.5 rounded-[6px] border text-xs flex items-start justify-between gap-3 ${
            feedback.type === 'success'
              ? 'bg-[#F0FDF4] border-[#BBF7D0] text-[#15803D]'
              : 'bg-[#FEF2F2] border-[#FECACA] text-[#B91C1C]'
          }`}
        >
          <div className="flex items-center gap-2">
            <Check className="w-4 h-4 shrink-0" strokeWidth={2} />
            <span>{feedback.message}</span>
          </div>
          <button
            onClick={() => setFeedback(null)}
            className="text-[#78716C] hover:text-[#1C1917]"
            aria-label="Dismiss message"
          >
            <X className="w-4 h-4" strokeWidth={1.5} />
          </button>
        </div>
      )}

      {error && <ErrorBanner error={error} onRetry={loadInvitations} />}

      {loading ? (
        <Loading text="Checking for pending invitations…" />
      ) : invitations.length === 0 ? (
        <EmptyState
          icon={Mail}
          title="No pending invitations"
          message="When someone invites your email address to join their workspace, it will appear here."
        />
      ) : (
        <div className="space-y-3">
          <div className="flex items-center justify-between text-xs text-[#78716C] px-1">
            <span>Pending ({invitations.length})</span>
            <button
              onClick={loadInvitations}
              className="text-[#4F46E5] hover:text-[#4338CA] font-medium flex items-center gap-1 cursor-pointer"
            >
              <RotateCw className="w-3 h-3" />
              Refresh
            </button>
          </div>

          <div className="space-y-3">
            {invitations.map((inv) => {
              const isAccepting = actionLoading[inv.id] === 'accept';
              const isDeclining = actionLoading[inv.id] === 'decline';
              const isBusy = isAccepting || isDeclining;

              return (
                <div
                  key={inv.id}
                  className="bg-white border border-[#E7E5E4] rounded-[8px] p-5 shadow-xs flex flex-col sm:flex-row sm:items-center justify-between gap-4"
                >
                  <div className="space-y-1.5 flex-1 min-w-0">
                    <div className="flex items-center gap-2.5">
                      <h3 className="text-sm font-semibold text-[#1C1917] truncate">
                        {inv.workspace_name}
                      </h3>
                      <Badge variant="neutral" size="sm">
                        <span className="capitalize">{inv.role}</span>
                      </Badge>
                    </div>

                    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-[#78716C]">
                      {inv.invited_by_email && (
                        <span>
                          Invited by{' '}
                          <strong className="text-[#1C1917] font-medium">
                            {inv.invited_by_email}
                          </strong>
                        </span>
                      )}
                      <span>
                        Expires{' '}
                        {inv.expires_at
                          ? new Date(inv.expires_at).toLocaleDateString()
                          : '—'}
                      </span>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 shrink-0">
                    <Button
                      variant="secondary"
                      size="sm"
                      disabled={isBusy}
                      loading={isDeclining}
                      onClick={() => handleDecline(inv)}
                    >
                      Decline
                    </Button>
                    <Button
                      variant="primary"
                      size="sm"
                      disabled={isBusy}
                      loading={isAccepting}
                      onClick={() => handleAccept(inv)}
                      icon={Check}
                    >
                      Accept Invitation
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
