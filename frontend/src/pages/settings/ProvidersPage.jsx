import { useState, useEffect, useCallback } from 'react';
import {
  Mail,
  Server,
  MessageSquare,
  Copy,
  Check,
  RefreshCw,
  Info,
  CheckCircle2,
  AlertCircle,
  X,
  Send,
  Plug,
} from 'lucide-react';
import { apiFetch, getEmailPreference, setEmailPreference } from '../../lib/api';
import { useAuth } from '../../lib/auth';
import ConfirmDialog from '../../components/ConfirmDialog';
import ErrorBanner from '../../components/ErrorBanner';
import Loading from '../../components/Loading';
import PasswordInput from '../../components/PasswordInput';
import Button from '../../components/ui/Button';
import Card from '../../components/ui/Card';
import Badge from '../../components/ui/Badge';
import Input from '../../components/ui/Input';
import Select from '../../components/ui/Select';
import Switch from '../../components/ui/Switch';
import { EXAMPLE_PHONE, EXAMPLE_FROM_PHONE } from '../../lib/examples';

const PROVIDER_META = {
  brevo: {
    label: 'Brevo Email',
    icon: Mail,
    desc: 'Email delivery via Brevo v3 REST API',
    help: 'Create an API key in your Brevo account and verify your sender address or domain before connecting.',
  },
  smtp: {
    label: 'SMTP Email',
    icon: Server,
    desc: 'Direct standard SMTP / STARTTLS socket',
    help: 'For Gmail, use an App Password (not your account password). The host must be a publicly accessible SMTP server.',
  },
  twilio: {
    label: 'Twilio SMS',
    icon: MessageSquare,
    desc: 'Programmable Messaging & Shortcodes',
    help: 'Trial accounts can only message verified numbers. In India, commercial SMS requires sender and template registration.',
  },
};

const PORT_OPTIONS = [25, 465, 587, 2525];

function isValidEmail(v) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v);
}

function isValidE164(v) {
  return /^\+[1-9]\d{6,14}$/.test(v);
}

