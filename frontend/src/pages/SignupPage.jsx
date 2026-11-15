import { useEffect, useRef, useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { getPublicConfig, apiFetch, ApiError } from '../lib/api';
import { useAuth } from '../lib/auth';
import { describeError } from '../lib/errors';
import PasswordInput from '../components/PasswordInput';
import Captcha from '../components/Captcha';
import Button from '../components/ui/Button';
import Input from '../components/ui/Input';
import { AlertCircle, Mail } from 'lucide-react';

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
  const [isAccountExists, setIsAccountExists] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [resendCooldown, setResendCooldown] = useState(0);
  const [resetSignal, setResetSignal] = useState(0);

  const cooldownRef = useRef(null);

  useEffect(() => {
    getPublicConfig(true)
      .then((cfg) => setConfig(cfg))
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
    setIsAccountExists(false);
    setSubmitting(true);
    try {
      const body = {
        email,
        password,
        workspace_name: config?.needs_setup ? undefined : workspaceName || undefined,
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
        setIsAccountExists(true);
      } else {
        const desc = describeError(err);
        setError(desc.title + ': ' + desc.message);
        setIsAccountExists(false);
      }
      setResetSignal((s) => s + 1);
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
    setResetSignal((s) => s + 1);
    setCaptchaToken(null);
  }

  if (configLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#FAFAF9]">
        <div className="flex items-center gap-2 text-xs text-[#78716C]">
          <div className="w-4 h-4 border-2 border-[#4F46E5] border-t-transparent rounded-full animate-spin" />
          <span>Loading...</span>
        </div>
      </div>
    );
  }

  if (config?.signup_mode === 'closed' && !config?.needs_setup) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-[#FAFAF9] px-4 py-12">
        <div className="w-full max-w-[400px] bg-white rounded-[10px] border border-[#E7E5E4] shadow-sm p-8 text-center">
          <div className="mx-auto flex items-center justify-center w-10 h-10 rounded-[8px] bg-[#F5F5F4] text-[#78716C] mb-4">
            <Mail className="w-5 h-5" strokeWidth={1.5} />
          </div>
          <h1 className="text-lg font-bold tracking-tight text-[#1C1917] mb-2">Sign-ups Closed</h1>
          <p className="text-xs text-[#78716C] mb-6">
            Sign-ups are currently closed for new users.
          </p>
          <Link to="/login" className="text-xs font-medium text-[#4F46E5] hover:text-[#4338CA] transition-colors">
            Back to login
          </Link>
        </div>
      </div>
    );
  }

  if (config?.signup_mode === 'invite_only' && !config?.needs_setup) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-[#FAFAF9] px-4 py-12">
        <div className="w-full max-w-[400px] bg-white rounded-[10px] border border-[#E7E5E4] shadow-sm p-8 text-center">
          <div className="mx-auto flex items-center justify-center w-10 h-10 rounded-[8px] bg-[#F5F5F4] text-[#78716C] mb-4">
            <Mail className="w-5 h-5" strokeWidth={1.5} />
          </div>
          <h1 className="text-lg font-bold tracking-tight text-[#1C1917] mb-2">Invitation Required</h1>
          <p className="text-xs text-[#78716C] mb-6">
            Accounts are created by invitation only. Check your email for an invite link from your team.
          </p>
          <Link to="/login" className="text-xs font-medium text-[#4F46E5] hover:text-[#4338CA] transition-colors">
            Back to login
          </Link>
        </div>
      </div>
    );
  }

  if (submitted) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-[#FAFAF9] px-4 py-12">
        <div className="w-full max-w-[400px] bg-white rounded-[10px] border border-[#E7E5E4] shadow-sm p-8">
          <div className="flex items-center justify-center w-10 h-10 rounded-[8px] bg-[#ECFDF5] text-[#047857] mb-5">
            <Mail className="w-5 h-5" strokeWidth={1.5} />
          </div>
          <h1 className="text-xl font-bold tracking-tight text-[#1C1917] mb-2">Check your inbox</h1>
          <p className="text-xs text-[#78716C] mb-6 leading-relaxed">
            We sent a verification email to <strong className="text-[#1C1917] font-medium">{email}</strong>. Follow the link inside to activate your workspace.
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
          <Button
            type="button"
            variant="secondary"
            onClick={handleResend}
            disabled={resendCooldown > 0}
            className="w-full"
          >
            {resendCooldown > 0 ? `Resend in ${resendCooldown}s` : 'Resend verification email'}
          </Button>
          <p className="mt-4 text-[11px] text-[#A8A29E] text-center">Check your spam folder if it doesn&apos;t arrive in 2 minutes.</p>
          <div className="mt-6 pt-5 border-t border-[#E7E5E4] text-center">
            <Link to="/login" className="text-xs font-medium text-[#4F46E5] hover:text-[#4338CA] transition-colors">
              Already have an account? Log in
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-[#FAFAF9] px-4 py-12">
      <div className="w-full max-w-[400px] bg-white rounded-[10px] border border-[#E7E5E4] shadow-sm p-8">
        <div className="flex items-center justify-center w-10 h-10 rounded-[8px] bg-[#4F46E5] text-white font-bold text-lg mb-6 shadow-sm">
          N
        </div>
        <h1 className="text-xl font-bold tracking-tight text-[#1C1917] mb-1">
          {config?.needs_setup ? 'Set up your workspace' : 'Create an account'}
        </h1>
        <p className="text-xs text-[#78716C] mb-6">
          {config?.needs_setup ? 'Create the initial superadmin account' : 'Start dispatching notifications in minutes'}
        </p>

        {error && (
          <div className="mb-5 p-3 rounded-[6px] bg-[#FEF2F2] border border-[#FECACA] flex items-start gap-2.5 text-[#B91C1C] text-xs">
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" strokeWidth={1.5} />
            <div className="flex-1">
              <span>{error}</span>
              {isAccountExists && (
                <div className="mt-2">
                  <Link
                    to="/login"
                    className="inline-flex items-center font-semibold text-[#B91C1C] underline hover:no-underline"
                  >
                    Sign in to your account &rarr;
                  </Link>
                </div>
              )}
            </div>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <Input
            label="Email"
            id="email"
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="name@company.com"
          />

          <div>
            <PasswordInput
              id="password"
              label="Password"
              minLength={8}
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            <p className="mt-1 text-[11px] text-[#A8A29E]">Minimum 8 characters</p>
          </div>

          {!config?.needs_setup && (
            <Input
              label="Workspace name"
              id="workspace-name"
              type="text"
              required
              value={workspaceName}
              onChange={(e) => setWorkspaceName(e.target.value)}
              placeholder="Acme Corp"
            />
          )}

          {config?.turnstile_site_key && (
            <Captcha
              siteKey={config.turnstile_site_key}
              onToken={setCaptchaToken}
              resetSignal={resetSignal}
            />
          )}

          <Button type="submit" loading={submitting} className="w-full mt-2">
            {submitting ? 'Creating account...' : 'Create account'}
          </Button>
        </form>

        <div className="mt-6 pt-5 border-t border-[#E7E5E4] text-center text-xs text-[#78716C]">
          Already have an account?{' '}
          <Link to="/login" className="text-[#4F46E5] hover:text-[#4338CA] font-medium transition-colors">
            Log in
          </Link>
        </div>
      </div>
    </div>
  );
}
