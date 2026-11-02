import { useState, useEffect } from 'react';
import { apiFetch } from '../../lib/api';
import { useAuth } from '../../lib/auth';
import ConfirmDialog from '../../components/ConfirmDialog';
import ErrorBanner from '../../components/ErrorBanner';

// Dark-styled PasswordInput
function DarkPasswordInput({ id, label, ...rest }) {
  const [show, setShow] = useState(false);
  return (
    <div className="space-y-1">
      {label && (
        <label htmlFor={id} className="block text-sm font-medium text-gray-300">
          {label}
        </label>
      )}
      <div className="relative">
        <input
          id={id}
          type={show ? 'text' : 'password'}
          className="block w-full rounded-lg bg-gray-800 border border-gray-700 text-white px-3 py-2 pr-10 text-sm placeholder-gray-500 focus:outline-none focus:border-blue-500"
          {...rest}
        />
        <button
          type="button"
          onClick={() => setShow((s) => !s)}
          className="absolute inset-y-0 right-0 flex items-center pr-3 text-gray-400 hover:text-gray-200"
          aria-label={show ? 'Hide password' : 'Show password'}
        >
          {show ? '🙈' : '👁'}
        </button>
      </div>
    </div>
  );
}

export default function AccountPage() {
  const { user, workspace, loginWithResponse, refreshWorkspaces, switchWorkspace } = useAuth();

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
        body: JSON.stringify({ current_password: currentPw, new_password: newPw }),
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
    <div className="space-y-6 max-w-lg">
      {/* Email */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 space-y-2">
        <h2 className="text-base font-semibold text-white">Account</h2>
        <div>
          <p className="text-xs text-gray-500 uppercase tracking-wide mb-1">Email</p>
          <p className="text-sm text-gray-300">{user?.email}</p>
        </div>
      </div>

      {/* Change password */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 space-y-4">
        <h2 className="text-base font-semibold text-white">Change password</h2>

        {pwSuccess && (
          <div className="px-4 py-3 rounded-lg bg-green-900/30 border border-green-700 text-green-300 text-sm">
            ✓ Password updated successfully.
          </div>
        )}
        {pwError && (
          <div className="px-4 py-3 rounded-lg bg-red-900/30 border border-red-700 text-red-300 text-sm">
            {pwError}
          </div>
        )}

        <form onSubmit={handleChangePassword} className="space-y-4">
          <DarkPasswordInput
            id="current-pw"
            label="Current password"
            value={currentPw}
            onChange={(e) => setCurrentPw(e.target.value)}
            required
            autoComplete="current-password"
          />
          <DarkPasswordInput
            id="new-pw"
            label="New password (min 8 characters)"
            value={newPw}
            onChange={(e) => setNewPw(e.target.value)}
            required
            autoComplete="new-password"
          />
          <DarkPasswordInput
            id="confirm-pw"
            label="Confirm new password"
            value={confirmPw}
            onChange={(e) => setConfirmPw(e.target.value)}
            required
            autoComplete="new-password"
          />
          <button
            type="submit"
            disabled={pwLoading || !currentPw || !newPw || !confirmPw}
            className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm font-medium transition-colors"
          >
            {pwLoading ? 'Updating…' : 'Update password'}
          </button>
        </form>
      </div>

      {/* Workspaces */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 space-y-4">
        <h2 className="text-base font-semibold text-white">Your Workspaces</h2>

        {wsError && <ErrorBanner error={wsError} onRetry={loadWorkspaces} />}

        {wsLoading ? (
          <p className="text-sm text-gray-400">Loading…</p>
        ) : workspacesList.length === 0 ? (
          <p className="text-sm text-gray-400">You have no workspaces. Create one to get started.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-gray-400 uppercase tracking-wide border-b border-gray-800">
                  <th className="pb-3 pr-4">Name</th>
                  <th className="pb-3 pr-4">Role</th>
                  <th className="pb-3">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800">
                {workspacesList.map((ws) => (
                  <tr key={ws.id} className="text-gray-300">
                    <td className="py-3 pr-4">
                      <span className={ws.id === workspace?.id ? 'text-white font-medium' : ''}>{ws.name}</span>
                      {ws.id === workspace?.id && <span className="ml-2 text-xs text-blue-400">(current)</span>}
                    </td>
                    <td className="py-3 pr-4 capitalize">{ws.role}</td>
                    <td className="py-3">
                      <button
                        type="button"
                        onClick={() => setLeaveConfirm({ open: true, ws })}
                        className="px-3 py-1 text-xs rounded bg-red-900 hover:bg-red-800 text-red-200"
                      >
                        Leave
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {leaveError && (
          <div className="px-4 py-3 rounded-lg bg-red-900/30 border border-red-700 text-red-300 text-sm">
            {leaveError}
          </div>
        )}
      </div>

      <ConfirmDialog
        open={leaveConfirm.open}
        title={`Leave "${leaveConfirm.ws?.name}"?`}
        message="You will lose access to this workspace. If you are the last owner, you will be blocked."
        confirmLabel="Leave workspace"
        loading={leaveLoading}
        onConfirm={handleLeave}
        onCancel={() => { setLeaveConfirm({ open: false, ws: null }); setLeaveError(null); }}
      />
    </div>
  );
}
