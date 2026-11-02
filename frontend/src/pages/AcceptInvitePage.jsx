import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams, useLocation } from 'react-router-dom';
import { apiFetch, ApiError } from '../lib/api';
import { useAuth } from '../lib/auth';
import PasswordInput from '../components/PasswordInput';

export default function AcceptInvitePage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token');
  const navigate = useNavigate();
  const location = useLocation();
  const auth = useAuth();

  const [inviteInfo, setInviteInfo] = useState(null);
  const [status, setStatus] = useState('loading'); // 'loading'|'loaded'|'error'
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!token) {
      setStatus('error');
      return;
    }
    apiFetch(`/auth/invitation-info?token=${encodeURIComponent(token)}`)
      .then(data => {
        setInviteInfo(data);
        setStatus('loaded');
      })
      .catch(() => setStatus('error'));
  }, [token]);

  async function handleAccept(e) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const body = inviteInfo.user_exists
        ? { token }
        : { token, password };
      const data = await apiFetch('/auth/accept-invitation', {
        method: 'POST',
        body: JSON.stringify(body),
      });
      auth.loginWithResponse(data);
      navigate('/');
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.detail || err.message || 'Failed to accept invitation.');
      } else {
        setError('An unexpected error occurred.');
      }
    } finally {
      setSubmitting(false);
    }
  }

  if (status === 'loading') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
        <p className="text-gray-500">Loading invitation...</p>
      </div>
    );
  }

  if (status === 'error') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
        <div className="w-full max-w-md bg-white rounded-xl shadow-md p-8">
          <h1 className="text-xl font-bold text-gray-900 mb-4">Invalid invitation</h1>
          <p className="text-gray-600">This invitation is invalid or expired.</p>
        </div>
      </div>
    );
  }

  // Case (c): existing user logged in as wrong email
  if (inviteInfo.user_exists && auth.user && auth.user.email !== inviteInfo.email) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
        <div className="w-full max-w-md bg-white rounded-xl shadow-md p-8">
          <h1 className="text-xl font-bold text-gray-900 mb-4">Wrong account</h1>
          <p className="text-gray-600 mb-6">
            You are logged in as <strong>{auth.user.email}</strong>. This invitation is for{' '}
            <strong>{inviteInfo.email}</strong>.
          </p>
          <button
            type="button"
            onClick={() => auth.logout()}
            className="w-full py-2 px-4 bg-indigo-600 text-white rounded-md text-sm font-medium hover:bg-indigo-700"
          >
            Log out
          </button>
        </div>
      </div>
    );
  }

  // Case (b): existing user, not logged in
  if (inviteInfo.user_exists && !auth.user) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
        <div className="w-full max-w-md bg-white rounded-xl shadow-md p-8">
          <h1 className="text-xl font-bold text-gray-900 mb-2">
            Join {inviteInfo.workspace_name}
          </h1>
          <p className="text-gray-600 mb-6">
            You were invited to join <strong>{inviteInfo.workspace_name}</strong> as{' '}
            <strong>{inviteInfo.role}</strong>. Log in to accept this invitation.
          </p>
          <button
            type="button"
            onClick={() =>
              navigate(
                '/login?redirect=' + encodeURIComponent(location.pathname + location.search)
              )
            }
            className="w-full py-2 px-4 bg-indigo-600 text-white rounded-md text-sm font-medium hover:bg-indigo-700"
          >
            Log in to accept
          </button>
        </div>
      </div>
    );
  }

  // Case (a): existing user logged in as the right email — show accept button
  // Case (d): new user — show password form
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
      <div className="w-full max-w-md bg-white rounded-xl shadow-md p-8">
        <h1 className="text-xl font-bold text-gray-900 mb-2">
          Join {inviteInfo.workspace_name}
        </h1>
        <p className="text-gray-600 mb-6">
          You were invited to join <strong>{inviteInfo.workspace_name}</strong> as{' '}
          <strong>{inviteInfo.role}</strong>.
        </p>
        {error && (
          <div className="mb-4 px-4 py-3 rounded-lg bg-red-50 border border-red-200 text-red-700 text-sm">
            {error}
          </div>
        )}
        <form onSubmit={handleAccept} className="space-y-4">
          {!inviteInfo.user_exists && (
            <PasswordInput
              id="password"
              label="Create a password"
              minLength={8}
              required
              value={password}
              onChange={e => setPassword(e.target.value)}
            />
          )}
          <button
            type="submit"
            disabled={submitting}
            className="w-full py-2 px-4 bg-indigo-600 text-white rounded-md text-sm font-medium hover:bg-indigo-700 disabled:opacity-50"
          >
            {submitting ? 'Accepting...' : 'Accept invitation'}
          </button>
        </form>
      </div>
    </div>
  );
}
