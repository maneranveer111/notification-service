import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams, useLocation } from 'react-router-dom';
import { apiFetch, ApiError } from '../lib/api';
import { useAuth } from '../lib/auth';
import PasswordInput from '../components/PasswordInput';
import Button from '../components/ui/Button';
import { AlertCircle, UserPlus, LogOut } from 'lucide-react';

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
      .then((data) => {
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
      const body = inviteInfo.user_exists ? { token } : { token, password };
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
      <div className="min-h-screen flex items-center justify-center bg-[#FAFAF9]">
        <div className="flex items-center gap-2 text-xs text-[#78716C]">
          <div className="w-4 h-4 border-2 border-[#4F46E5] border-t-transparent rounded-full animate-spin" />
          <span>Loading invitation...</span>
        </div>
      </div>
    );
  }

  if (status === 'error') {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-[#FAFAF9] px-4 py-12">
        <div className="w-full max-w-[400px] bg-white rounded-[10px] border border-[#E7E5E4] shadow-sm p-8 text-center">
          <div className="mx-auto flex items-center justify-center w-10 h-10 rounded-[8px] bg-[#FEF2F2] text-[#B91C1C] mb-4">
            <AlertCircle className="w-5 h-5" strokeWidth={1.5} />
          </div>
          <h1 className="text-xl font-bold tracking-tight text-[#1C1917] mb-2">Invalid invitation</h1>
          <p className="text-xs text-[#78716C] mb-6">This invitation link is invalid or has expired.</p>
        </div>
      </div>
    );
  }

  // Case (c): existing user logged in as wrong email
  if (inviteInfo.user_exists && auth.user && auth.user.email !== inviteInfo.email) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-[#FAFAF9] px-4 py-12">
        <div className="w-full max-w-[400px] bg-white rounded-[10px] border border-[#E7E5E4] shadow-sm p-8">
          <div className="flex items-center justify-center w-10 h-10 rounded-[8px] bg-[#FEF2F2] text-[#B91C1C] mb-5">
            <AlertCircle className="w-5 h-5" strokeWidth={1.5} />
          </div>
          <h1 className="text-xl font-bold tracking-tight text-[#1C1917] mb-2">Wrong account</h1>
          <p className="text-xs text-[#78716C] mb-6 leading-relaxed">
            You are logged in as <strong className="text-[#1C1917]">{auth.user.email}</strong>. This invitation was sent to{' '}
            <strong className="text-[#1C1917]">{inviteInfo.email}</strong>.
          </p>
          <Button
            type="button"
            variant="secondary"
            icon={LogOut}
            onClick={() => auth.logout()}
            className="w-full"
          >
            Log out
          </Button>
        </div>
      </div>
    );
  }

  // Case (b): existing user, not logged in
  if (inviteInfo.user_exists && !auth.user) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-[#FAFAF9] px-4 py-12">
        <div className="w-full max-w-[400px] bg-white rounded-[10px] border border-[#E7E5E4] shadow-sm p-8">
          <div className="flex items-center justify-center w-10 h-10 rounded-[8px] bg-[#EEF2FF] text-[#4F46E5] mb-5">
            <UserPlus className="w-5 h-5" strokeWidth={1.5} />
          </div>
          <h1 className="text-xl font-bold tracking-tight text-[#1C1917] mb-1">
            Join {inviteInfo.workspace_name}
          </h1>
          <p className="text-xs text-[#78716C] mb-6 leading-relaxed">
            You were invited to join <strong className="text-[#1C1917]">{inviteInfo.workspace_name}</strong> as{' '}
            <span className="capitalize font-medium text-[#1C1917]">{inviteInfo.role}</span>. Log in to accept this invitation.
          </p>
          <Button
            type="button"
            onClick={() =>
              navigate('/login?redirect=' + encodeURIComponent(location.pathname + location.search))
            }
            className="w-full"
          >
            Log in to accept
          </Button>
        </div>
      </div>
    );
  }

  // Case (a): existing user logged in as the right email — show accept button
  // Case (d): new user — show password form
  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-[#FAFAF9] px-4 py-12">
      <div className="w-full max-w-[400px] bg-white rounded-[10px] border border-[#E7E5E4] shadow-sm p-8">
        <div className="flex items-center justify-center w-10 h-10 rounded-[8px] bg-[#EEF2FF] text-[#4F46E5] mb-5">
          <UserPlus className="w-5 h-5" strokeWidth={1.5} />
        </div>
        <h1 className="text-xl font-bold tracking-tight text-[#1C1917] mb-1">
          Join {inviteInfo.workspace_name}
        </h1>
        <p className="text-xs text-[#78716C] mb-6 leading-relaxed">
          You were invited to join <strong className="text-[#1C1917]">{inviteInfo.workspace_name}</strong> as{' '}
          <span className="capitalize font-medium text-[#1C1917]">{inviteInfo.role}</span>.
        </p>

        {error && (
          <div className="mb-5 p-3 rounded-[6px] bg-[#FEF2F2] border border-[#FECACA] flex items-start gap-2.5 text-[#B91C1C] text-xs">
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" strokeWidth={1.5} />
            <span>{error}</span>
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
              onChange={(e) => setPassword(e.target.value)}
            />
          )}
          <Button type="submit" loading={submitting} className="w-full mt-2">
            {submitting ? 'Accepting...' : 'Accept invitation'}
          </Button>
        </form>
      </div>
    </div>
  );
}