function ProviderCard({
  providerKey,
  info,
  isAdmin,
  is503,
  isDefault,
  onEdit,
  onTest,
  onDisconnect,
}) {
  const meta = PROVIDER_META[providerKey];
  const Icon = meta.icon;
  const connected = info?.is_active;
  const fields = info?.fields || {};
  const hints = info?.hints || {};

  return (
    <div className="bg-white border border-[#E7E5E4] rounded-[8px] p-5 flex flex-col justify-between shadow-xs">
      <div className="space-y-3">
        {/* Header */}
        <div className="flex items-center justify-between gap-2">
          <div className="w-8 h-8 rounded-[6px] bg-[#F5F5F4] border border-[#E7E5E4] flex items-center justify-center text-[#1C1917]">
            <Icon className="w-4 h-4" strokeWidth={1.5} />
          </div>
          <div className="flex items-center gap-1.5">
            {isDefault && (
              <Badge variant="accent" size="sm">
                Default
              </Badge>
            )}
            <Badge
              variant={connected ? 'success' : 'neutral'}
              dot
              size="sm"
            >
              {connected ? 'Connected' : 'Not connected'}
            </Badge>
          </div>
        </div>

        <div>
          <h3 className="font-semibold text-sm text-[#1C1917]">{meta.label}</h3>
          <p className="text-xs text-[#78716C] mt-0.5">{meta.desc}</p>
        </div>

        {/* Connected details */}
        {connected && (
          <div className="text-xs text-[#78716C] space-y-1 pt-2 border-t border-[#E7E5E4]">
            {providerKey === 'brevo' && (
              <>
                {fields.from_email && (
                  <p className="truncate">
                    <span className="text-[#1C1917] font-medium">From:</span>{' '}
                    {fields.from_email}
                    {fields.from_name ? ` (${fields.from_name})` : ''}
                  </p>
                )}
                {hints.api_key && (
                  <p className="font-mono text-[11px]">
                    Key: ••••{hints.api_key}
                  </p>
                )}
              </>
            )}
            {providerKey === 'smtp' && (
              <>
                {fields.host && (
                  <p className="truncate">
                    <span className="text-[#1C1917] font-medium">Host:</span>{' '}
                    {fields.host}:{fields.port ?? ''}
                  </p>
                )}
                {fields.from_email && (
                  <p className="truncate">
                    <span className="text-[#1C1917] font-medium">From:</span>{' '}
                    {fields.from_email}
                  </p>
                )}
              </>
            )}
            {providerKey === 'twilio' && (
              <>
                {fields.from_number && (
                  <p>
                    <span className="text-[#1C1917] font-medium">From:</span>{' '}
                    {fields.from_number}
                  </p>
                )}
                {hints.account_sid && (
                  <p className="font-mono text-[11px]">
                    SID: ••••{hints.account_sid}
                  </p>
                )}
              </>
            )}

            <div className="pt-1">
              {info.last_verified_at ? (
                <span className="inline-flex items-center gap-1 text-[11px] text-[#15803D]">
                  <CheckCircle2 className="w-3.5 h-3.5" strokeWidth={1.5} />
                  Verified
                </span>
              ) : info.last_error ? (
                <span className="inline-flex items-center gap-1 text-[11px] text-[#B91C1C]">
                  <AlertCircle className="w-3.5 h-3.5" strokeWidth={1.5} />
                  Error in last test
                </span>
              ) : (
                <span className="text-[11px] text-[#A8A29E]">Not yet tested</span>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Action Buttons */}
      {isAdmin && (
        <div className="flex flex-wrap items-center gap-2 pt-4 mt-2 border-t border-[#E7E5E4]">
          <Button
            variant="secondary"
            size="sm"
            className="shrink-0 whitespace-nowrap"
            onClick={() => onEdit(providerKey)}
            disabled={is503}
            icon={Plug}
          >
            {connected ? 'Configure' : 'Connect'}
          </Button>
          {connected && (
            <>
              <Button
                variant="secondary"
                size="sm"
                className="shrink-0 whitespace-nowrap"
                onClick={() => onTest(providerKey)}
                disabled={is503}
              >
                Test
              </Button>
              <Button
                variant="destructive"
                size="sm"
                className="shrink-0 whitespace-nowrap"
                onClick={() => onDisconnect(providerKey)}
                disabled={is503}
              >
                Disconnect
              </Button>
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
  const [useTls, setUseTls] = useState(
    fields.use_tls !== undefined ? fields.use_tls : true
  );

  // Twilio
  const [accountSid, setAccountSid] = useState('');
  const [authToken, setAuthToken] = useState('');
  const [fromNumber, setFromNumber] = useState(fields.from_number || '');

  const [errors, setErrors] = useState({});
  const [serverError, setServerError] = useState(null);
  const [loading, setLoading] = useState(false);

  const meta = PROVIDER_META[providerKey];
  const secretPlaceholder = 'Saved. Leave blank to keep existing.';

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
      else if (!isValidEmail(smtpFromEmail))
        e.smtpFromEmail = 'Must be a valid email.';
    }
    if (providerKey === 'twilio') {
      if (!isEditing && !accountSid) e.accountSid = 'Account SID is required.';
      if (!isEditing && !authToken) e.authToken = 'Auth token is required.';
      if (!fromNumber) e.fromNumber = 'From number is required.';
      else if (!isValidE164(fromNumber))
        e.fromNumber = 'Must be in E.164 format (e.g. +12125550100).';
    }
    return e;
  }

  async function handleSubmit(e) {
    e.preventDefault();
    const errs = validate();
    if (Object.keys(errs).length > 0) {
      setErrors(errs);
      return;
    }
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
        setServerError(
          'This server has no encryption key configured. Ask the operator to set ENCRYPTION_KEY.'
        );
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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="bg-white border border-[#E7E5E4] rounded-[12px] w-full max-w-md shadow-xl overflow-hidden max-h-[90vh] flex flex-col">
        <div className="p-5 border-b border-[#E7E5E4] flex items-center justify-between">
          <h2 className="text-base font-semibold text-[#1C1917]">
            {isEditing ? 'Configure' : 'Connect'} {meta.label}
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded text-[#78716C] hover:text-[#1C1917] transition-colors"
          >
            <X className="w-4 h-4" strokeWidth={1.5} />
          </button>
        </div>

        <div className="p-5 overflow-y-auto space-y-4">
          {is503 && (
            <div className="px-3.5 py-2.5 rounded-[6px] bg-[#FEFCE8] border border-[#FEF08A] text-[#A16207] text-xs">
              This server has no encryption key configured. Ask the operator to set ENCRYPTION_KEY.
            </div>
          )}

          {serverError && (
            <div className="px-3.5 py-2.5 rounded-[6px] bg-[#FEF2F2] border border-[#FECACA] text-[#B91C1C] text-xs">
              {serverError}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            {providerKey === 'brevo' && (
              <>
                <PasswordInput
                  id="brevo-api-key"
                  label={`API Key${isEditing ? '' : ' *'}`}
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  placeholder={
                    isEditing && secrets.includes('api_key')
                      ? secretPlaceholder
                      : 'xkeysib-...'
                  }
                  error={errors.apiKey}
                  autoComplete="off"
                />
                <Input
                  id="brevo-from-email"
                  label="From Email *"
                  type="email"
                  value={fromEmail}
                  onChange={(e) => setFromEmail(e.target.value)}
                  placeholder="sender@example.com"
                  error={errors.fromEmail}
                />
                <Input
                  id="brevo-from-name"
                  label="From Name (optional)"
                  type="text"
                  value={fromName}
                  onChange={(e) => setFromName(e.target.value)}
                  placeholder="Notification Service"
                />
              </>
            )}

            {providerKey === 'smtp' && (
              <>
                <Input
                  id="smtp-host"
                  label="Host *"
                  type="text"
                  value={host}
                  onChange={(e) => setHost(e.target.value)}
                  placeholder="smtp.example.com"
                  error={errors.host}
                />
                <Select
                  id="smtp-port"
                  label="Port *"
                  value={port}
                  onChange={(e) => setPort(e.target.value)}
                >
                  {PORT_OPTIONS.map((p) => (
                    <option key={p} value={p}>
                      {p}
                    </option>
                  ))}
                </Select>
                <Input
                  id="smtp-username"
                  label="Username"
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="smtp-user"
                  autoComplete="username"
                />
                <PasswordInput
                  id="smtp-password"
                  label="Password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder={
                    isEditing && secrets.includes('password')
                      ? secretPlaceholder
                      : ''
                  }
                  autoComplete="new-password"
                />
                <Input
                  id="smtp-from-email"
                  label="From Email *"
                  type="email"
                  value={smtpFromEmail}
                  onChange={(e) => setSmtpFromEmail(e.target.value)}
                  placeholder="notifications@example.com"
                  error={errors.smtpFromEmail}
                />
                <div className="pt-1">
                  <Switch
                    id="smtp-tls"
                    label="Use TLS / STARTTLS"
                    checked={useTls}
                    onChange={setUseTls}
                  />
                </div>
              </>
            )}

            {providerKey === 'twilio' && (
              <>
                <Input
                  id="twilio-sid"
                  label={`Account SID${!isEditing ? ' *' : ''}`}
                  type="text"
                  value={accountSid}
                  onChange={(e) => setAccountSid(e.target.value)}
                  placeholder={
                    isEditing && secrets.includes('account_sid')
                      ? secretPlaceholder
                      : 'ACxxxxxxxx...'
                  }
                  error={errors.accountSid}
                  autoComplete="off"
                />
                <PasswordInput
                  id="twilio-auth-token"
                  label={`Auth Token${!isEditing ? ' *' : ''}`}
                  value={authToken}
                  onChange={(e) => setAuthToken(e.target.value)}
                  placeholder={
                    isEditing && secrets.includes('auth_token')
                      ? secretPlaceholder
                      : ''
                  }
                  error={errors.authToken}
                  autoComplete="off"
                />
                <Input
                  id="twilio-from-number"
                  label="From Number * (E.164)"
                  type="tel"
                  value={fromNumber}
                  onChange={(e) => setFromNumber(e.target.value)}
                  placeholder={EXAMPLE_FROM_PHONE}
                  error={errors.fromNumber}
                />
              </>
            )}

            <p className="text-[11px] text-[#78716C] pt-2 border-t border-[#E7E5E4]">
              {meta.help}
            </p>

            <div className="flex gap-2.5 pt-2">
              <Button
                variant="secondary"
                size="sm"
                className="flex-1"
                onClick={onClose}
                disabled={loading}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                variant="primary"
                size="sm"
                className="flex-1"
                loading={loading}
                disabled={is503}
              >
                Save Provider
              </Button>
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
      setResult({
        ok: false,
        error: err?.detail || err?.message || 'Test failed.',
      });
    } finally {
      setLoading(false);
    }
  }

  function handleClose() {
    onTested();
    onClose();
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="bg-white border border-[#E7E5E4] rounded-[12px] w-full max-w-sm shadow-xl p-5 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold text-[#1C1917]">
            Test {meta.label}
          </h2>
          <button
            type="button"
            onClick={handleClose}
            className="p-1 rounded text-[#78716C] hover:text-[#1C1917]"
          >
            <X className="w-4 h-4" strokeWidth={1.5} />
          </button>
        </div>

        {result ? (
          <div
            className={`px-3.5 py-2.5 rounded-[6px] border text-xs ${
              result.ok
                ? 'bg-[#F0FDF4] border-[#BBF7D0] text-[#15803D]'
                : 'bg-[#FEF2F2] border-[#FECACA] text-[#B91C1C]'
            }`}
          >
            {result.ok ? '✓ Test dispatched successfully.' : `✗ ${result.error || 'Test failed.'}`}
          </div>
        ) : (
          <form onSubmit={handleTest} className="space-y-4">
            <Input
              id="test-to"
              label={isEmail ? 'Recipient Email *' : 'Recipient Phone (E.164) *'}
              type={isEmail ? 'email' : 'tel'}
              required
              value={to}
              onChange={(e) => setTo(e.target.value)}
              placeholder={isEmail ? 'test@example.com' : EXAMPLE_PHONE}
              autoFocus
            />
            <div className="flex gap-2.5 pt-1">
              <Button
                variant="secondary"
                size="sm"
                className="flex-1"
                onClick={handleClose}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                variant="primary"
                size="sm"
                className="flex-1"
                loading={loading}
                disabled={!to}
                icon={Send}
              >
                Send Test
              </Button>
            </div>
          </form>
        )}

        {result && (
          <Button
            variant="secondary"
            size="sm"
            className="w-full"
            onClick={handleClose}
          >
            Close
          </Button>
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

  useEffect(() => {
    load();
  }, [load]);

  async function handleRegen() {
    setRegenLoading(true);
    try {
      const d = await apiFetch('/providers/webhooks/regenerate', {
        method: 'POST',
      });
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
    <Card
      title="Delivery Webhooks"
      subtitle="Configure these ingestion endpoints in your provider portals to receive delivery confirmations, spam flags, and bounce receipts."
    >
      {loading ? (
        <Loading text="Loading webhooks…" />
      ) : error ? (
        <ErrorBanner error={error} onRetry={load} />
      ) : webhooks ? (
        <div className="space-y-4">
          {/* Brevo Webhook URL */}
          <div className="space-y-1.5">
            <label className="block text-xs font-medium text-[#1C1917]">
              Brevo Webhook URL
            </label>
            <div className="flex items-center gap-2 min-w-0">
              <input
                type="text"
                readOnly
                value={webhooks.brevo_url}
                className="block min-w-0 flex-1 bg-[#FAFAF9] border border-[#E7E5E4] rounded-[6px] text-xs font-mono text-[#1C1917] px-3 py-2 select-all focus:outline-none overflow-x-auto"
              />
              <Button
                variant="secondary"
                size="sm"
                className="shrink-0 whitespace-nowrap"
                onClick={() => copyUrl('brevo', webhooks.brevo_url)}
                icon={copiedField === 'brevo' ? Check : Copy}
              >
                {copiedField === 'brevo' ? 'Copied' : 'Copy'}
              </Button>
            </div>
            <p className="text-[11px] text-[#78716C]">
              Paste this URL in Brevo → Transactional → Settings → Webhooks. Enable events: delivered, hard bounce, soft bounce, blocked, spam, error.
            </p>
          </div>

          {/* Twilio Webhook URL */}
          <div className="space-y-1.5">
            <label className="block text-xs font-medium text-[#1C1917]">
              Twilio Webhook URL
            </label>
            <div className="flex items-center gap-2 min-w-0">
              <input
                type="text"
                readOnly
                value={webhooks.twilio_url}
                className="block min-w-0 flex-1 bg-[#FAFAF9] border border-[#E7E5E4] rounded-[6px] text-xs font-mono text-[#1C1917] px-3 py-2 select-all focus:outline-none overflow-x-auto"
              />
              <Button
                variant="secondary"
                size="sm"
                className="shrink-0 whitespace-nowrap"
                onClick={() => copyUrl('twilio', webhooks.twilio_url)}
                icon={copiedField === 'twilio' ? Check : Copy}
              >
                {copiedField === 'twilio' ? 'Copied' : 'Copy'}
              </Button>
            </div>
            <p className="text-[11px] text-[#78716C]">
              The Twilio status callback URL is attached automatically when dispatching outbound payloads — manual setup is optional.
            </p>
          </div>

          {/* Regenerate */}
          <div className="pt-3 border-t border-[#E7E5E4] flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <p className="text-xs font-medium text-[#1C1917]">
                Rotate Webhook URLs
              </p>
              <p className="text-[11px] text-[#78716C]">
                Regenerating creates brand new webhook secrets. Previous endpoints will immediately stop acknowledging incoming events.
              </p>
            </div>
            <Button
              variant="destructive"
              size="sm"
              onClick={() => setConfirmRegen(true)}
              disabled={is503}
              icon={RefreshCw}
            >
              Regenerate URLs
            </Button>
          </div>
        </div>
      ) : null}

      <ConfirmDialog
        open={confirmRegen}
        destructive
        title="Regenerate webhook URLs?"
        message="The previous webhook endpoints will immediately stop acknowledging delivery receipts. You must update your provider settings right away."
        confirmLabel="Regenerate"
        loading={regenLoading}
        onConfirm={handleRegen}
        onCancel={() => setConfirmRegen(false)}
      />
    </Card>
  );
}

function DefaultEmailProviderCard({
  isAdmin,
  is503,
  emailPref,
  availableProviders,
  onPrefChange,
}) {
  if (!isAdmin) return null;

  const emailOptions = availableProviders.filter((p) => p === 'brevo' || p === 'smtp');
  const disabled = emailOptions.length < 2 || is503;

  return (
    <Card className="p-5">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h3 className="font-semibold text-sm text-[#1C1917]">Default email provider</h3>
          <p className="text-xs text-[#78716C] mt-0.5">
            {emailOptions.length < 2
              ? 'Connect at least 2 email providers to set a default fallback preference.'
              : 'Choose which provider to attempt first when sending email notifications.'}
          </p>
        </div>
        <div className="w-48 shrink-0">
          <select
            value={emailPref || ''}
            onChange={(e) => onPrefChange(e.target.value || null)}
            disabled={disabled}
            className="w-full bg-[#FAFAF9] border border-[#E7E5E4] rounded-[6px] px-2.5 py-1.5 text-xs text-[#1C1917] focus:outline-none focus:border-[#4F46E5] disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <option value="">Automatic (default)</option>
            {emailOptions.map((p) => (
              <option key={p} value={p}>
                {PROVIDER_META[p]?.label || p}
              </option>
            ))}
          </select>
        </div>
      </div>
    </Card>
  );
}

export default function ProvidersPage() {
  const { isAdmin } = useAuth();
  const [providers, setProviders] = useState([]);
  const [emailPref, setEmailPref] = useState(null);
  const [availableEmailProviders, setAvailableEmailProviders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [is503, setIs503] = useState(false);

  const [editModal, setEditModal] = useState({ open: false, provider: null });
  const [testModal, setTestModal] = useState({ open: false, provider: null });
  const [disconnectConfirm, setDisconnectConfirm] = useState({
    open: false,
    provider: null,
  });
  const [disconnectLoading, setDisconnectLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setIs503(false);
    try {
      const data = await apiFetch('/providers');
      setProviders(data);
      if (isAdmin) {
        try {
          const prefData = await getEmailPreference();
          setEmailPref(prefData.provider);
          setAvailableEmailProviders(prefData.available || []);
        } catch (_) {}
      }
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
  }, [isAdmin]);

  useEffect(() => {
    load();
  }, [load]);

  const providerMap = {};
  providers.forEach((p) => {
    providerMap[p.provider] = p;
  });

  async function handlePrefChange(newPref) {
    try {
      const res = await setEmailPreference(newPref);
      setEmailPref(res.provider);
    } catch (e) {
      setError(e);
    }
  }

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
        <div className="px-3.5 py-2.5 rounded-[6px] bg-[#FEFCE8] border border-[#FEF08A] text-[#A16207] text-xs">
          ⚠ This server has no encryption key configured. Ask the operator to set ENCRYPTION_KEY. Provider forms are disabled.
        </div>
      )}

      {error && <ErrorBanner error={error} onRetry={load} />}

      {loading ? (
        <Loading text="Loading providers…" />
      ) : (
        <>
          {connectedCount === 0 && !error && !is503 && (
            <div className="px-3.5 py-2.5 rounded-[6px] bg-white border border-[#E7E5E4] text-[#78716C] text-xs flex items-center gap-2">
              <Info className="w-4 h-4 text-[#4F46E5] shrink-0" strokeWidth={1.5} />
              <span>
                No external providers connected yet. Connect your email or SMS gateways to route notifications directly.
              </span>
            </div>
          )}

          <div className="grid gap-4" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))' }}>
            {Object.keys(PROVIDER_META).map((key) => (
              <ProviderCard
                key={key}
                providerKey={key}
                info={providerMap[key]}
                isAdmin={isAdmin}
                is503={is503}
                isDefault={emailPref === key}
                onEdit={(k) => setEditModal({ open: true, provider: k })}
                onTest={(k) => setTestModal({ open: true, provider: k })}
                onDisconnect={(k) =>
                  setDisconnectConfirm({ open: true, provider: k })
                }
              />
            ))}
          </div>

          <DefaultEmailProviderCard
            isAdmin={isAdmin}
            is503={is503}
            emailPref={emailPref}
            availableProviders={availableEmailProviders}
            onPrefChange={handlePrefChange}
          />

          <WebhooksPanel is503={is503} />
        </>
      )}

      {editModal.open && (
        <EditModal
          providerKey={editModal.provider}
          info={providerMap[editModal.provider]}
          is503={is503}
          onClose={() => setEditModal({ open: false, provider: null })}
          onSaved={() => {
            setEditModal({ open: false, provider: null });
            load();
          }}
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
        destructive
        title={`Disconnect ${
          disconnectConfirm.provider
            ? PROVIDER_META[disconnectConfirm.provider]?.label
            : ''
        }?`}
        message="This will remove the provider configuration from this workspace. Delivery will fail until you reconnect."
        confirmLabel="Disconnect"
        loading={disconnectLoading}
        onConfirm={handleDisconnect}
        onCancel={() => setDisconnectConfirm({ open: false, provider: null })}
      />
    </div>
  );
}
