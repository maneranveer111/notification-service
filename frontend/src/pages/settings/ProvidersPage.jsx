import { useState, useEffect, useCallback } from 'react';
import { apiFetch } from '../../lib/api';
import { useAuth } from '../../lib/auth';
import ConfirmDialog from '../../components/ConfirmDialog';
import ErrorBanner from '../../components/ErrorBanner';
import Loading from '../../components/Loading';
import EmptyState from '../../components/EmptyState';
import PasswordInput from '../../components/PasswordInput';

const PROVIDER_META = {
  brevo: {
    label: 'Brevo Email',
    icon: '📧',
    help: 'Create an API key in your Brevo account and verify your sender address or domain before connecting.',
  },
  smtp: {
    label: 'SMTP Email',
    icon: '📨',
    help: 'For Gmail, use an App Password (not your account password). The host must be a publicly accessible SMTP server.',
  },
  twilio: {
    label: 'Twilio SMS',
    icon: '📱',
    help: 'Trial accounts can only message verified numbers. In India, commercial SMS requires sender and template registration with your carrier and Twilio, handled in your own Twilio account.',
  },
};

const PORT_OPTIONS = [25, 465, 587, 2525];

function isValidEmail(v) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v);
}

function isValidE164(v) {
  return /^\+[1-9]\d{6,14}$/.test(v);
}

// Dark-styled PasswordInput wrapper
function DarkPasswordInput({ id, label, ...rest }) {
  const [show, setShow] = useState(false);
  return (
    <div className="space-y-1">
      {label && (
        <label htmlFor={id} className="block text-sm font-medium text-gray-300">
          {label}
        </label>
      )}
      <div className="relative">
        <input
          id={id}
          type={show ? 'text' : 'password'}
          className="block w-full rounded-lg bg-gray-800 border border-gray-700 text-white px-3 py-2 pr-10 text-sm placeholder-gray-500 focus:outline-none focus:border-blue-500"
          {...rest}
        />
        <button
          type="button"
          onClick={() => setShow((s) => !s)}
          className="absolute inset-y-0 right-0 flex items-center pr-3 text-gray-400 hover:text-gray-200"
          aria-label={show ? 'Hide' : 'Show'}
        >
          {show ? '🙈' : '👁'}
        </button>
      </div>
    </div>
  );
}

