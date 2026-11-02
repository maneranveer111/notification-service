import { useEffect, useRef, useState } from 'react';
import { useNavigate, useSearchParams, Link } from 'react-router-dom';
import { useAuth } from '../lib/auth';
import { getPublicConfig, apiFetch, ApiError } from '../lib/api';
import { describeError } from '../lib/errors';
import Captcha from '../components/Captcha';

/**
 * Returns the redirect destination only when it is a safe same-origin path:
 *   - must start with exactly one "/"
 *   - must NOT start with "//" (protocol-relative URL)
 *   - must NOT contain "://" (absolute URL with scheme)
 *   - must NOT start with "/\" (IE-era bypass: /\evil.com)
 * Falls back to "/" for anything that doesn't pass.
 */
function getSafeRedirect(searchParams) {
  const dest = searchParams.get('redirect') || searchParams.get('next') || '';
  if (
    dest.startsWith('/') &&
    !dest.startsWith('//') &&
    !dest.startsWith('/\\') &&
    !dest.includes('://')
  ) {
    return dest;
  }
  return '/';
}

export default function LoginPage() {
  const { user, loading: authLoading, login } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  const [config, setConfig] = useState(null);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  // Resend-verification mode
  const [resendMode, setResendMode] = useState(false);
  const [resendLoading, setResendLoading] = useState(false);
  const [resendDone, setResendDone] = useState(false);
  const [resendCooldown, setResendCooldown] = useState(0);
  const [captchaToken, setCaptchaToken] = useState(null);
  const [resetSignal, setResetSignal] = useState(0);

  const cooldownRef = useRef(null);

  useEffect(() => {
    getPublicConfig().then(setConfig);
  }, []);

  // Redirect if already logged in
  useEffect(() => {
    if (!authLoading && user) {
      navigate(getSafeRedirect(searchParams), { replace: true });
    }
  }, [user, authLoading, navigate, searchParams]);

  useEffect(() => {
    return () => {
      if (cooldownRef.current) clearInterval(cooldownRef.current);
    };
  }, []);

  function startCooldown() {
    setResendCooldown(60);
    cooldownRef.current = setInterval(() => {
      setResendCooldown(prev => {
        if (prev <= 1) {
          clearInterval(cooldownRef.current);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await login(email, password);
      navigate(getSafeRedirect(searchParams), { replace: true });
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 401) {
          setError('Invalid email or password.');
        } else if (err.status === 403 && err.code === 'email_not_verified') {
          setResendMode(true);
        } else {
          const desc = describeError(err);
          setError(desc.title + ': ' + desc.message);
        }
      } else {
        const desc = describeError(err);
        setError(desc.title + ': ' + desc.message);
      }
    } finally {
      setLoading(false);
    }
  }

  async function handleResend(e) {
    e.preventDefault();
    setResendLoading(true);
    try {
      await apiFetch('/auth/resend-verification', {
        method: 'POST',
        body: JSON.stringify({ email, captcha_token: captchaToken || undefined }),
      });
      setResendDone(true);
      startCooldown();
    } catch {
      // per spec: always show success message regardless
      setResendDone(true);
      startCooldown();
    } finally {
      setResendLoading(false);
      setResetSignal(s => s + 1);
      setCaptchaToken(null);
    }
  }

  if (authLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
        <p className="text-gray-500">Loading...</p>
      </div>
    );
  }

  if (resendMode) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
        <div className="w-full max-w-md bg-white rounded-xl shadow-md p-8">
          <h1 className="text-xl font-bold text-gray-900 mb-2">Verify your email</h1>
          <p className="text-gray-600 mb-6">
            Your email address has not been verified. Enter your email below to receive a new
            verification link.
          </p>
          {resendDone ? (
            <>
              <p className="text-green-700 text-sm mb-4">
                If that account exists, we sent an email.
              </p>
              {resendCooldown > 0 && (
                <p className="text-gray-500 text-sm">
                  You can request another in {resendCooldown}s.
                </p>
              )}
            </>
          ) : (
            <form onSubmit={handleResend} className="space-y-4">
              <div>
                <label htmlFor="resend-email" className="block text-sm font-medium text-gray-700">
                  Email address
                </label>
                <input
                  id="resend-email"
                  type="email"
                  required
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>
              {config?.turnstile_site_key && (
                <Captcha
                  siteKey={config.turnstile_site_key}
                  onToken={setCaptchaToken}
                  resetSignal={resetSignal}
                />
              )}
              <button
                type="submit"
                disabled={resendLoading}
                className="w-full py-2 px-4 bg-indigo-600 text-white rounded-md text-sm font-medium hover:bg-indigo-700 disabled:opacity-50"
              >
                {resendLoading ? 'Sending...' : 'Send verification email'}
              </button>
            </form>
          )}
          <button
            type="button"
            onClick={() => setResendMode(false)}
            className="mt-4 block text-sm text-indigo-600 hover:underline"
          >
            Back to login
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
      <div className="w-full max-w-md bg-white rounded-xl shadow-md p-8">
        <h1 className="text-xl font-bold text-gray-900 mb-6">Sign in to your account</h1>
        {error && (
          <div className="mb-4 px-4 py-3 rounded-lg bg-red-50 border border-red-200 text-red-700 text-sm">
            {error}
          </div>
        )}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="email" className="block text-sm font-medium text-gray-700">
              Email
            </label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={e => setEmail(e.target.value)}
              className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>
          <div>
            <label htmlFor="password" className="block text-sm font-medium text-gray-700">
              Password
            </label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={e => setPassword(e.target.value)}
              className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>
          <div className="flex items-center justify-end">
            <Link to="/forgot-password" className="text-sm text-indigo-600 hover:underline">
              Forgot password?
            </Link>
          </div>
          <button
            type="submit"
            disabled={loading}
            className="w-full py-2 px-4 bg-indigo-600 text-white rounded-md text-sm font-medium hover:bg-indigo-700 disabled:opacity-50"
          >
            {loading ? 'Signing in...' : 'Sign in'}
          </button>
        </form>
        <p className="mt-4 text-sm text-gray-600">
          {config?.signup_mode === 'open' || config?.needs_setup ? (
            <>
              Don't have an account?{' '}
              <Link to="/signup" className="text-indigo-600 hover:underline">
                Create an account
              </Link>
            </>
          ) : (
            'Accounts are created by invitation.'
          )}
        </p>
      </div>
    </div>
  );
}
