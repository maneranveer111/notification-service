import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { getPublicConfig, apiFetch } from '../lib/api';
import { describeError } from '../lib/errors';
import { EXAMPLE_EMAIL } from '../lib/examples';
import Captcha from '../components/Captcha';
import Button from '../components/ui/Button';
import Input from '../components/ui/Input';
import { AlertCircle, KeyRound } from 'lucide-react';

export default function ForgotPasswordPage() {
  const [config, setConfig] = useState(null);
  const [email, setEmail] = useState('');
  const [captchaToken, setCaptchaToken] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState(null);
  const [resetSignal, setResetSignal] = useState(0);

  useEffect(() => {
    getPublicConfig().then(setConfig);
  }, []);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await apiFetch('/auth/forgot-password', {
        method: 'POST',
        body: JSON.stringify({ email, captcha_token: captchaToken || undefined }),
      });
    } catch (err) {
      const desc = describeError(err);
      setError(desc.title + ': ' + desc.message);
    } finally {
      setDone(true);
      setSubmitting(false);
      setResetSignal((s) => s + 1);
      setCaptchaToken(null);
    }
  }

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-[#FAFAF9] px-4 py-12">
      <div className="w-full max-w-[400px] bg-white rounded-[10px] border border-[#E7E5E4] shadow-sm p-8">
        <div className="flex items-center justify-center w-10 h-10 rounded-[8px] bg-[#EEF2FF] text-[#4F46E5] mb-5">
          <KeyRound className="w-5 h-5" strokeWidth={1.5} />
        </div>
        <h1 className="text-xl font-bold tracking-tight text-[#1C1917] mb-1">Reset your password</h1>
        <p className="text-xs text-[#78716C] mb-6">
          Enter your account email to receive a password recovery link.
        </p>

        {error && !done && (
          <div className="mb-5 p-3 rounded-[6px] bg-[#FEF2F2] border border-[#FECACA] flex items-start gap-2.5 text-[#B91C1C] text-xs">
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" strokeWidth={1.5} />
            <span>{error}</span>
          </div>
        )}

        {done ? (
          <div className="space-y-4">
            <div className="p-3 rounded-[6px] bg-[#ECFDF5] border border-[#A7F3D0] text-[#047857] text-xs leading-relaxed">
              If an account exists for that email, we sent a password reset link. Please check your inbox and spam folder.
            </div>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            <Input
              label="Email address"
              id="email"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder={EXAMPLE_EMAIL}
            />
            {config?.turnstile_site_key && (
              <Captcha
                siteKey={config.turnstile_site_key}
                onToken={setCaptchaToken}
                resetSignal={resetSignal}
              />
            )}
            <Button type="submit" loading={submitting} className="w-full mt-2">
              Send reset link
            </Button>
          </form>
        )}

        <div className="mt-6 pt-5 border-t border-[#E7E5E4] text-center">
          <Link to="/login" className="text-xs font-medium text-[#4F46E5] hover:text-[#4338CA] transition-colors">
            Back to login
          </Link>
        </div>
      </div>
    </div>
  );
}