function ProviderCard({ providerKey, info, isAdmin, is503, onEdit, onTest, onDisconnect }) {
  const meta = PROVIDER_META[providerKey];
  const connected = info?.is_active;
  const fields = info?.fields || {};
  const hints = info?.hints || {};

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 space-y-3">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="text-lg">{meta.icon}</span>
          <h3 className="font-semibold text-white">{meta.label}</h3>
        </div>
        <span className={`text-xs px-2.5 py-1 rounded-full font-medium ${
          connected
            ? 'bg-green-800 text-green-200'
            : 'bg-gray-700 text-gray-400'
        }`}>
          {connected ? 'Connected' : 'Not connected'}
        </span>
      </div>

      {/* Non-secret fields */}
      {connected && (
        <div className="text-sm text-gray-400 space-y-1">
          {providerKey === 'brevo' && (
            <>
              {fields.from_email && <p>From: {fields.from_email}{fields.from_name ? ` (${fields.from_name})` : ''}</p>}
              {hints.api_key && <p>API key: ****{hints.api_key}</p>}
            </>
          )}
          {providerKey === 'smtp' && (
            <>
              {fields.host && <p>Host: {fields.host}:{fields.port ?? ''}</p>}
              {fields.from_email && <p>From: {fields.from_email}</p>}
              {fields.use_tls !== undefined && <p>TLS: {fields.use_tls ? 'Yes' : 'No'}</p>}
            </>
          )}
          {providerKey === 'twilio' && (
            <>
              {fields.from_number && <p>From: {fields.from_number}</p>}
              {hints.account_sid && <p>Account SID: ****{hints.account_sid}</p>}
            </>
          )}
        </div>
      )}

      {/* Last verified / last error */}
      {connected && (
        <div className="text-xs">
          {info.last_verified_at ? (
            <p className="text-green-400">✓ Verified {new Date(info.last_verified_at).toLocaleString()}</p>
          ) : info.last_error ? (
            <p className="text-red-400">✗ Error: {info.last_error}</p>
          ) : (
            <p className="text-gray-500">Not yet tested</p>
          )}
        </div>
      )}

      {/* Actions */}
      {isAdmin && (
        <div className="flex flex-wrap gap-2 pt-1">
          <button
            type="button"
            onClick={() => onEdit(providerKey)}
            disabled={is503}
            className="px-3 py-1.5 text-xs rounded-lg bg-blue-700 hover:bg-blue-600 disabled:opacity-50 text-white font-medium transition-colors"
          >
            {connected ? 'Edit' : 'Connect'}
          </button>
          {connected && (
            <>
              <button
                type="button"
                onClick={() => onTest(providerKey)}
                disabled={is503}
                className="px-3 py-1.5 text-xs rounded-lg bg-gray-700 hover:bg-gray-600 disabled:opacity-50 text-gray-200 font-medium transition-colors"
              >
                Test
              </button>
              <button
                type="button"
                onClick={() => onDisconnect(providerKey)}
                disabled={is503}
                className="px-3 py-1.5 text-xs rounded-lg bg-red-800 hover:bg-red-700 disabled:opacity-50 text-red-200 font-medium transition-colors"
              >
                Disconnect
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}

function EditModal({ providerKey, info, onClose, onSaved, is503 }) {
  const isEditing = info?.is_active;
  const fields = info?.fields || {};
  const secrets = info?.secrets_set || [];

  // Brevo
  const [apiKey, setApiKey] = useState('');
  const [fromEmail, setFromEmail] = useState(fields.from_email || '');
  const [fromName, setFromName] = useState(fields.from_name || '');

  // SMTP
  const [host, setHost] = useState(fields.host || '');
  const [port, setPort] = useState(String(fields.port || '587'));
  const [username, setUsername] = useState(fields.username || '');
  const [password, setPassword] = useState('');
  const [smtpFromEmail, setSmtpFromEmail] = useState(fields.from_email || '');
  const [useTls, setUseTls] = useState(fields.use_tls !== undefined ? fields.use_tls : true);

  // Twilio
  const [accountSid, setAccountSid] = useState('');
  const [authToken, setAuthToken] = useState('');
  const [fromNumber, setFromNumber] = useState(fields.from_number || '');

  const [errors, setErrors] = useState({});
  const [serverError, setServerError] = useState(null);
  const [loading, setLoading] = useState(false);

  const meta = PROVIDER_META[providerKey];
  const secretPlaceholder = 'A value is saved. Leave blank to keep it.';

  function validate() {
    const e = {};
    if (providerKey === 'brevo') {
      if (!isEditing && !apiKey) e.apiKey = 'API key is required.';
      if (!fromEmail) e.fromEmail = 'From email is required.';
      else if (!isValidEmail(fromEmail)) e.fromEmail = 'Must be a valid email.';
    }
    if (providerKey === 'smtp') {
      if (!isEditing && !host) e.host = 'Host is required.';
      if (!smtpFromEmail) e.smtpFromEmail = 'From email is required.';
      else if (!isValidEmail(smtpFromEmail)) e.smtpFromEmail = 'Must be a valid email.';
    }
    if (providerKey === 'twilio') {
      if (!isEditing && !accountSid) e.accountSid = 'Account SID is required.';
      if (!isEditing && !authToken) e.authToken = 'Auth token is required.';
      if (!fromNumber) e.fromNumber = 'From number is required.';
      else if (!isValidE164(fromNumber)) e.fromNumber = 'Must be E.164 format (e.g. +12125550100).';
    }
    return e;
  }

  async function handleSubmit(e) {
    e.preventDefault();
    const errs = validate();
    if (Object.keys(errs).length > 0) { setErrors(errs); return; }
    setErrors({});
    setServerError(null);
    setLoading(true);

    let body = {};
    if (providerKey === 'brevo') {
      if (apiKey) body.api_key = apiKey;
      body.from_email = fromEmail;
      if (fromName) body.from_name = fromName;
    } else if (providerKey === 'smtp') {
      body.host = host;
      body.port = Number(port);
      if (username) body.username = username;
      if (password) body.password = password;
      body.from_email = smtpFromEmail;
      body.use_tls = useTls;
    } else if (providerKey === 'twilio') {
      if (accountSid) body.account_sid = accountSid;
      if (authToken) body.auth_token = authToken;
      body.from_number = fromNumber;
    }

    try {
      await apiFetch(`/providers/${providerKey}`, {
        method: 'PUT',
        body: JSON.stringify(body),
      });
      onSaved();
    } catch (err) {
      if (err.status === 503) {
        setServerError('This server has no encryption key configured. Ask the operator to set ENCRYPTION_KEY.');
      } else if (err.status === 422 && Array.isArray(err.detail)) {
        const fieldErrs = {};
        err.detail.forEach((d) => {
          const key = d.loc ? d.loc[d.loc.length - 1] : 'general';
          fieldErrs[key] = d.msg;
        });
        setErrors(fieldErrs);
      } else {
        setServerError(err?.detail || err?.message || 'Failed to save provider.');
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="bg-gray-900 border border-gray-700 rounded-xl w-full max-w-md shadow-2xl overflow-y-auto max-h-[90vh]">
        <div className="p-6 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-white">
              {isEditing ? 'Edit' : 'Connect'} {meta.label}
            </h2>
            <button
              type="button"
              onClick={onClose}
              className="text-gray-400 hover:text-gray-200 text-xl leading-none"
              aria-label="Close"
            >
              ×
            </button>
          </div>

          {is503 && (
            <div className="px-4 py-3 rounded-lg bg-yellow-900/40 border border-yellow-700 text-yellow-300 text-sm">
              This server has no encryption key configured. Ask the operator to set ENCRYPTION_KEY.
            </div>
          )}

          {serverError && (
            <div className="px-4 py-3 rounded-lg bg-red-900/30 border border-red-700 text-red-300 text-sm">
              {serverError}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            {providerKey === 'brevo' && (
              <>
                <div>
                  <DarkPasswordInput
                    id="brevo-api-key"
                    label={`API Key${isEditing ? '' : ' *'}`}
                    value={apiKey}
                    onChange={(e) => setApiKey(e.target.value)}
                    placeholder={isEditing && secrets.includes('api_key') ? secretPlaceholder : 'Brevo API key'}
                    autoComplete="off"
                  />
                  {errors.apiKey && <p className="text-xs text-red-400 mt-1">{errors.apiKey}</p>}
                </div>
                <div>
                  <label htmlFor="brevo-from-email" className="block text-sm font-medium text-gray-300 mb-1">
                    From Email *
                  </label>
                  <input
                    id="brevo-from-email"
                    type="email"
                    value={fromEmail}
                    onChange={(e) => setFromEmail(e.target.value)}
                    className="w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 text-sm"
                    placeholder="sender@example.com"
                  />
                  {errors.fromEmail && <p className="text-xs text-red-400 mt-1">{errors.fromEmail}</p>}
                </div>
                <div>
                  <label htmlFor="brevo-from-name" className="block text-sm font-medium text-gray-300 mb-1">
                    From Name (optional)
                  </label>
                  <input
                    id="brevo-from-name"
                    type="text"
                    value={fromName}
                    onChange={(e) => setFromName(e.target.value)}
                    className="w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 text-sm"
                    placeholder="Sender Name"
                  />
                </div>
              </>
            )}

            {providerKey === 'smtp' && (
              <>
                <div>
                  <label htmlFor="smtp-host" className="block text-sm font-medium text-gray-300 mb-1">
                    Host *
                  </label>
                  <input
                    id="smtp-host"
                    type="text"
                    value={host}
                    onChange={(e) => setHost(e.target.value)}
                    className="w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 text-sm"
                    placeholder="smtp.example.com"
                  />
                  {errors.host && <p className="text-xs text-red-400 mt-1">{errors.host}</p>}
                </div>
                <div>
                  <label htmlFor="smtp-port" className="block text-sm font-medium text-gray-300 mb-1">
                    Port *
                  </label>
                  <select
                    id="smtp-port"
                    value={port}
                    onChange={(e) => setPort(e.target.value)}
                    className="w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 text-white focus:outline-none focus:border-blue-500 text-sm"
                  >
                    {PORT_OPTIONS.map((p) => (
                      <option key={p} value={p}>{p}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label htmlFor="smtp-username" className="block text-sm font-medium text-gray-300 mb-1">
                    Username
                  </label>
                  <input
                    id="smtp-username"
                    type="text"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    className="w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 text-sm"
                    autoComplete="username"
                  />
                </div>
                <div>
                  <DarkPasswordInput
                    id="smtp-password"
                    label="Password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder={isEditing && secrets.includes('password') ? secretPlaceholder : ''}
                    autoComplete="new-password"
                  />
                </div>
                <div>
                  <label htmlFor="smtp-from-email" className="block text-sm font-medium text-gray-300 mb-1">
                    From Email *
                  </label>
                  <input
                    id="smtp-from-email"
                    type="email"
                    value={smtpFromEmail}
                    onChange={(e) => setSmtpFromEmail(e.target.value)}
                    className="w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 text-sm"
                    placeholder="sender@example.com"
                  />
                  {errors.smtpFromEmail && <p className="text-xs text-red-400 mt-1">{errors.smtpFromEmail}</p>}
                </div>
                <div className="flex items-center gap-2">
                  <input
                    id="smtp-tls"
                    type="checkbox"
                    checked={useTls}
                    onChange={(e) => setUseTls(e.target.checked)}
                    className="rounded border-gray-600 bg-gray-800 text-blue-500"
                  />
                  <label htmlFor="smtp-tls" className="text-sm text-gray-300">Use TLS</label>
                </div>
              </>
            )}

            {providerKey === 'twilio' && (
              <>
                <div>
                  <label htmlFor="twilio-sid" className="block text-sm font-medium text-gray-300 mb-1">
                    Account SID{!isEditing ? ' *' : ''}
                  </label>
                  <input
                    id="twilio-sid"
                    type="text"
                    value={accountSid}
                    onChange={(e) => setAccountSid(e.target.value)}
                    className="w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 text-sm"
                    placeholder={isEditing && secrets.includes('account_sid') ? secretPlaceholder : 'ACxxxxxxxx...'}
                    autoComplete="off"
                  />
                  {errors.accountSid && <p className="text-xs text-red-400 mt-1">{errors.accountSid}</p>}
                </div>
                <div>
                  <DarkPasswordInput
                    id="twilio-auth-token"
                    label={`Auth Token${!isEditing ? ' *' : ''}`}
                    value={authToken}
                    onChange={(e) => setAuthToken(e.target.value)}
                    placeholder={isEditing && secrets.includes('auth_token') ? secretPlaceholder : ''}
                    autoComplete="off"
                  />
                  {errors.authToken && <p className="text-xs text-red-400 mt-1">{errors.authToken}</p>}
                </div>
                <div>
                  <label htmlFor="twilio-from-number" className="block text-sm font-medium text-gray-300 mb-1">
                    From Number * (E.164 format)
                  </label>
                  <input
                    id="twilio-from-number"
                    type="tel"
                    value={fromNumber}
                    onChange={(e) => setFromNumber(e.target.value)}
                    className="w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 text-sm"
                    placeholder="+12125550100"
                  />
                  {errors.fromNumber && <p className="text-xs text-red-400 mt-1">{errors.fromNumber}</p>}
                </div>
              </>
            )}

            {/* Help text */}
            <p className="text-xs text-gray-500 border-t border-gray-800 pt-3">{meta.help}</p>

            <div className="flex gap-3 pt-1">
              <button
                type="button"
                onClick={onClose}
                disabled={loading}
                className="flex-1 px-4 py-2 rounded-lg bg-gray-700 hover:bg-gray-600 disabled:opacity-50 text-gray-300 text-sm font-medium"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={loading || is503}
                className="flex-1 px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm font-medium"
              >
                {loading ? 'Saving…' : 'Save'}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}

function TestModal({ providerKey, onClose, onTested }) {
  const meta = PROVIDER_META[providerKey];
  const isEmail = providerKey === 'brevo' || providerKey === 'smtp';
  const [to, setTo] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);

  async function handleTest(e) {
    e.preventDefault();
    setLoading(true);
    setResult(null);
    try {
      const res = await apiFetch(`/providers/${providerKey}/test`, {
        method: 'POST',
        body: JSON.stringify({ to }),
      });
      setResult({ ok: res.ok, error: res.error });
    } catch (err) {
      setResult({ ok: false, error: err?.detail || err?.message || 'Test failed.' });
    } finally {
      setLoading(false);
    }
  }

  function handleClose() {
    onTested();
    onClose();
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="bg-gray-900 border border-gray-700 rounded-xl w-full max-w-sm shadow-2xl p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-white">Test {meta.label}</h2>
          <button type="button" onClick={handleClose} className="text-gray-400 hover:text-gray-200 text-xl" aria-label="Close">×</button>
        </div>

        {result ? (
          <div className={`px-4 py-3 rounded-lg border text-sm ${
            result.ok
              ? 'bg-green-900/30 border-green-700 text-green-300'
              : 'bg-red-900/30 border-red-700 text-red-300'
          }`}>
            {result.ok ? '✓ Test sent successfully.' : `✗ ${result.error || 'Test failed.'}`}
          </div>
        ) : (
          <form onSubmit={handleTest} className="space-y-4">
            <div>
              <label htmlFor="test-to" className="block text-sm font-medium text-gray-300 mb-1">
                {isEmail ? 'Recipient email *' : 'Recipient phone (E.164) *'}
              </label>
              <input
                id="test-to"
                type={isEmail ? 'email' : 'tel'}
                required
                value={to}
                onChange={(e) => setTo(e.target.value)}
                className="w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 text-sm"
                placeholder={isEmail ? 'test@example.com' : '+12125550100'}
                autoFocus
              />
            </div>
            <div className="flex gap-3">
              <button type="button" onClick={handleClose} className="flex-1 px-4 py-2 rounded-lg bg-gray-700 hover:bg-gray-600 text-gray-300 text-sm font-medium">
                Cancel
              </button>
              <button type="submit" disabled={loading || !to} className="flex-1 px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm font-medium">
                {loading ? 'Sending…' : 'Send test'}
              </button>
            </div>
          </form>
        )}

        {result && (
          <button type="button" onClick={handleClose} className="w-full px-4 py-2 rounded-lg bg-gray-700 hover:bg-gray-600 text-gray-300 text-sm font-medium">
            Close
          </button>
        )}
      </div>
    </div>
  );
}

function WebhooksPanel({ is503 }) {
  const [webhooks, setWebhooks] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [confirmRegen, setConfirmRegen] = useState(false);
  const [regenLoading, setRegenLoading] = useState(false);
  const [copiedField, setCopiedField] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const d = await apiFetch('/providers/webhooks');
      setWebhooks(d);
      setError(null);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function handleRegen() {
    setRegenLoading(true);
    try {
      const d = await apiFetch('/providers/webhooks/regenerate', { method: 'POST' });
      setWebhooks(d);
      setConfirmRegen(false);
    } catch (e) {
      setError(e);
    } finally {
      setRegenLoading(false);
    }
  }

  function copyUrl(field, val) {
    navigator.clipboard.writeText(val).then(() => {
      setCopiedField(field);
      setTimeout(() => setCopiedField(null), 2000);
    });
  }

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 space-y-4">
      <h3 className="font-semibold text-white">Delivery Webhooks</h3>

      {loading ? (
        <Loading text="Loading webhooks…" />
      ) : error ? (
        <ErrorBanner error={error} onRetry={load} />
      ) : webhooks ? (
        <div className="space-y-4">
          {/* Brevo */}
          <div className="space-y-1.5">
            <p className="text-sm font-medium text-gray-300">Brevo Webhook URL</p>
            <div className="flex items-center gap-2">
              <code className="flex-1 text-xs text-green-300 bg-gray-800 px-3 py-2 rounded-lg truncate">
                {webhooks.brevo_url}
              </code>
              <button
                type="button"
                onClick={() => copyUrl('brevo', webhooks.brevo_url)}
                className="shrink-0 px-3 py-1.5 text-xs rounded-lg bg-gray-700 hover:bg-gray-600 text-gray-300"
              >
                {copiedField === 'brevo' ? 'Copied!' : 'Copy'}
              </button>
            </div>
            <p className="text-xs text-gray-500">
              Paste this URL in Brevo → Transactional → Settings → Webhooks. Enable events: delivered, hard bounce, soft bounce, blocked, invalid email, spam, error.
            </p>
          </div>

          {/* Twilio */}
          <div className="space-y-1.5">
            <p className="text-sm font-medium text-gray-300">Twilio Webhook URL</p>
            <div className="flex items-center gap-2">
              <code className="flex-1 text-xs text-green-300 bg-gray-800 px-3 py-2 rounded-lg truncate">
                {webhooks.twilio_url}
              </code>
              <button
                type="button"
                onClick={() => copyUrl('twilio', webhooks.twilio_url)}
                className="shrink-0 px-3 py-1.5 text-xs rounded-lg bg-gray-700 hover:bg-gray-600 text-gray-300"
              >
                {copiedField === 'twilio' ? 'Copied!' : 'Copy'}
              </button>
            </div>
            <p className="text-xs text-gray-500">
              The Twilio status callback URL is set automatically when a message is sent — nothing to paste.
            </p>
          </div>

          {/* Regenerate */}
          <div className="pt-2 border-t border-gray-800">
            <button
              type="button"
              onClick={() => setConfirmRegen(true)}
              disabled={is503}
              className="px-3 py-1.5 text-xs rounded-lg bg-amber-700 hover:bg-amber-600 disabled:opacity-50 text-white font-medium transition-colors"
            >
              Regenerate URLs
            </button>
            <p className="text-xs text-gray-500 mt-1">
              Regenerating creates new URLs immediately. Old URLs stop working instantly.
            </p>
          </div>
        </div>
      ) : null}

      <ConfirmDialog
        open={confirmRegen}
        title="Regenerate webhook URLs?"
        message="The old URLs will stop working immediately. You will need to update them in Brevo and any other integrations."
        confirmLabel="Regenerate"
        loading={regenLoading}
        onConfirm={handleRegen}
        onCancel={() => setConfirmRegen(false)}
      />
    </div>
  );
}

export default function ProvidersPage() {
  const { isAdmin } = useAuth();
  const [providers, setProviders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [is503, setIs503] = useState(false);

  const [editModal, setEditModal] = useState({ open: false, provider: null });
  const [testModal, setTestModal] = useState({ open: false, provider: null });
  const [disconnectConfirm, setDisconnectConfirm] = useState({ open: false, provider: null });
  const [disconnectLoading, setDisconnectLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setIs503(false);
    try {
      const data = await apiFetch('/providers');
      setProviders(data);
      setError(null);
    } catch (e) {
      if (e.status === 503) {
        setIs503(true);
        setError(null);
      } else {
        setError(e);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const providerMap = {};
  providers.forEach((p) => { providerMap[p.provider] = p; });

  async function handleDisconnect() {
    const key = disconnectConfirm.provider;
    setDisconnectLoading(true);
    try {
      await apiFetch(`/providers/${key}`, { method: 'DELETE' });
      setDisconnectConfirm({ open: false, provider: null });
      load();
    } catch (e) {
      setError(e);
    } finally {
      setDisconnectLoading(false);
    }
  }

  const connectedCount = providers.filter((p) => p.is_active).length;

  return (
    <div className="space-y-6">
      {is503 && (
        <div className="px-4 py-3 rounded-lg bg-yellow-900/40 border border-yellow-700 text-yellow-300 text-sm">
          ⚠ This server has no encryption key configured. Ask the operator to set ENCRYPTION_KEY. Provider forms are disabled.
        </div>
      )}

      {error && <ErrorBanner error={error} onRetry={load} />}

      {loading ? (
        <Loading text="Loading providers…" />
      ) : (
        <>
          {connectedCount === 0 && !error && !is503 && (
            <div className="px-4 py-3 rounded-lg bg-gray-800 border border-gray-700 text-gray-400 text-sm">
              No provider connected yet. Connect one to start sending.
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {Object.keys(PROVIDER_META).map((key) => (
              <ProviderCard
                key={key}
                providerKey={key}
                info={providerMap[key]}
                isAdmin={isAdmin}
                is503={is503}
                onEdit={(k) => setEditModal({ open: true, provider: k })}
                onTest={(k) => setTestModal({ open: true, provider: k })}
                onDisconnect={(k) => setDisconnectConfirm({ open: true, provider: k })}
              />
            ))}
          </div>

          <WebhooksPanel is503={is503} />
        </>
      )}

      {editModal.open && (
        <EditModal
          providerKey={editModal.provider}
          info={providerMap[editModal.provider]}
          is503={is503}
          onClose={() => setEditModal({ open: false, provider: null })}
          onSaved={() => { setEditModal({ open: false, provider: null }); load(); }}
        />
      )}

      {testModal.open && (
        <TestModal
          providerKey={testModal.provider}
          onClose={() => setTestModal({ open: false, provider: null })}
          onTested={load}
        />
      )}

      <ConfirmDialog
        open={disconnectConfirm.open}
        title={`Disconnect ${disconnectConfirm.provider ? PROVIDER_META[disconnectConfirm.provider]?.label : ''}?`}
        message="This will remove the provider configuration. Sending will stop until you reconnect."
        confirmLabel="Disconnect"
        loading={disconnectLoading}
        onConfirm={handleDisconnect}
        onCancel={() => setDisconnectConfirm({ open: false, provider: null })}
      />
    </div>
  );
}
