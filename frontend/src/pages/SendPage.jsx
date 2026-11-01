import { useState, useEffect, useId } from 'react';
import { Link } from 'react-router-dom';
import { sendEmail, sendSMS, sendWebhook, listTemplates, ApiError } from '../lib/api';
import { useAuth } from '../lib/auth';
import { validateEmail, validatePhone } from '../lib/csv';
import ErrorBanner from '../components/ErrorBanner';

function renderPreview(text, vars) {
  if (!text) return '';
  return text.replace(/\{\{\s*(\w+)\s*\}\}/g, (match, key) => {
    const val = vars[key];
    return val !== undefined && val !== '' ? String(val) : match;
  });
}

export default function SendPage() {
  const { canWrite } = useAuth();
  const [tab, setTab] = useState('email'); // 'email' | 'sms' | 'webhook'

  // Templates
  const [allTemplates, setAllTemplates] = useState([]);
  const [useTemplate, setUseTemplate] = useState(false);
  const [selectedTemplateId, setSelectedTemplateId] = useState('');
  const [templateVars, setTemplateVars] = useState({});

  // Common fields
  const [recipient, setRecipient] = useState('');
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  const [priority, setPriority] = useState('normal');
  const [category, setCategory] = useState('transactional');

  // Scheduling
  const [isScheduled, setIsScheduled] = useState(false);
  const [scheduledAtRaw, setScheduledAtRaw] = useState('');

  // Status
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [successResult, setSuccessResult] = useState(null);
  const [idempotencyKey, setIdempotencyKey] = useState(() => crypto.randomUUID());

  // Fetch templates once on mount
  useEffect(() => {
    listTemplates({ limit: 200 })
      .then((res) => setAllTemplates(res.data || []))
      .catch(() => {});
  }, []);

  const channelTemplates = allTemplates.filter((t) => t.channel === tab);
  const selectedTemplate = channelTemplates.find((t) => t.id === selectedTemplateId);

  // When switching tabs or template, update template vars
  useEffect(() => {
    setSelectedTemplateId('');
    setTemplateVars({});
  }, [tab, useTemplate]);

  useEffect(() => {
    if (selectedTemplate) {
      const vars = {};
      (selectedTemplate.variables || []).forEach((v) => {
        vars[v] = '';
      });
      setTemplateVars(vars);
    } else {
      setTemplateVars({});
    }
  }, [selectedTemplate]);

  // Validation
  let validationError = null;
  if (!recipient.trim()) {
    validationError = 'Recipient is required.';
  } else if (tab === 'email' && !validateEmail(recipient.trim())) {
    validationError = 'Invalid email address format.';
  } else if (tab === 'sms' && !validatePhone(recipient.trim())) {
    validationError = 'Phone number must be 10 to 15 digits (optional leading +).';
  } else if (tab === 'webhook') {
    if (!recipient.trim().startsWith('https://')) {
      validationError = 'Webhook URL must start with https://';
    } else if (!recipient.includes('slack.com') && !recipient.includes('discord.com') && !recipient.includes('discordapp.com')) {
      validationError = 'Only Slack (hooks.slack.com) and Discord webhook URLs are supported.';
    }
  }

  if (!validationError && tab !== 'webhook' && useTemplate) {
    if (!selectedTemplate) {
      validationError = 'Please select a template.';
    } else {
      const missing = (selectedTemplate.variables || []).filter((v) => !templateVars[v]?.trim());
      if (missing.length > 0) {
        validationError = `Please provide values for all variables: ${missing.join(', ')}`;
      }
    }
  }

  if (!validationError && tab === 'email' && !useTemplate) {
    if (!subject.trim()) validationError = 'Subject is required.';
    else if (!body.trim()) validationError = 'Body is required.';
  }

  if (!validationError && tab === 'sms' && !useTemplate) {
    if (!body.trim()) validationError = 'Message is required.';
    else if (body.length > 1600) validationError = 'Message cannot exceed 1600 characters.';
  }

  if (!validationError && tab === 'webhook') {
    if (!body.trim()) validationError = 'Webhook payload body is required.';
  }

  let scheduleIso = null;
  if (!validationError && isScheduled && tab !== 'webhook') {
    if (!scheduledAtRaw) {
      validationError = 'Please select a scheduled date and time.';
    } else {
      const schedDate = new Date(scheduledAtRaw);
      const now = new Date();
      const maxDate = new Date(now.getTime() + 30 * 24 * 60 * 60 * 1000);
      if (schedDate <= now) {
        validationError = 'Scheduled time must be in the future.';
      } else if (schedDate > maxDate) {
        validationError = 'Scheduled time cannot be more than 30 days ahead.';
      } else {
        scheduleIso = schedDate.toISOString();
      }
    }
  }

  async function handleSubmit(e) {
    e.preventDefault();
    if (!canWrite) {
      setError(new Error('Write access required.'));
      return;
    }
    if (validationError) {
      setError(new Error(validationError));
      return;
    }

    setLoading(true);
    setError(null);
    setSuccessResult(null);

    try {
      let res;
      if (tab === 'email') {
        const payload = {
          recipient: recipient.trim(),
          priority,
          category,
          scheduled_at: scheduleIso || undefined,
        };
        if (useTemplate) {
          payload.template_id = selectedTemplate.id;
          payload.variables = templateVars;
        } else {
          payload.subject = subject.trim();
          payload.body = body;
        }
        res = await sendEmail(payload, idempotencyKey);
      } else if (tab === 'sms') {
        const payload = {
          recipient: recipient.trim(),
          priority,
          category,
          scheduled_at: scheduleIso || undefined,
        };
        if (useTemplate) {
          payload.template_id = selectedTemplate.id;
          payload.variables = templateVars;
        } else {
          payload.message = body;
        }
        res = await sendSMS(payload, idempotencyKey);
      } else {
        // webhook
        const payload = {
          recipient: recipient.trim(),
          body,
          priority,
        };
        res = await sendWebhook(payload, idempotencyKey);
      }

      setSuccessResult(res);
      // Generate new idempotency key for next submission
      setIdempotencyKey(crypto.randomUUID());

      // Clear form values on success
      setRecipient('');
      setSubject('');
      setBody('');
      setScheduledAtRaw('');
      setIsScheduled(false);
      setUseTemplate(false);
      setSelectedTemplateId('');
      setTemplateVars({});
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">Send Notification</h1>
      </div>

      {error && <ErrorBanner error={error} />}

      {successResult && (
        <div
          className={`rounded-xl p-4 border flex flex-col sm:flex-row sm:items-center justify-between gap-3 ${
            successResult.status === 'suppressed'
              ? 'bg-amber-950/40 border-amber-800 text-amber-300'
              : 'bg-emerald-950/40 border-emerald-800 text-emerald-300'
          }`}
        >
          <div>
            <p className="font-semibold text-sm">
              {successResult.status === 'suppressed'
                ? '⚠ Recipient is on the suppression list, nothing was sent'
                : `Notification queued (${successResult.status})!`}
            </p>
            {successResult.scheduled_at && (
              <p className="text-xs mt-1 text-purple-300">
                Scheduled for: {new Date(successResult.scheduled_at).toLocaleString()}
              </p>
            )}
            <p className="text-xs font-mono opacity-80 mt-0.5">ID: {successResult.id}</p>
          </div>
          <Link
            to={`/notifications/${successResult.id}`}
            className="self-start sm:self-auto px-3 py-1.5 rounded-lg bg-gray-800 hover:bg-gray-700 text-white text-xs font-medium border border-gray-700 shrink-0"
          >
            View Notification &rarr;
          </Link>
        </div>
      )}

      <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 shadow-xl">
        {/* Tabs */}
        <div className="flex gap-2 mb-6 border-b border-gray-800 pb-4">
          <button
            type="button"
            onClick={() => setTab('email')}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              tab === 'email' ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-300 hover:bg-gray-700'
            }`}
          >
            Email
          </button>
          <button
            type="button"
            onClick={() => setTab('sms')}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              tab === 'sms' ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-300 hover:bg-gray-700'
            }`}
          >
            SMS
          </button>
          <button
            type="button"
            onClick={() => setTab('webhook')}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              tab === 'webhook' ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-300 hover:bg-gray-700'
            }`}
          >
            Slack / Discord
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Recipient */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1" htmlFor="recipient">
              {tab === 'email' ? 'Recipient Email' : tab === 'sms' ? 'Recipient Phone' : 'Webhook URL'}
            </label>
            <input
              id="recipient"
              type={tab === 'email' ? 'email' : tab === 'sms' ? 'tel' : 'url'}
              required
              value={recipient}
              onChange={(e) => setRecipient(e.target.value)}
              placeholder={
                tab === 'email'
                  ? 'user@example.com'
                  : tab === 'sms'
                  ? '+15551234567'
                  : 'https://hooks.slack.com/services/... or https://discord.com/api/webhooks/...'
              }
              className="w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 text-sm"
            />
            {tab === 'webhook' && (
              <p className="text-xs text-gray-400 mt-1">
                Must start with https:// and only Slack (hooks.slack.com) or Discord (discord.com) URLs are accepted.
              </p>
            )}
          </div>

          {/* Template toggle for Email/SMS */}
          {tab !== 'webhook' && (
            <div className="pt-1">
              <label className="flex items-center gap-2 cursor-pointer text-sm text-gray-300">
                <input
                  type="checkbox"
                  checked={useTemplate}
                  onChange={(e) => setUseTemplate(e.target.checked)}
                  className="rounded bg-gray-800 border-gray-700 text-blue-600 focus:ring-0"
                />
                Use a template
              </label>
            </div>
          )}

          {/* Template Selection */}
          {tab !== 'webhook' && useTemplate && (
            <div className="space-y-4 p-4 rounded-xl bg-gray-950/60 border border-gray-800">
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-1">Select Template</label>
                {channelTemplates.length === 0 ? (
                  <p className="text-xs text-gray-500">No {tab.toUpperCase()} templates available. Create one first under Templates.</p>
                ) : (
                  <select
                    value={selectedTemplateId}
                    onChange={(e) => setSelectedTemplateId(e.target.value)}
                    className="w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 text-white text-sm"
                  >
                    <option value="">-- Choose a template --</option>
                    {channelTemplates.map((t) => (
                      <option key={t.id} value={t.id}>
                        {t.name} ({t.variables?.length || 0} vars)
                      </option>
                    ))}
                  </select>
                )}
              </div>

              {selectedTemplate && (
                <>
                  {/* Variable inputs */}
                  {(selectedTemplate.variables || []).length > 0 && (
                    <div className="space-y-2">
                      <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Template Variables</p>
                      {selectedTemplate.variables.map((v) => (
                        <div key={v}>
                          <label className="block text-xs text-gray-300 mb-0.5">{`{{${v}}}`}</label>
                          <input
                            type="text"
                            required
                            value={templateVars[v] || ''}
                            onChange={(e) => setTemplateVars({ ...templateVars, [v]: e.target.value })}
                            placeholder={`Value for ${v}`}
                            className="w-full px-3 py-1.5 rounded-lg bg-gray-800 border border-gray-700 text-white text-sm"
                          />
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Live Preview */}
                  <div className="p-3 bg-gray-900 rounded-lg border border-gray-800 space-y-2">
                    <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Live Preview</p>
                    {tab === 'email' && selectedTemplate.subject_template && (
                      <div>
                        <span className="text-xs text-gray-500 block">Subject:</span>
                        <p className="text-sm font-medium text-gray-200">
                          {renderPreview(selectedTemplate.subject_template, templateVars)}
                        </p>
                      </div>
                    )}
                    <div>
                      <span className="text-xs text-gray-500 block">Body:</span>
                      <pre className="text-xs font-mono text-gray-300 whitespace-pre-wrap">
                        {renderPreview(selectedTemplate.body_template, templateVars)}
                      </pre>
                    </div>
                  </div>
                </>
              )}
            </div>
          )}

          {/* Direct Subject and Body (when NOT using template) */}
          {tab === 'email' && !useTemplate && (
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1" htmlFor="subject">
                Subject
              </label>
              <input
                id="subject"
                type="text"
                required
                maxLength={255}
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
                placeholder="Notification Subject"
                className="w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 text-sm"
              />
            </div>
          )}

          {((tab === 'email' && !useTemplate) || (tab === 'sms' && !useTemplate) || tab === 'webhook') && (
            <div>
              <div className="flex justify-between items-center mb-1">
                <label className="block text-sm font-medium text-gray-300" htmlFor="body">
                  {tab === 'email' ? 'Body' : tab === 'sms' ? 'Message' : 'Payload Body'}
                </label>
                {tab === 'sms' && (
                  <span className={`text-xs ${body.length > 1600 ? 'text-red-400' : 'text-gray-400'}`}>
                    {body.length} / 1600
                  </span>
                )}
              </div>
              <textarea
                id="body"
                required
                rows={4}
                maxLength={tab === 'sms' ? 1600 : undefined}
                value={body}
                onChange={(e) => setBody(e.target.value)}
                placeholder={
                  tab === 'email'
                    ? 'Enter email body content...'
                    : tab === 'sms'
                    ? 'Enter SMS message content...'
                    : 'Enter message payload to post to webhook...'
                }
                className="w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 text-sm"
              />
            </div>
          )}

          {/* Options: Priority, Category, Schedule */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2 border-t border-gray-800">
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1">Priority</label>
              <select
                value={priority}
                onChange={(e) => setPriority(e.target.value)}
                className="w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 text-white text-sm"
              >
                <option value="high">High</option>
                <option value="normal">Normal</option>
                <option value="low">Low</option>
              </select>
            </div>

            {tab !== 'webhook' && (
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-1">Category</label>
                <select
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 text-white text-sm"
                >
                  <option value="transactional">Transactional</option>
                  <option value="marketing">Marketing</option>
                </select>
                <p className="text-xs text-gray-500 mt-1">
                  marketing respects unsubscribes and adds an unsubscribe link; transactional is for OTPs and receipts
                </p>
              </div>
            )}
          </div>

          {/* Scheduling option */}
          {tab !== 'webhook' && (
            <div className="space-y-2 pt-2 border-t border-gray-800">
              <label className="flex items-center gap-2 cursor-pointer text-sm text-gray-300">
                <input
                  type="checkbox"
                  checked={isScheduled}
                  onChange={(e) => setIsScheduled(e.target.checked)}
                  className="rounded bg-gray-800 border-gray-700 text-blue-600 focus:ring-0"
                />
                Schedule delivery
              </label>
              {isScheduled && (
                <div>
                  <input
                    type="datetime-local"
                    value={scheduledAtRaw}
                    onChange={(e) => setScheduledAtRaw(e.target.value)}
                    className="px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 text-white text-sm"
                  />
                  <p className="text-xs text-gray-500 mt-1">
                    Must be in the future and at most 30 days ahead.
                  </p>
                </div>
              )}
            </div>
          )}

          {/* Submit */}
          <div className="pt-4">
            <button
              type="submit"
              disabled={loading || Boolean(validationError)}
              className="w-full sm:w-auto px-6 py-2.5 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm font-medium transition-colors"
            >
              {loading ? 'Sending...' : `Send ${tab === 'email' ? 'Email' : tab === 'sms' ? 'SMS' : 'Webhook'}`}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
