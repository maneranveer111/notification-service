import { useState, useEffect, useCallback } from 'react';
import {
  Users,
  Send,
  ShieldCheck,
  RotateCw,
  Clock,
  History,
} from 'lucide-react';
import { apiFetch } from '../../lib/api';
import { useAuth } from '../../lib/auth';
import { describeError } from '../../lib/errors';
import ConfirmDialog from '../../components/ConfirmDialog';
import ErrorBanner from '../../components/ErrorBanner';
import Loading from '../../components/Loading';
import EmptyState from '../../components/EmptyState';
import Button from '../../components/ui/Button';
import Input from '../../components/ui/Input';
import Select from '../../components/ui/Select';
import Card from '../../components/ui/Card';
import Badge from '../../components/ui/Badge';

const ROLES = ['owner', 'admin', 'viewer'];
const INVITE_ROLES = ['admin', 'viewer'];

function getInitials(email) {
  if (!email) return 'U';
  const name = email.split('@')[0];
  return name.slice(0, 2).toUpperCase();
}

export default function TeamPage() {
  const { workspace, user } = useAuth();
  const myRole = workspace?.role || 'viewer';
  const isAdmin = myRole === 'owner' || myRole === 'admin';

  // Members state
  const [members, setMembers] = useState([]);
  const [membersLoading, setMembersLoading] = useState(true);
  const [membersError, setMembersError] = useState(null);
  const [roleErrors, setRoleErrors] = useState({});
  const [removeConfirm, setRemoveConfirm] = useState({
    open: false,
    member: null,
  });
  const [removeLoading, setRemoveLoading] = useState(false);

  // Invitations state
  const [invitations, setInvitations] = useState([]);
  const [invitesLoading, setInvitesLoading] = useState(true);
  const [invitesError, setInvitesError] = useState(null);
  const [revokeConfirm, setRevokeConfirm] = useState({
    open: false,
    invite: null,
  });
  const [revokeLoading, setRevokeLoading] = useState(false);
  const [resendingId, setResendingId] = useState(null);

  // Invite form
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteRole, setInviteRole] = useState('viewer');
  const [inviteLoading, setInviteLoading] = useState(false);
  const [inviteError, setInviteError] = useState(null);
  const [inviteSuccess, setInviteSuccess] = useState(false);

  const loadMembers = useCallback(async () => {
    setMembersLoading(true);
    try {
      const data = await apiFetch('/workspaces/current/members');
      setMembers(data);
      setMembersError(null);
    } catch (e) {
      setMembersError(e);
    } finally {
      setMembersLoading(false);
    }
  }, []);

  const loadInvitations = useCallback(async () => {
    setInvitesLoading(true);
    try {
      const data = await apiFetch('/workspaces/current/invitations');
      setInvitations(data);
      setInvitesError(null);
    } catch (e) {
      setInvitesError(e);
    } finally {
      setInvitesLoading(false);
    }
  }, []);

  useEffect(() => {
    loadMembers();
    if (isAdmin) loadInvitations();
    else setInvitesLoading(false);
  }, [loadMembers, loadInvitations, isAdmin]);

  async function handleRoleChange(member, newRole) {
    setRoleErrors((prev) => ({ ...prev, [member.user_id]: null }));
    try {
      await apiFetch(`/workspaces/current/members/${member.user_id}`, {
        method: 'PATCH',
        body: JSON.stringify({ role: newRole }),
      });
      loadMembers();
    } catch (err) {
      const detail = err?.detail || err?.message || 'Failed to change role.';
      setRoleErrors((prev) => ({
        ...prev,
        [member.user_id]:
          typeof detail === 'string' ? detail : JSON.stringify(detail),
      }));
    }
  }

  async function handleRemove() {
    const member = removeConfirm.member;
    setRemoveLoading(true);
    try {
      await apiFetch(`/workspaces/current/members/${member.user_id}`, {
        method: 'DELETE',
      });
      setRemoveConfirm({ open: false, member: null });
      loadMembers();
    } catch (err) {
      const detail = err?.detail || err?.message || 'Failed to remove member.';
      setRoleErrors((prev) => ({
        ...prev,
        [member.user_id]:
          typeof detail === 'string' ? detail : JSON.stringify(detail),
      }));
      setRemoveConfirm({ open: false, member: null });
    } finally {
      setRemoveLoading(false);
    }
  }

  async function handleRevokeInvite() {
    const invite = revokeConfirm.invite;
    setRevokeLoading(true);
    try {
      await apiFetch(`/workspaces/current/invitations/${invite.id}`, {
        method: 'DELETE',
      });
      setRevokeConfirm({ open: false, invite: null });
      loadInvitations();
    } catch (err) {
      setInvitesError(err);
      setRevokeConfirm({ open: false, invite: null });
    } finally {
      setRevokeLoading(false);
    }
  }

  async function handleResendInvite(invite) {
    setResendingId(invite.id);
    try {
      await apiFetch(`/workspaces/current/invitations/${invite.id}/resend`, {
        method: 'POST',
      });
      loadInvitations();
    } catch (err) {
      setInvitesError(err);
    } finally {
      setResendingId(null);
    }
  }

  async function handleInvite(e) {
    e.preventDefault();
    setInviteLoading(true);
    setInviteError(null);
    setInviteSuccess(false);
    try {
      await apiFetch('/workspaces/current/invitations', {
        method: 'POST',
        body: JSON.stringify({
          email: inviteEmail.trim(),
          role: inviteRole,
        }),
      });
      setInviteEmail('');
      setInviteRole('viewer');
      setInviteSuccess(true);
      loadInvitations();
    } catch (err) {
      const desc = describeError(err);
      setInviteError(desc.title + ': ' + desc.message);
    } finally {
      setInviteLoading(false);
    }
  }

  const isSelf = (member) => member.email === user?.email;
  const now = new Date();

  // Split invitations into active pending vs historical
  const pendingInvitations = invitations.filter(
    (inv) => inv.status === 'pending' && new Date(inv.expires_at) > now
  );

  const historyInvitations = invitations.filter(
    (inv) => inv.status !== 'pending' || new Date(inv.expires_at) <= now
  );

  return (
    <div className="space-y-6">
      {/* SECTION A: Members */}
      <div className="bg-white border border-[#E7E5E4] rounded-[8px] overflow-hidden shadow-xs">
        <div className="px-5 py-4 border-b border-[#E7E5E4] flex items-center justify-between">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold text-[#1C1917]">Workspace Members</h3>
            <Badge variant="neutral" size="sm">
              {members.length} active
            </Badge>
          </div>
          <div className="flex items-center gap-1.5 text-xs text-[#78716C]">
            <ShieldCheck className="w-3.5 h-3.5 text-[#15803D]" strokeWidth={1.5} />
            <span>Role-based access active</span>
          </div>
        </div>

        {membersError && (
          <div className="p-4">
            <ErrorBanner error={membersError} onRetry={loadMembers} />
          </div>
        )}

        {membersLoading ? (
          <Loading text="Loading members…" />
        ) : members.length === 0 ? (
          <EmptyState
            icon={Users}
            title="No members"
            message="No members found in this workspace."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs min-w-[550px]">
              <thead className="bg-[#FAFAF9] border-b border-[#E7E5E4] text-[11px] font-semibold text-[#78716C] uppercase tracking-wider">
                <tr>
                  <th className="px-5 py-3">User / Email</th>
                  <th className="px-5 py-3">Role</th>
                  <th className="px-5 py-3">Status</th>
                  {isAdmin && <th className="px-5 py-3 text-right">Actions</th>}
                </tr>
              </thead>
              <tbody className="divide-y divide-[#E7E5E4]">
                {members.map((member) => (
                  <tr
                    key={member.user_id}
                    className="hover:bg-[#FAFAF9]/60 transition-colors h-[48px]"
                  >
                    <td className="px-5 py-3">
                      <div className="flex items-center gap-3">
                        <div className="w-7 h-7 rounded-full bg-[#F5F5F4] border border-[#E7E5E4] flex items-center justify-center text-[11px] font-semibold text-[#1C1917] shrink-0">
                          {getInitials(member.full_name || member.email)}
                        </div>
                        <div className="min-w-0">
                          <p className="text-xs font-medium text-[#1C1917] truncate">
                            {member.full_name || member.email}
                          </p>
                          {member.full_name && (
                            <p className="text-[11px] text-[#78716C] truncate">
                              {member.email}
                            </p>
                          )}
                          {isSelf(member) && (
                            <span className="text-[10px] text-[#78716C]">
                              (Current user)
                            </span>
                          )}
                        </div>
                      </div>
                    </td>
                    <td className="px-5 py-3">
                      {isAdmin && !isSelf(member) ? (
                        <div className="space-y-1">
                          <select
                            value={member.role}
                            onChange={(e) =>
                              handleRoleChange(member, e.target.value)
                            }
                            className="bg-white border border-[#E7E5E4] rounded-[4px] px-2 py-1 text-xs text-[#1C1917] focus:outline-none focus:border-[#4F46E5] capitalize"
                            aria-label={`Role for ${member.email}`}
                          >
                            {ROLES.filter(
                              (r) => myRole === 'owner' || r !== 'owner'
                            ).map((r) => (
                              <option key={r} value={r}>
                                {r.charAt(0).toUpperCase() + r.slice(1)}
                              </option>
                            ))}
                          </select>
                          {roleErrors[member.user_id] && (
                            <p className="text-[11px] text-[#B91C1C]">
                              {roleErrors[member.user_id]}
                            </p>
                          )}
                        </div>
                      ) : (
                        <Badge
                          variant={
                            member.role === 'owner'
                              ? 'neutral'
                              : member.role === 'admin'
                              ? 'accent'
                              : 'neutral'
                          }
                          dot
                          size="sm"
                        >
                          <span className="capitalize">{member.role}</span>
                        </Badge>
                      )}
                    </td>
                    <td className="px-5 py-3">
                      <Badge variant="success" dot size="sm">
                        Active
                      </Badge>
                    </td>
                    {isAdmin && (
                      <td className="px-5 py-3 text-right">
                        {!isSelf(member) && (
                          <Button
                            variant="ghost"
                            size="sm"
                            className="text-[#B91C1C] hover:text-[#991B1B] hover:bg-[#FEF2F2]"
                            onClick={() =>
                              setRemoveConfirm({ open: true, member })
                            }
                          >
                            Remove
                          </Button>
                        )}
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Invite Member Section (Admin only) */}
      {isAdmin && (
        <Card
          title="Invite team member"
          subtitle="They'll receive an email invitation with instructions to join this workspace."
        >
          <form
            onSubmit={handleInvite}
            className="flex flex-col sm:flex-row items-stretch sm:items-end gap-3"
          >
            <div className="flex-1">
              <Input
                id="invite-email"
                label="Email Address *"
                type="email"
                required
                value={inviteEmail}
                onChange={(e) => setInviteEmail(e.target.value)}
                placeholder="colleague@example.com"
              />
            </div>
            <div className="w-full sm:w-40">
              <Select
                id="invite-role"
                label="Assigned Role"
                value={inviteRole}
                onChange={(e) => setInviteRole(e.target.value)}
              >
                {INVITE_ROLES.map((r) => (
                  <option key={r} value={r} className="capitalize">
                    {r.charAt(0).toUpperCase() + r.slice(1)}
                  </option>
                ))}
              </Select>
            </div>
            <Button
              type="submit"
              variant="primary"
              size="md"
              loading={inviteLoading}
              disabled={!inviteEmail.trim()}
              icon={Send}
            >
              Send Invite
            </Button>
          </form>

          {inviteError && (
            <p className="text-xs text-[#B91C1C] mt-2">{inviteError}</p>
          )}
          {inviteSuccess && (
            <p className="text-xs text-[#15803D] mt-2">
              Invitation dispatched successfully.
            </p>
          )}
        </Card>
      )}

      {/* SECTION B: Pending Invitations Section (Admin only) */}
      {isAdmin && (
        <div className="bg-white border border-[#E7E5E4] rounded-[8px] overflow-hidden shadow-xs">
          <div className="px-5 py-4 border-b border-[#E7E5E4] flex items-center justify-between">
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-semibold text-[#1C1917]">
                Pending invitations
              </h3>
              <Badge variant="warning" size="sm">
                {pendingInvitations.length} pending
              </Badge>
            </div>
            <span className="text-xs text-[#78716C]">
              Links expire after 7 days
            </span>
          </div>

          {invitesError && (
            <div className="p-4">
              <ErrorBanner error={invitesError} onRetry={loadInvitations} />
            </div>
          )}

          {invitesLoading ? (
            <Loading text="Loading invitations…" />
          ) : pendingInvitations.length === 0 ? (
            <div className="p-8 text-center text-xs text-[#78716C]">
              No pending invitations for this workspace.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs min-w-[550px]">
                <thead className="bg-[#FAFAF9] border-b border-[#E7E5E4] text-[11px] font-semibold text-[#78716C] uppercase tracking-wider">
                  <tr>
                    <th className="px-5 py-3">Email Address</th>
                    <th className="px-5 py-3">Assigned Role</th>
                    <th className="px-5 py-3">Sent Date</th>
                    <th className="px-5 py-3">Expires</th>
                    <th className="px-5 py-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#E7E5E4]">
                  {pendingInvitations.map((inv) => (
                    <tr
                      key={inv.id}
                      className="hover:bg-[#FAFAF9]/60 transition-colors h-[48px]"
                    >
                      <td className="px-5 py-3 font-medium text-[#1C1917]">
                        {inv.email}
                      </td>
                      <td className="px-5 py-3">
                        <Badge
                          variant={inv.role === 'admin' ? 'accent' : 'neutral'}
                          size="sm"
                        >
                          <span className="capitalize">{inv.role}</span>
                        </Badge>
                      </td>
                      <td className="px-5 py-3 text-[#78716C]">
                        {inv.created_at
                          ? new Date(inv.created_at).toLocaleDateString()
                          : '—'}
                      </td>
                      <td className="px-5 py-3 text-[#78716C]">
                        <div className="flex items-center gap-1.5">
                          <Clock className="w-3.5 h-3.5 text-[#A8A29E]" />
                          <span>
                            {inv.expires_at
                              ? new Date(inv.expires_at).toLocaleDateString()
                              : '—'}
                          </span>
                        </div>
                      </td>
                      <td className="px-5 py-3 text-right space-x-2">
                        <Button
                          variant="ghost"
                          size="sm"
                          icon={RotateCw}
                          loading={resendingId === inv.id}
                          onClick={() => handleResendInvite(inv)}
                        >
                          Resend
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="text-[#B91C1C] hover:text-[#991B1B] hover:bg-[#FEF2F2]"
                          onClick={() =>
                            setRevokeConfirm({ open: true, invite: inv })
                          }
                        >
                          Cancel
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* SECTION C: Invitation History Section (Admin only) */}
      {isAdmin && (
        <div className="bg-white border border-[#E7E5E4] rounded-[8px] overflow-hidden shadow-xs">
          <div className="px-5 py-4 border-b border-[#E7E5E4] flex items-center justify-between">
            <div className="flex items-center gap-2">
              <History className="w-4 h-4 text-[#78716C]" strokeWidth={1.5} />
              <h3 className="text-sm font-semibold text-[#1C1917]">
                Invitation history
              </h3>
              <Badge variant="neutral" size="sm">
                {historyInvitations.length} total
              </Badge>
            </div>
            <span className="text-xs text-[#78716C]">
              Past accepted, cancelled, and expired invitations
            </span>
          </div>

          {invitesLoading ? (
            <Loading text="Loading invitation history…" />
          ) : historyInvitations.length === 0 ? (
            <div className="p-8 text-center text-xs text-[#78716C]">
              No invitation history recorded for this workspace.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs min-w-[550px]">
                <thead className="bg-[#FAFAF9] border-b border-[#E7E5E4] text-[11px] font-semibold text-[#78716C] uppercase tracking-wider">
                  <tr>
                    <th className="px-5 py-3">Email Address</th>
                    <th className="px-5 py-3">Assigned Role</th>
                    <th className="px-5 py-3">Final Status</th>
                    <th className="px-5 py-3">Date</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#E7E5E4]">
                  {historyInvitations.map((inv) => {
                    const isExpired =
                      inv.status === 'expired' ||
                      (inv.status === 'pending' && new Date(inv.expires_at) <= now);
                    const effectiveStatus = isExpired ? 'expired' : inv.status;

                    let statusBadge = (
                      <Badge variant="neutral" size="sm">
                        {effectiveStatus}
                      </Badge>
                    );
                    if (effectiveStatus === 'accepted') {
                      statusBadge = (
                        <Badge variant="success" dot size="sm">
                          Accepted
                        </Badge>
                      );
                    } else if (effectiveStatus === 'revoked') {
                      statusBadge = (
                        <Badge variant="error" dot size="sm">
                          Cancelled
                        </Badge>
                      );
                    } else if (effectiveStatus === 'declined') {
                      statusBadge = (
                        <Badge variant="neutral" dot size="sm">
                          Declined
                        </Badge>
                      );
                    } else if (effectiveStatus === 'expired') {
                      statusBadge = (
                        <Badge variant="warning" dot size="sm">
                          Expired
                        </Badge>
                      );
                    }

                    let dateLabel = '—';
                    if (effectiveStatus === 'accepted') {
                      dateLabel = `Accepted ${
                        inv.accepted_at
                          ? new Date(inv.accepted_at).toLocaleDateString()
                          : new Date(inv.created_at).toLocaleDateString()
                      }`;
                    } else if (effectiveStatus === 'expired') {
                      dateLabel = `Expired ${new Date(
                        inv.expires_at
                      ).toLocaleDateString()}`;
                    } else if (inv.created_at) {
                      dateLabel = `Sent ${new Date(
                        inv.created_at
                      ).toLocaleDateString()}`;
                    }

                    return (
                      <tr
                        key={inv.id}
                        className="hover:bg-[#FAFAF9]/60 transition-colors h-[48px]"
                      >
                        <td className="px-5 py-3 font-medium text-[#1C1917]">
                          {inv.email}
                        </td>
                        <td className="px-5 py-3">
                          <Badge
                            variant={inv.role === 'admin' ? 'accent' : 'neutral'}
                            size="sm"
                          >
                            <span className="capitalize">{inv.role}</span>
                          </Badge>
                        </td>
                        <td className="px-5 py-3">{statusBadge}</td>
                        <td className="px-5 py-3 text-[#78716C]">{dateLabel}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Remove Member Dialog */}
      <ConfirmDialog
        open={removeConfirm.open}
        destructive
        title="Remove member?"
        message={`Remove ${removeConfirm.member?.email} from this workspace? They will lose all access.`}
        confirmLabel="Remove Member"
        loading={removeLoading}
        onConfirm={handleRemove}
        onCancel={() => setRemoveConfirm({ open: false, member: null })}
      />

      {/* Revoke Invitation Dialog */}
      <ConfirmDialog
        open={revokeConfirm.open}
        destructive
        title="Cancel invitation?"
        message={`Cancel the pending invitation for ${revokeConfirm.invite?.email}? They will no longer be able to accept it.`}
        confirmLabel="Cancel Invitation"
        loading={revokeLoading}
        onConfirm={handleRevokeInvite}
        onCancel={() => setRevokeConfirm({ open: false, invite: null })}
      />
    </div>
  );
}
