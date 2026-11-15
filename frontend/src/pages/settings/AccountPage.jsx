import { useState, useEffect } from 'react';
import { Check } from 'lucide-react';
import { apiFetch } from '../../lib/api';
import { useAuth } from '../../lib/auth';
import ConfirmDialog from '../../components/ConfirmDialog';
import ErrorBanner from '../../components/ErrorBanner';
import PasswordInput from '../../components/PasswordInput';
import Button from '../../components/ui/Button';
import Card from '../../components/ui/Card';
import Badge from '../../components/ui/Badge';

export default function AccountPage() {
  const {
    user,
    workspace,
    loginWithResponse,
    refreshWorkspaces,
    switchWorkspace,
  } = useAuth();

  // Change password
  const [currentPw, setCurrentPw] = useState('');
  const [newPw, setNewPw] = useState('');
  const [confirmPw, setConfirmPw] = useState('');
  const [pwLoading, setPwLoading] = useState(false);
  const [pwError, setPwError] = useState(null);
  const [pwSuccess, setPwSuccess] = useState(false);

  // Workspaces
  const [workspacesList, setWorkspacesList] = useState([]);
  const [wsLoading, setWsLoading] = useState(true);
  const [wsError, setWsError] = useState(null);
  const [leaveConfirm, setLeaveConfirm] = useState({ open: false, ws: null });
  const [leaveLoading, setLeaveLoading] = useState(false);
  const [leaveError, setLeaveError] = useState(null);

  useEffect(() => {
    loadWorkspaces();
  }, []);

  async function loadWorkspaces() {
    setWsLoading(true);
    try {
      const data = await apiFetch('/workspaces');
      setWorkspacesList(data);
      setWsError(null);
    } catch (e) {
      setWsError(e);
    } finally {
      setWsLoading(false);
    }
  }

  async function handleChangePassword(e) {
    e.preventDefault();
    setPwError(null);
    setPwSuccess(false);

    if (newPw.length < 8) {
      setPwError('New password must be at least 8 characters.');
      return;
    }
    if (newPw !== confirmPw) {
      setPwError('New password and confirmation do not match.');
      return;
    }

    setPwLoading(true);
    try {
      const body = await apiFetch('/auth/change-password', {
        method: 'POST',
        body: JSON.stringify({
          current_password: currentPw,
          new_password: newPw,
        }),
      });
      loginWithResponse(body);
      setCurrentPw('');
      setNewPw('');
      setConfirmPw('');
      setPwSuccess(true);
    } catch (err) {
      setPwError(err?.detail || err?.message || 'Failed to change password.');
    } finally {
      setPwLoading(false);
    }
  }

  async function handleLeave() {
    const ws = leaveConfirm.ws;
    setLeaveLoading(true);
    setLeaveError(null);

    try {
      const isCurrentWs = ws.id === workspace?.id;

      if (!isCurrentWs) {
        // Switch to target workspace first, then leave
        const switchBody = await apiFetch('/auth/switch-workspace', {
          method: 'POST',
          body: JSON.stringify({ workspace_id: ws.id }),
        });
        loginWithResponse(switchBody);
      }

      await apiFetch('/workspaces/current/leave', { method: 'POST' });

      await refreshWorkspaces();
      const remaining = await apiFetch('/workspaces');
      setWorkspacesList(remaining);
      setLeaveConfirm({ open: false, ws: null });

      if (remaining.length > 0) {
        switchWorkspace(remaining[0].id);
      }
    } catch (err) {
      const msg = err?.detail || err?.message || 'Failed to leave workspace.';
      setLeaveError(typeof msg === 'string' ? msg : JSON.stringify(msg));
    } finally {
      setLeaveLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      {/* Account Email Card */}
      <Card
        title="Account Profile"
        subtitle="Your authenticated account identity."
      >
        <div className="flex items-center justify-between py-2">
          <div>
            <p className="text-xs text-[#78716C]">Email Address</p>
            <p className="text-sm font-medium text-[#1C1917] mt-0.5">
              {user?.email}
            </p>
          </div>
          <Badge variant="neutral" size="sm">
            Verified
          </Badge>
        </div>
      </Card>

      {/* Change Password Card */}
      <Card
        title="Change Password"
        subtitle="Update your security credentials."
      >
        {pwSuccess && (
          <div className="mb-4 px-3.5 py-2.5 rounded-[6px] bg-[#F0FDF4] border border-[#BBF7D0] text-[#15803D] text-xs flex items-center gap-2">
            <Check className="w-4 h-4" strokeWidth={2} />
            <span>Password updated successfully.</span>
          </div>
        )}

        {pwError && (
          <div className="mb-4">
            <ErrorBanner error={pwError} />
          </div>
        )}

        <form onSubmit={handleChangePassword} className="space-y-4 max-w-md">
          <PasswordInput
            id="current-pw"
            label="Current Password"
            value={currentPw}
            onChange={(e) => setCurrentPw(e.target.value)}
            required
            autoComplete="current-password"
          />
          <PasswordInput
            id="new-pw"
            label="New Password (min 8 characters)"
            value={newPw}
            onChange={(e) => setNewPw(e.target.value)}
            required
            autoComplete="new-password"
          />
          <PasswordInput
            id="confirm-pw"
            label="Confirm New Password"
            value={confirmPw}
            onChange={(e) => setConfirmPw(e.target.value)}
            required
            autoComplete="new-password"
          />
          <Button
            type="submit"
            variant="primary"
            size="sm"
            loading={pwLoading}
            disabled={!currentPw || !newPw || !confirmPw}
          >
            Update Password
          </Button>
        </form>
      </Card>

      {/* Your Workspaces Card */}
      <div className="bg-white border border-[#E7E5E4] rounded-[8px] overflow-hidden shadow-xs">
        <div className="px-5 py-4 border-b border-[#E7E5E4]">
          <h3 className="text-sm font-semibold text-[#1C1917]">
            Your Workspaces
          </h3>
          <p className="text-xs text-[#78716C] mt-0.5">
            Workspaces you currently belong to.
          </p>
        </div>

        {wsError && (
          <div className="p-4">
            <ErrorBanner error={wsError} onRetry={loadWorkspaces} />
          </div>
        )}

        {wsLoading ? (
          <div className="p-8 text-center text-xs text-[#78716C]">
            Loading workspaces…
          </div>
        ) : workspacesList.length === 0 ? (
          <div className="p-8 text-center text-xs text-[#78716C]">
            You have no workspaces.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs min-w-[400px]">
              <thead className="bg-[#FAFAF9] border-b border-[#E7E5E4] text-[11px] font-semibold text-[#78716C] uppercase tracking-wider">
                <tr>
                  <th className="px-5 py-3">Workspace</th>
                  <th className="px-5 py-3">Role</th>
                  <th className="px-5 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#E7E5E4]">
                {workspacesList.map((ws) => (
                  <tr
                    key={ws.id}
                    className="hover:bg-[#FAFAF9]/60 transition-colors h-[44px]"
                  >
                    <td className="px-5 py-3 font-medium text-[#1C1917]">
                      {ws.name}
                      {ws.id === workspace?.id && (
                        <span className="ml-2 text-[10px] text-[#4F46E5] font-semibold">
                          (Current)
                        </span>
                      )}
                    </td>
                    <td className="px-5 py-3">
                      <Badge variant="neutral" size="sm">
                        <span className="capitalize">{ws.role}</span>
                      </Badge>
                    </td>
                    <td className="px-5 py-3 text-right">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-[#B91C1C] hover:text-[#991B1B] hover:bg-[#FEF2F2]"
                        onClick={() => setLeaveConfirm({ open: true, ws })}
                      >
                        Leave
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {leaveError && (
          <div className="p-4 border-t border-[#E7E5E4]">
            <ErrorBanner error={leaveError} />
          </div>
        )}
      </div>

      <ConfirmDialog
        open={leaveConfirm.open}
        destructive
        title={`Leave "${leaveConfirm.ws?.name}"?`}
        message="You will lose access to this workspace. If you are the last owner, the request will be rejected."
        confirmLabel="Leave Workspace"
        loading={leaveLoading}
        onConfirm={handleLeave}
        onCancel={() => {
          setLeaveConfirm({ open: false, ws: null });
          setLeaveError(null);
        }}
      />
    </div>
  );
}
