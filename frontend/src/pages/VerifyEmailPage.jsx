import { useEffect, useRef, useState } from 'react';
import { useNavigate, useSearchParams, Link } from 'react-router-dom';
import { apiFetch, getPublicConfig } from '../lib/api';
import { useAuth } from '../lib/auth';
import { EXAMPLE_EMAIL } from '../lib/examples';
import Captcha from '../components/Captcha';
import Button from '../components/ui/Button';
import Input from '../components/ui/Input';
import { AlertCircle } from 'lucide-react';

export default function VerifyEmailPage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token');
  const { loginWithResponse } = useAuth();
  const navigate = useNavigate();
  const calledRef = useRef(false);
  const [status, setStatus] = useState('loading'); // 'loading'|'success'|'error'
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
    if (!token) {
      setStatus('error');
      return;
    }
    apiFetch('/auth/verify-email', { method: 'POST', body: JSON.stringify({ token }) })
      .then((body) => {
        loginWithResponse(body);
        navigate('/');
      })
      .catch(() => setStatus('error'));
  }, [token, loginWithResponse, navigate]);

  if (status === 'loading') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#FAFAF9]">
        <div className="flex items-center gap-2 text-xs text-[#78716C]">
          <div className="w-4 h-4 border-2 border-[#4F46E5] border-t-transparent rounded-full animate-spin" />
          <span>Verifying email...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-[#FAFAF9] px-4 py-12">
      <div className="w-full max-w-[400px] bg-white rounded-[10px] border border-[#E7E5E4] shadow-sm p-8">
        <div className="flex items-center justify-center w-10 h-10 rounded-[8px] bg-[#FEF2F2] text-[#B91C1C] mb-5">
          <AlertCircle className="w-5 h-5" strokeWidth={1.5} />
        </div>
        <h1 className="text-xl font-bold tracking-tight text-[#1C1917] mb-1">Verification failed</h1>
        <p className="text-xs text-[#78716C] mb-6">
          This verification link is invalid or has expired. You can request a new one below.
        </p>

        {!resendDone ? (
          <div className="space-y-4">
            <Input
              label="Email address"
              type="email"
              value={resendEmail}
              onChange={(e) => setResendEmail(e.target.value)}
              placeholder={EXAMPLE_EMAIL}
            />
            {config?.turnstile_site_key && (
              <Captcha siteKey={config.turnstile_site_key} onToken={setCaptchaToken} resetSignal={null} />
            )}
            <Button
              onClick={async () => {
                setResendLoading(true);
                try {
                  await apiFetch('/auth/resend-verification', {
                    method: 'POST',
                    body: JSON.stringify({ email: resendEmail, captcha_token: captchaToken || undefined }),
                  });
                  setResendDone(true);
                } catch {
                  // silent
                }
                setResendLoading(false);
              }}
              disabled={resendLoading || !resendEmail}
              loading={resendLoading}
              className="w-full mt-2"
            >
              Resend verification email
            </Button>
          </div>
        ) : (
          <div className="p-3 rounded-[6px] bg-[#ECFDF5] border border-[#A7F3D0] text-[#047857] text-xs leading-relaxed">
            If that account exists, we sent a new verification email. Check your inbox and spam folder.
          </div>
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
