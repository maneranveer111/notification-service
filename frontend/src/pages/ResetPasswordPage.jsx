import { useState } from 'react';
import { useSearchParams, Link } from 'react-router-dom';
import { apiFetch } from '../lib/api';
import PasswordInput from '../components/PasswordInput';
import Button from '../components/ui/Button';
import { AlertCircle, CheckCircle2, Lock } from 'lucide-react';

export default function ResetPasswordPage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token');

  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState(null);
  const [failed, setFailed] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);

    if (password.length < 8) {
      setError('Password must be at least 8 characters.');
      return;
    }
    if (password !== confirm) {
      setError('Passwords do not match.');
      return;
    }

    setSubmitting(true);
    try {
      await apiFetch('/auth/reset-password', {
        method: 'POST',
        body: JSON.stringify({ token, new_password: password }),
      });
      setDone(true);
    } catch {
      setFailed(true);
    } finally {
      setSubmitting(false);
    }
  }

  if (done) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-[#FAFAF9] px-4 py-12">
        <div className="w-full max-w-[400px] bg-white rounded-[10px] border border-[#E7E5E4] shadow-sm p-8 text-center">
          <div className="mx-auto flex items-center justify-center w-10 h-10 rounded-[8px] bg-[#ECFDF5] text-[#047857] mb-4">
            <CheckCircle2 className="w-5 h-5" strokeWidth={1.5} />
          </div>
          <h1 className="text-xl font-bold tracking-tight text-[#1C1917] mb-2">Password updated</h1>
          <p className="text-xs text-[#78716C] mb-6">
            Your password has been changed successfully. You can now log in with your new credentials.
          </p>
          <Link to="/login">
            <Button className="w-full">Go to login</Button>
          </Link>
        </div>
      </div>
    );
  }

  if (failed) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-[#FAFAF9] px-4 py-12">
        <div className="w-full max-w-[400px] bg-white rounded-[10px] border border-[#E7E5E4] shadow-sm p-8 text-center">
          <div className="mx-auto flex items-center justify-center w-10 h-10 rounded-[8px] bg-[#FEF2F2] text-[#B91C1C] mb-4">
            <AlertCircle className="w-5 h-5" strokeWidth={1.5} />
          </div>
          <h1 className="text-xl font-bold tracking-tight text-[#1C1917] mb-2">Link expired</h1>
          <p className="text-xs text-[#78716C] mb-6">
            This password reset link is invalid or has expired.
          </p>
          <Link to="/forgot-password">
            <Button variant="secondary" className="w-full">
              Request a new link
            </Button>
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-[#FAFAF9] px-4 py-12">
      <div className="w-full max-w-[400px] bg-white rounded-[10px] border border-[#E7E5E4] shadow-sm p-8">
        <div className="flex items-center justify-center w-10 h-10 rounded-[8px] bg-[#EEF2FF] text-[#4F46E5] mb-5">
          <Lock className="w-5 h-5" strokeWidth={1.5} />
        </div>
        <h1 className="text-xl font-bold tracking-tight text-[#1C1917] mb-1">Set a new password</h1>
        <p className="text-xs text-[#78716C] mb-6">
          Choose a secure password with at least 8 characters.
        </p>

        {error && (
          <div className="mb-5 p-3 rounded-[6px] bg-[#FEF2F2] border border-[#FECACA] flex items-start gap-2.5 text-[#B91C1C] text-xs">
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" strokeWidth={1.5} />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <PasswordInput
            id="password"
            label="New password"
            minLength={8}
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <PasswordInput
            id="confirm"
            label="Confirm password"
            minLength={8}
            required
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
          />

          <Button type="submit" loading={submitting} className="w-full mt-2">
            Update password
          </Button>
        </form>

        <div className="mt-6 pt-5 border-t border-[#E7E5E4] text-center">
          <Link to="/login" className="text-xs font-medium text-[#4F46E5] hover:text-[#4338CA] transition-colors">
            Back to login
          </Link>
        </div>
      </div>
    </div>
  );
}
