import { useEffect, useRef, useState } from 'react';
import { useNavigate, useSearchParams, Link } from 'react-router-dom';
import { useAuth } from '../lib/auth';
import { getPublicConfig, apiFetch, ApiError, absoluteApiBase } from '../lib/api';
import { canShowSignupLink, signupMessage } from '../lib/signupRules';
import { describeError } from '../lib/errors';
import PasswordInput from '../components/PasswordInput';
import Captcha from '../components/Captcha';
import Button from '../components/ui/Button';
import Input from '../components/ui/Input';
import { AlertCircle } from 'lucide-react';

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
    getPublicConfig(true).then(setConfig);
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
      setResendCooldown((prev) => {
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
      setResetSignal((s) => s + 1);
      setCaptchaToken(null);
    }
  }

  if (authLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#FAFAF9]">
        <div className="flex items-center gap-2 text-xs text-[#78716C]">
          <div className="w-4 h-4 border-2 border-[#4F46E5] border-t-transparent rounded-full animate-spin" />
          <span>Loading...</span>
        </div>
      </div>
    );
  }

  if (resendMode) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-[#FAFAF9] px-4 py-12">
        <div className="w-full max-w-[400px] bg-white rounded-[10px] border border-[#E7E5E4] shadow-sm p-8">
          <div className="flex items-center justify-center w-10 h-10 rounded-[8px] bg-[#4F46E5] text-white font-bold text-lg mb-6 shadow-sm">
            N
          </div>
          <h1 className="text-xl font-bold tracking-tight text-[#1C1917] mb-1.5">Verify your email</h1>
          <p className="text-xs text-[#78716C] mb-6 leading-relaxed">
            Your email address has not been verified. Enter your email below to receive a new verification link.
          </p>

          {resendDone ? (
            <div className="space-y-4">
              <div className="p-3 rounded-[6px] bg-[#ECFDF5] border border-[#A7F3D0] text-[#047857] text-xs">
                If that account exists, we sent a verification email.
              </div>
              {resendCooldown > 0 && (
                <p className="text-xs text-[#78716C]">
                  You can request another in {resendCooldown}s.
                </p>
              )}
            </div>
          ) : (
            <form onSubmit={handleResend} className="space-y-4">
              <Input
                label="Email address"
                id="resend-email"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="name@company.com"
              />
              {config?.turnstile_site_key && (
                <Captcha
                  siteKey={config.turnstile_site_key}
                  onToken={setCaptchaToken}
                  resetSignal={resetSignal}
                />
              )}
              <Button type="submit" loading={resendLoading} className="w-full">
                Send verification email
              </Button>
            </form>
          )}

          <div className="mt-6 pt-5 border-t border-[#E7E5E4] text-center">
            <button
              type="button"
              onClick={() => setResendMode(false)}
              className="text-xs font-medium text-[#4F46E5] hover:text-[#4338CA] transition-colors"
            >
              Back to login
            </button>
          </div>
        </div>
        {searchParams.get('debug') === '1' && (
          <div className="mt-4 text-center text-[11px] text-[#A8A29E]">
            server: {config?.environment || 'unknown'} · v{config?.version || 'dev'} · API {absoluteApiBase()}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-[#FAFAF9] px-4 py-12">
      <div className="w-full max-w-[400px] bg-white rounded-[10px] border border-[#E7E5E4] shadow-sm p-8">
        <div className="flex items-center justify-center w-10 h-10 rounded-[8px] bg-[#4F46E5] text-white font-bold text-lg mb-6 shadow-sm">
          N
        </div>
        <h1 className="text-xl font-bold tracking-tight text-[#1C1917] mb-1">Sign in to Notify</h1>
        <p className="text-xs text-[#78716C] mb-6">Welcome back. Enter your credentials to continue.</p>

        {error && (
          <div className="mb-5 p-3 rounded-[6px] bg-[#FEF2F2] border border-[#FECACA] flex items-start gap-2.5 text-[#B91C1C] text-xs">
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" strokeWidth={1.5} />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <Input
            label="Email"
            id="email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="name@company.com"
          />

          <div>
            <PasswordInput
              id="password"
              label="Password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            <div className="flex justify-end mt-1.5">
              <Link
                to="/forgot-password"
                className="text-[11px] text-[#78716C] hover:text-[#1C1917] transition-colors"
              >
                Forgot password?
              </Link>
            </div>
          </div>

          <Button type="submit" loading={loading} className="w-full mt-2">
            Sign in
          </Button>
        </form>

        <div className="mt-6 pt-5 border-t border-[#E7E5E4] text-center text-xs text-[#78716C]">
          {canShowSignupLink(config) ? (
            <>
              Don&apos;t have an account?{' '}
              <Link to="/signup" className="text-[#4F46E5] hover:text-[#4338CA] font-medium transition-colors">
                Create an account
              </Link>
            </>
          ) : (
            signupMessage(config) || 'Accounts are created by invitation.'
          )}
        </div>
      </div>
      {searchParams.get('debug') === '1' && (
        <div className="mt-4 text-center text-[11px] text-[#A8A29E]">
          server: {config?.environment || 'unknown'} · v{config?.version || 'dev'} · API {absoluteApiBase()}
        </div>
      )}
    </div>
  );
}
