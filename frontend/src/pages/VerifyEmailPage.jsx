import { useEffect, useRef, useState } from 'react';
import { useNavigate, useSearchParams, Link } from 'react-router-dom';
import { apiFetch } from '../lib/api';
import { useAuth } from '../lib/auth';
import Captcha from '../components/Captcha';
import { getPublicConfig } from '../lib/api';

export default function VerifyEmailPage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token');
  const { loginWithResponse } = useAuth();
  const navigate = useNavigate();
  const calledRef = useRef(false);
  const [status, setStatus] = useState('loading'); // 'loading'|'success'|'error'
  const [error, setError] = useState(null);
  const [resendEmail, setResendEmail] = useState('');
  const [captchaToken, setCaptchaToken] = useState(null);
  const [config, setConfig] = useState(null);
  const [resendDone, setResendDone] = useState(false);
  const [resendLoading, setResendLoading] = useState(false);

  useEffect(() => {
    getPublicConfig().then(setConfig);
  }, []);

  useEffect(() => {
    if (calledRef.current) return;
    calledRef.current = true;
    if (!token) { setStatus('error'); return; }
    apiFetch('/auth/verify-email', { method: 'POST', body: JSON.stringify({ token }) })
      .then(body => { loginWithResponse(body); navigate('/'); })
      .catch(() => setStatus('error'));
  }, []);

  if (status === 'loading') return <div className="min-h-screen flex items-center justify-center"><p>Verifying...</p></div>;

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
      <div className="w-full max-w-md bg-white rounded-xl shadow-md p-8">
        <h1 className="text-xl font-bold mb-4">Verification failed</h1>
        <p className="text-gray-600 mb-4">This link is invalid or expired.</p>
        {!resendDone ? (
          <>
            <div className="space-y-3">
              <div>
                <label className="block text-sm font-medium text-gray-700">Email address</label>
                <input type="email" className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm" value={resendEmail} onChange={e => setResendEmail(e.target.value)} />
              </div>
              {config?.turnstile_site_key && <Captcha siteKey={config.turnstile_site_key} onToken={setCaptchaToken} resetSignal={null} />}
              <button
                onClick={async () => {
                  setResendLoading(true);
                  try { await apiFetch('/auth/resend-verification', { method: 'POST', body: JSON.stringify({ email: resendEmail, captcha_token: captchaToken || undefined }) }); setResendDone(true); } catch {}
                  setResendLoading(false);
                }}
                disabled={resendLoading || !resendEmail}
                className="w-full py-2 px-4 bg-indigo-600 text-white rounded-md text-sm font-medium hover:bg-indigo-700 disabled:opacity-50"
              >
                {resendLoading ? 'Sending...' : 'Resend verification email'}
              </button>
            </div>
          </>
        ) : <p className="text-green-600">If that account exists, we sent a new verification email.</p>}
        <Link to="/login" className="mt-4 block text-sm text-indigo-600 hover:underline">Back to login</Link>
      </div>
    </div>
  );
}
