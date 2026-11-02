import { useState, useEffect, useCallback } from 'react';
import { apiFetch } from '../../lib/api';
import { useAuth } from '../../lib/auth';
import { describeError } from '../../lib/errors';
import ConfirmDialog from '../../components/ConfirmDialog';
import ErrorBanner from '../../components/ErrorBanner';
import Loading from '../../components/Loading';
import EmptyState from '../../components/EmptyState';

const ROLES = ['viewer', 'admin', 'owner'];
const INVITE_ROLES = ['viewer', 'admin'];

function InviteStatusBadge({ status }) {
  const styles = {
    pending: 'bg-yellow-800 text-yellow-200',
    accepted: 'bg-green-800 text-green-200',
    revoked: 'bg-gray-700 text-gray-400',
    expired: 'bg-red-900 text-red-300',
  };
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${styles[status] || styles.pending}`}>
      {status}
    </span>
  );
}

export default function TeamPage() {
  const { isAdmin, role: myRole, user } = useAuth();

  // Members
  const [members, setMembers] = useState([]);
  const [membersLoading, setMembersLoading] = useState(true);
  const [membersError, setMembersError] = useState(null);
  const [roleErrors, setRoleErrors] = useState({});
  const [removeConfirm, setRemoveConfirm] = useState({ open: false, member: null });
  const [removeLoading, setRemoveLoading] = useState(false);

  // Invitations
  const [invitations, setInvitations] = useState([]);
  const [invitesLoading, setInvitesLoading] = useState(true);
  const [invitesError, setInvitesError] = useState(null);
  const [revokeConfirm, setRevokeConfirm] = useState({ open: false, invite: null });
  const [revokeLoading, setRevokeLoading] = useState(false);

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
      setRoleErrors((prev) => ({ ...prev, [member.user_id]: typeof detail === 'string' ? detail : JSON.stringify(detail) }));
    }
  }

  async function handleRemove() {
    const member = removeConfirm.member;
    setRemoveLoading(true);
    try {
      await apiFetch(`/workspaces/current/members/${member.user_id}`, { method: 'DELETE' });
      setRemoveConfirm({ open: false, member: null });
      loadMembers();
    } catch (err) {
      const detail = err?.detail || err?.message || 'Failed to remove member.';
      setRoleErrors((prev) => ({ ...prev, [member.user_id]: typeof detail === 'string' ? detail : JSON.stringify(detail) }));
      setRemoveConfirm({ open: false, member: null });
    } finally {
      setRemoveLoading(false);
    }
  }

  async function handleResend(inviteId) {
    try {
      await apiFetch(`/workspaces/current/invitations/${inviteId}/resend`, { method: 'POST' });
      loadInvitations();
    } catch (err) {
      setInvitesError(err);
    }
  }

  async function handleRevokeInvite() {
    const invite = revokeConfirm.invite;
    setRevokeLoading(true);
    try {
      await apiFetch(`/workspaces/current/invitations/${invite.id}`, { method: 'DELETE' });
      setRevokeConfirm({ open: false, invite: null });
      loadInvitations();
    } catch (err) {
      setInvitesError(err);
      setRevokeConfirm({ open: false, invite: null });
    } finally {
      setRevokeLoading(false);
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
        body: JSON.stringify({ email: inviteEmail.trim(), role: inviteRole }),
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

  return (
    <div className="space-y-8">
      {/* Members section */}
      <div className="space-y-4">
        <h2 className="text-base font-semibold text-white">Members</h2>

        {membersError && <ErrorBanner error={membersError} onRetry={loadMembers} />}

        {membersLoading ? (
          <Loading text="Loading members…" />
        ) : members.length === 0 ? (
          <EmptyState message="No members found." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[400px]">
              <thead>
                <tr className="text-left text-xs text-gray-400 uppercase tracking-wide border-b border-gray-800">
                  <th className="pb-3 pr-4">Email</th>
                  <th className="pb-3 pr-4">Role</th>
                  {isAdmin && <th className="pb-3">Actions</th>}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800">
                {members.map((member) => (
                  <tr key={member.user_id} className="text-gray-300">
                    <td className="py-3 pr-4">
                      <span className={isSelf(member) ? 'text-white font-medium' : ''}>{member.email}</span>
                      {isSelf(member) && <span className="ml-2 text-xs text-gray-500">(you)</span>}
                    </td>
                    <td className="py-3 pr-4">
                      {isAdmin && !isSelf(member) ? (
                        <select
                          value={member.role}
                          onChange={(e) => handleRoleChange(member, e.target.value)}
                          className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-sm text-gray-200 focus:outline-none focus:border-blue-500"
                          aria-label={`Role for ${member.email}`}
                        >
                          {ROLES.filter((r) => myRole === 'owner' || r !== 'owner').map((r) => (
                            <option key={r} value={r}>{r}</option>
                          ))}
                        </select>
                      ) : (
                        <span className="capitalize text-gray-400">{member.role}</span>
                      )}
                      {roleErrors[member.user_id] && (
                        <p className="text-xs text-red-400 mt-1">{roleErrors[member.user_id]}</p>
                      )}
                    </td>
                    {isAdmin && (
                      <td className="py-3">
                        {!isSelf(member) && (
                          <button
                            type="button"
                            onClick={() => setRemoveConfirm({ open: true, member })}
                            className="px-3 py-1 text-xs rounded bg-red-900 hover:bg-red-800 text-red-200 font-medium"
                          >
                            Remove
                          </button>
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

      {/* Invitations section (admin only) */}
      {isAdmin && (
        <div className="space-y-4">
          <h2 className="text-base font-semibold text-white">Invitations</h2>

          {/* Invite form */}
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 space-y-3">
            <h3 className="text-sm font-medium text-gray-300">Invite someone</h3>
            <form onSubmit={handleInvite} className="flex flex-wrap gap-3 items-end">
              <div className="flex-1 min-w-[200px]">
                <label htmlFor="invite-email" className="block text-xs text-gray-400 mb-1">Email *</label>
                <input
                  id="invite-email"
                  type="email"
                  required
                  value={inviteEmail}
                  onChange={(e) => setInviteEmail(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 text-sm"
                  placeholder="colleague@example.com"
                />
              </div>
              <div>
                <label htmlFor="invite-role" className="block text-xs text-gray-400 mb-1">Role</label>
                <select
                  id="invite-role"
                  value={inviteRole}
                  onChange={(e) => setInviteRole(e.target.value)}
                  className="px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 text-gray-200 focus:outline-none focus:border-blue-500 text-sm"
                >
                  {INVITE_ROLES.map((r) => (
                    <option key={r} value={r}>{r}</option>
                  ))}
                </select>
              </div>
              <button
                type="submit"
                disabled={inviteLoading || !inviteEmail.trim()}
                className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm font-medium transition-colors"
              >
                {inviteLoading ? 'Sending…' : 'Send invite'}
              </button>
            </form>
            {inviteError && <p className="text-sm text-red-400">{inviteError}</p>}
            {inviteSuccess && <p className="text-sm text-green-400">Invitation sent!</p>}
          </div>

          {invitesError && <ErrorBanner error={invitesError} onRetry={loadInvitations} />}

          {invitesLoading ? (
            <Loading text="Loading invitations…" />
          ) : invitations.length === 0 ? (
            <EmptyState message="No pending invitations." />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm min-w-[500px]">
                <thead>
                  <tr className="text-left text-xs text-gray-400 uppercase tracking-wide border-b border-gray-800">
                    <th className="pb-3 pr-4">Email</th>
                    <th className="pb-3 pr-4">Role</th>
                    <th className="pb-3 pr-4">Status</th>
                    <th className="pb-3 pr-4">Expires</th>
                    <th className="pb-3">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-800">
                  {invitations.map((inv) => (
                    <tr key={inv.id} className="text-gray-300">
                      <td className="py-3 pr-4">{inv.email}</td>
                      <td className="py-3 pr-4 capitalize">{inv.role}</td>
                      <td className="py-3 pr-4">
                        <InviteStatusBadge status={inv.status} />
                      </td>
                      <td className="py-3 pr-4 text-gray-400">
                        {inv.expires_at ? new Date(inv.expires_at).toLocaleDateString() : '—'}
                      </td>
                      <td className="py-3">
                        {inv.status === 'pending' && (
                          <div className="flex items-center gap-2">
                            <button
                              type="button"
                              onClick={() => handleResend(inv.id)}
                              className="px-2 py-1 text-xs rounded bg-gray-700 hover:bg-gray-600 text-gray-300"
                            >
                              Resend
                            </button>
                            <button
                              type="button"
                              onClick={() => setRevokeConfirm({ open: true, invite: inv })}
                              className="px-2 py-1 text-xs rounded bg-red-900 hover:bg-red-800 text-red-200"
                            >
                              Revoke
                            </button>
                          </div>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      <ConfirmDialog
        open={removeConfirm.open}
        title="Remove member?"
        message={`Remove ${removeConfirm.member?.email} from this workspace?`}
        confirmLabel="Remove"
        loading={removeLoading}
        onConfirm={handleRemove}
        onCancel={() => setRemoveConfirm({ open: false, member: null })}
      />

      <ConfirmDialog
        open={revokeConfirm.open}
        title="Revoke invitation?"
        message={`Revoke the invitation for ${revokeConfirm.invite?.email}?`}
        confirmLabel="Revoke"
        loading={revokeLoading}
        onConfirm={handleRevokeInvite}
        onCancel={() => setRevokeConfirm({ open: false, invite: null })}
      />
    </div>
  );
}
