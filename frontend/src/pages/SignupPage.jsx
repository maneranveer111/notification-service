import { useEffect, useRef, useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { getPublicConfig, apiFetch, ApiError } from '../lib/api';
import { useAuth } from '../lib/auth';
import { describeError } from '../lib/errors';
import PasswordInput from '../components/PasswordInput';
import Captcha from '../components/Captcha';

export default function SignupPage() {
  const { loginWithResponse } = useAuth();
  const navigate = useNavigate();

  const [config, setConfig] = useState(null);
  const [configLoading, setConfigLoading] = useState(true);

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [workspaceName, setWorkspaceName] = useState('');
  const [captchaToken, setCaptchaToken] = useState(null);
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [resendCooldown, setResendCooldown] = useState(0);
  const [resetSignal, setResetSignal] = useState(0);

  const cooldownRef = useRef(null);

  useEffect(() => {
    getPublicConfig()
      .then(cfg => setConfig(cfg))
      .finally(() => setConfigLoading(false));
  }, []);

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
    setSubmitting(true);
    try {
      const body = {
        email,
        password,
        workspace_name: config?.needs_setup ? undefined : (workspaceName || undefined),
        captcha_token: captchaToken || undefined,
      };
      const { data, response } = await apiFetch('/auth/signup', {
        method: 'POST',
        body: JSON.stringify(body),
        _raw: true,
      });
      if (response.status === 201) {
        loginWithResponse(data);
        navigate('/');
      } else if (response.status === 202) {
        setSubmitted(true);
      }
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setError('An account with this email already exists.');
      } else {
        const desc = describeError(err);
        setError(desc.title + ': ' + desc.message);
      }
      setResetSignal(s => s + 1);
      setCaptchaToken(null);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleResend() {
    try {
      await apiFetch('/auth/resend-verification', {
        method: 'POST',
        body: JSON.stringify({ email, captcha_token: captchaToken || undefined }),
      });
      startCooldown();
    } catch {
      // silently fail — "check your inbox" already shown
    }
    setResetSignal(s => s + 1);
    setCaptchaToken(null);
  }

  if (configLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
        <p className="text-gray-500">Loading...</p>
      </div>
    );
  }

  if (config?.signup_mode === 'closed' && !config?.needs_setup) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
        <div className="w-full max-w-md bg-white rounded-xl shadow-md p-8 text-center">
          <p className="text-gray-700">Sign-ups are currently closed.</p>
          <Link to="/login" className="mt-4 inline-block text-sm text-indigo-600 hover:underline">
            Back to login
          </Link>
        </div>
      </div>
    );
  }

  if (config?.signup_mode === 'invite_only' && !config?.needs_setup) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
        <div className="w-full max-w-md bg-white rounded-xl shadow-md p-8 text-center">
          <p className="text-gray-700">Accounts are created by invitation only.</p>
          <Link to="/login" className="mt-4 inline-block text-sm text-indigo-600 hover:underline">
            Back to login
          </Link>
        </div>
      </div>
    );
  }

  if (submitted) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
        <div className="w-full max-w-md bg-white rounded-xl shadow-md p-8">
          <h1 className="text-xl font-bold text-gray-900 mb-2">Check your inbox</h1>
          <p className="text-gray-600 mb-6">
            We sent a verification email to <strong>{email}</strong>.
          </p>
          {config?.turnstile_site_key && (
            <div className="mb-4">
              <Captcha
                siteKey={config.turnstile_site_key}
                onToken={setCaptchaToken}
                resetSignal={resetSignal}
              />
            </div>
          )}
          <button
            type="button"
            onClick={handleResend}
            disabled={resendCooldown > 0}
            className="w-full py-2 px-4 bg-indigo-600 text-white rounded-md text-sm font-medium hover:bg-indigo-700 disabled:opacity-50"
          >
            {resendCooldown > 0 ? `Resend in ${resendCooldown}s` : 'Resend verification email'}
          </button>
          <p className="mt-4 text-sm text-gray-500">Check your spam folder too.</p>
          <Link to="/login" className="mt-4 block text-sm text-indigo-600 hover:underline">
            Already have an account? Log in
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
      <div className="w-full max-w-md bg-white rounded-xl shadow-md p-8">
        <h1 className="text-xl font-bold text-gray-900 mb-6">
          {config?.needs_setup ? 'Set up your account' : 'Create an account'}
        </h1>
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
              required
              value={email}
              onChange={e => setEmail(e.target.value)}
              className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>
          <div>
            <PasswordInput
              id="password"
              label="Password"
              minLength={8}
              required
              value={password}
              onChange={e => setPassword(e.target.value)}
            />
            <p className="mt-1 text-xs text-gray-500">Minimum 8 characters</p>
          </div>
          {!config?.needs_setup && (
            <div>
              <label htmlFor="workspace-name" className="block text-sm font-medium text-gray-700">
                Workspace name
              </label>
              <input
                id="workspace-name"
                type="text"
                required
                value={workspaceName}
                onChange={e => setWorkspaceName(e.target.value)}
                className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>
          )}
          {config?.turnstile_site_key && (
            <Captcha
              siteKey={config.turnstile_site_key}
              onToken={setCaptchaToken}
              resetSignal={resetSignal}
            />
          )}
          <button
            type="submit"
            disabled={submitting}
            className="w-full py-2 px-4 bg-indigo-600 text-white rounded-md text-sm font-medium hover:bg-indigo-700 disabled:opacity-50"
          >
            {submitting ? 'Creating account...' : 'Create account'}
          </button>
        </form>
        <p className="mt-4 text-sm text-gray-600">
          Already have an account?{' '}
          <Link to="/login" className="text-indigo-600 hover:underline">
            Log in
          </Link>
        </p>
      </div>
    </div>
  );
}
