import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { getPublicConfig, apiFetch } from '../lib/api';
import { describeError } from '../lib/errors';
import Captcha from '../components/Captcha';

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
      // Show error only for unexpected failures; network errors, etc.
      const desc = describeError(err);
      setError(desc.title + ': ' + desc.message);
    } finally {
      // Always show the "we sent a link" message regardless of response
      setDone(true);
      setSubmitting(false);
      setResetSignal(s => s + 1);
      setCaptchaToken(null);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
      <div className="w-full max-w-md bg-white rounded-xl shadow-md p-8">
        <h1 className="text-xl font-bold text-gray-900 mb-6">Reset your password</h1>
        {error && !done && (
          <div className="mb-4 px-4 py-3 rounded-lg bg-red-50 border border-red-200 text-red-700 text-sm">
            {error}
          </div>
        )}
        {done ? (
          <p className="text-gray-700 text-sm">
            If an account exists for that email, we sent a reset link.
          </p>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label htmlFor="email" className="block text-sm font-medium text-gray-700">
                Email address
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
              {submitting ? 'Sending...' : 'Send reset link'}
            </button>
          </form>
        )}
        <Link to="/login" className="mt-4 block text-sm text-indigo-600 hover:underline">
          Back to login
        </Link>
      </div>
    </div>
  );
}
