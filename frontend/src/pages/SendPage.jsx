import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import {
  Mail,
  MessageSquare,
  Webhook,
  Send,
  Check,
  Eye,
} from 'lucide-react';
import {
  sendEmail,
  sendSMS,
  sendWebhook,
  listTemplates,
} from '../lib/api';
import { useAuth } from '../lib/auth';
import { validateEmail, validatePhone } from '../lib/csv';
import { describeError } from '../lib/errors';
import Button from '../components/ui/Button';
import Input from '../components/ui/Input';
import Select from '../components/ui/Select';
import Switch from '../components/ui/Switch';

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
  const [errorAction, setErrorAction] = useState(null);
  const [successResult, setSuccessResult] = useState(null);
  const [idempotencyKey, setIdempotencyKey] = useState(() =>
    crypto.randomUUID()
  );

  // Fetch templates once on mount
  useEffect(() => {
    listTemplates({ limit: 200 })
      .then((res) => setAllTemplates(res.data || []))
      .catch(() => {});
  }, []);

  const channelTemplates = allTemplates.filter((t) => t.channel === tab);
  const selectedTemplate = channelTemplates.find(
    (t) => t.id === selectedTemplateId
  );

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
    } else if (
      !recipient.includes('slack.com') &&
      !recipient.includes('discord.com') &&
      !recipient.includes('discordapp.com')
    ) {
      validationError =
        'Only Slack (hooks.slack.com) and Discord webhook URLs are supported.';
    }
  }

  if (!validationError && tab !== 'webhook' && useTemplate) {
    if (!selectedTemplate) {
      validationError = 'Please select a template.';
    } else {
      const missing = (selectedTemplate.variables || []).filter(
        (v) => !templateVars[v]?.trim()
      );
      if (missing.length > 0) {
        validationError = `Please provide values for all variables: ${missing.join(
          ', '
        )}`;
      }
    }
  }

  if (!validationError && tab === 'email' && !useTemplate) {
    if (!subject.trim()) validationError = 'Subject is required.';
    else if (!body.trim()) validationError = 'Body is required.';
  }

  if (!validationError && tab === 'sms' && !useTemplate) {
    if (!body.trim()) validationError = 'Message is required.';
    else if (body.length > 1600)
      validationError = 'Message cannot exceed 1600 characters.';
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
    setErrorAction(null);
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
      setIdempotencyKey(crypto.randomUUID());

      // Reset fields on success
      setRecipient('');
      setSubject('');
      setBody('');
      setScheduledAtRaw('');
      setIsScheduled(false);
      setUseTemplate(false);
      setSelectedTemplateId('');
      setTemplateVars({});
    } catch (err) {
      const desc = describeError(err);
      setError(desc.title + ': ' + desc.message);
      if (desc.action) {
        setErrorAction(desc.action);
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-6 max-w-[760px]">
      <div>
        <h1 className="text-xl sm:text-2xl font-semibold text-[#1C1917] tracking-tight">
          Send Notification
        </h1>
        <p className="text-xs sm:text-sm text-[#78716C] mt-0.5">
          Dispatch a single notification now or schedule it for future delivery.
        </p>
      </div>

      {error && (
        <div className="flex items-center justify-between gap-3 px-3.5 py-2.5 rounded-[6px] bg-[#FEF2F2] border border-[#FECACA] text-[#B91C1C] text-xs">
          <span>{typeof error === 'string' ? error : error?.message || String(error)}</span>
          {errorAction && (
            <Link
              to={errorAction.to}
              className="shrink-0 px-2.5 py-1 rounded-[4px] bg-white border border-[#FECACA] hover:bg-[#FEF2F2] text-[#B91C1C] font-medium"
            >
              {errorAction.label}
            </Link>
          )}
        </div>
      )}

      {successResult && (
        <div
          className={`rounded-[8px] p-4 border flex flex-col sm:flex-row sm:items-center justify-between gap-3 ${
            successResult.status === 'suppressed'
              ? 'bg-[#FEFCE8] border-[#FEF08A] text-[#A16207]'
              : 'bg-[#F0FDF4] border-[#BBF7D0] text-[#15803D]'
          }`}
        >
          <div>
            <p className="font-semibold text-xs sm:text-sm flex items-center gap-1.5">
              <Check className="w-4 h-4" strokeWidth={2} />
              {successResult.status === 'suppressed'
                ? 'Recipient is suppressed — message discarded.'
                : `Notification queued (${successResult.status})`}
            </p>
            {successResult.scheduled_at && (
              <p className="text-xs mt-1 text-[#4F46E5]">
                Scheduled for: {new Date(successResult.scheduled_at).toLocaleString()}
              </p>
            )}
            <p className="text-[11px] font-mono opacity-80 mt-0.5">
              ID: {successResult.id}
            </p>
          </div>
          <Link to={`/notifications/${successResult.id}`}>
            <Button variant="secondary" size="sm">
              View Status →
            </Button>
          </Link>
        </div>
      )}

      {/* Main Send Form Card */}
      <div className="bg-white border border-[#E7E5E4] rounded-[8px] p-6 shadow-xs space-y-6">
        {/* Underline Tabs */}
        <div className="border-b border-[#E7E5E4] -mt-1 pb-px">
          <div className="flex gap-6">
            <button
              type="button"
              onClick={() => setTab('email')}
              className={`pb-2.5 text-xs sm:text-sm font-medium border-b-2 flex items-center gap-2 cursor-pointer transition-colors ${
                tab === 'email'
                  ? 'border-[#4F46E5] text-[#1C1917]'
                  : 'border-transparent text-[#78716C] hover:text-[#1C1917]'
              }`}
            >
              <Mail className="w-4 h-4" strokeWidth={1.5} />
              Email
            </button>
            <button
              type="button"
              onClick={() => setTab('sms')}
              className={`pb-2.5 text-xs sm:text-sm font-medium border-b-2 flex items-center gap-2 cursor-pointer transition-colors ${
                tab === 'sms'
                  ? 'border-[#4F46E5] text-[#1C1917]'
                  : 'border-transparent text-[#78716C] hover:text-[#1C1917]'
              }`}
            >
              <MessageSquare className="w-4 h-4" strokeWidth={1.5} />
              SMS
            </button>
            <button
              type="button"
              onClick={() => setTab('webhook')}
              className={`pb-2.5 text-xs sm:text-sm font-medium border-b-2 flex items-center gap-2 cursor-pointer transition-colors ${
                tab === 'webhook'
                  ? 'border-[#4F46E5] text-[#1C1917]'
                  : 'border-transparent text-[#78716C] hover:text-[#1C1917]'
              }`}
            >
              <Webhook className="w-4 h-4" strokeWidth={1.5} />
              Slack / Discord
            </button>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-5">
          {/* Recipient */}
          <Input
            id="recipient"
            label={
              tab === 'email'
                ? 'Recipient Email *'
                : tab === 'sms'
                ? 'Recipient Phone Number (E.164) *'
                : 'Webhook Endpoint URL *'
            }
            type={tab === 'email' ? 'email' : tab === 'sms' ? 'tel' : 'url'}
            required
            value={recipient}
            onChange={(e) => setRecipient(e.target.value)}
            placeholder={
              tab === 'email'
                ? 'user@example.com'
                : tab === 'sms'
                ? '+18166843869'
                : 'https://hooks.slack.com/services/... or https://discord.com/api/webhooks/...'
            }
            helper={
              tab === 'webhook'
                ? 'Only Slack (hooks.slack.com) and Discord (discord.com) URLs are accepted.'
                : undefined
            }
          />

          {/* Template switch for Email / SMS */}
          {tab !== 'webhook' && (
            <div className="pt-1">
              <Switch
                id="toggle-template"
                label="Use a template"
                description="Inject dynamic parameters into a pre-registered template."
                checked={useTemplate}
                onChange={setUseTemplate}
              />
            </div>
          )}

          {/* Template selection & inputs */}
          {tab !== 'webhook' && useTemplate && (
            <div className="space-y-4 p-4 rounded-[6px] bg-[#FAFAF9] border border-[#E7E5E4]">
              <Select
                id="template-select"
                label="Select Template"
                value={selectedTemplateId}
                onChange={(e) => setSelectedTemplateId(e.target.value)}
              >
                <option value="">-- Choose a template --</option>
                {channelTemplates.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name} ({t.variables?.length || 0} variables)
                  </option>
                ))}
              </Select>

              {selectedTemplate && (
                <>
                  {(selectedTemplate.variables || []).length > 0 && (
                    <div className="space-y-2 pt-2 border-t border-[#E7E5E4]">
                      <p className="text-[11px] font-semibold text-[#78716C] uppercase tracking-wider">
                        Template Variables
                      </p>
                      {selectedTemplate.variables.map((v) => (
                        <Input
                          key={v}
                          id={`var-${v}`}
                          label={`{{${v}}}`}
                          type="text"
                          required
                          value={templateVars[v] || ''}
                          onChange={(e) =>
                            setTemplateVars({
                              ...templateVars,
                              [v]: e.target.value,
                            })
                          }
                          placeholder={`Value for ${v}`}
                        />
                      ))}
                    </div>
                  )}

                  {/* Live Preview Box */}
                  <div className="p-3 bg-white rounded-[6px] border border-[#E7E5E4] space-y-1.5">
                    <p className="text-[11px] font-semibold text-[#78716C] uppercase tracking-wider flex items-center gap-1">
                      <Eye className="w-3.5 h-3.5" strokeWidth={1.5} />
                      Live Render Preview
                    </p>
                    {tab === 'email' && selectedTemplate.subject_template && (
                      <div>
                        <span className="text-[11px] text-[#78716C]">
                          Subject:
                        </span>
                        <p className="text-xs font-medium text-[#1C1917]">
                          {renderPreview(
                            selectedTemplate.subject_template,
                            templateVars
                          )}
                        </p>
                      </div>
                    )}
                    <div>
                      <span className="text-[11px] text-[#78716C]">Body:</span>
                      <pre className="text-xs font-mono text-[#1C1917] whitespace-pre-wrap mt-0.5">
                        {renderPreview(
                          selectedTemplate.body_template,
                          templateVars
                        )}
                      </pre>
                    </div>
                  </div>
                </>
              )}
            </div>
          )}

          {/* Direct Subject & Body */}
          {tab === 'email' && !useTemplate && (
            <Input
              id="direct-subject"
              label="Subject *"
              type="text"
              required
              maxLength={255}
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              placeholder="e.g. Account Security Notification"
            />
          )}

          {((tab === 'email' && !useTemplate) ||
            (tab === 'sms' && !useTemplate) ||
            tab === 'webhook') && (
            <div className="space-y-1.5">
              <div className="flex justify-between items-center">
                <label
                  htmlFor="direct-body"
                  className="block text-xs font-medium text-[#1C1917]"
                >
                  {tab === 'email'
                    ? 'Body *'
                    : tab === 'sms'
                    ? 'Message Content *'
                    : 'Payload Body *'}
                </label>
                {tab === 'sms' && (
                  <span
                    className={`text-[11px] ${
                      body.length > 1600
                        ? 'text-[#B91C1C] font-semibold'
                        : 'text-[#78716C]'
                    }`}
                  >
                    {body.length} / 1600
                  </span>
                )}
              </div>
              <textarea
                id="direct-body"
                required
                rows={4}
                maxLength={tab === 'sms' ? 1600 : undefined}
                value={body}
                onChange={(e) => setBody(e.target.value)}
                placeholder={
                  tab === 'email'
                    ? 'Enter notification message...'
                    : tab === 'sms'
                    ? 'Enter SMS text...'
                    : 'Enter JSON or text payload...'
                }
                className="w-full text-xs px-3 py-2 rounded-[6px] bg-white border border-[#E7E5E4] text-[#1C1917] placeholder:text-[#A8A29E] focus:outline-none focus:ring-2 focus:ring-[#4F46E5]/20 focus:border-[#4F46E5]"
              />
            </div>
          )}

          {/* Priority & Category (Segmented Control) */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-3 border-t border-[#E7E5E4]">
            <Select
              id="send-priority"
              label="Priority Level"
              value={priority}
              onChange={(e) => setPriority(e.target.value)}
            >
              <option value="high">High (Immediate)</option>
              <option value="normal">Normal (Standard)</option>
              <option value="low">Low (Bulk Background)</option>
            </Select>

            {tab !== 'webhook' && (
              <div className="space-y-1.5">
                <label className="block text-xs font-medium text-[#1C1917]">
                  Category
                </label>
                {/* Segmented Control */}
                <div className="inline-flex rounded-[6px] border border-[#E7E5E4] bg-[#FAFAF9] p-0.5 w-full">
                  <button
                    type="button"
                    onClick={() => setCategory('transactional')}
                    className={`flex-1 py-1.5 text-xs font-medium rounded-[4px] transition-colors cursor-pointer ${
                      category === 'transactional'
                        ? 'bg-white text-[#1C1917] shadow-xs'
                        : 'text-[#78716C] hover:text-[#1C1917]'
                    }`}
                  >
                    Transactional
                  </button>
                  <button
                    type="button"
                    onClick={() => setCategory('marketing')}
                    className={`flex-1 py-1.5 text-xs font-medium rounded-[4px] transition-colors cursor-pointer ${
                      category === 'marketing'
                        ? 'bg-white text-[#1C1917] shadow-xs'
                        : 'text-[#78716C] hover:text-[#1C1917]'
                    }`}
                  >
                    Marketing
                  </button>
                </div>
                <p className="text-[11px] text-[#78716C]">
                  Marketing automatically includes unsubscribe headers and links.
                </p>
              </div>
            )}
          </div>

          {/* Scheduling option (Switch) */}
          {tab !== 'webhook' && (
            <div className="space-y-3 pt-3 border-t border-[#E7E5E4]">
              <Switch
                id="toggle-schedule"
                label="Schedule delivery"
                description="Queue this notification to dispatch at a future timestamp (up to 30 days)."
                checked={isScheduled}
                onChange={setIsScheduled}
              />
              {isScheduled && (
                <div className="pl-12 max-w-xs">
                  <Input
                    id="schedule-time"
                    type="datetime-local"
                    value={scheduledAtRaw}
                    onChange={(e) => setScheduledAtRaw(e.target.value)}
                  />
                </div>
              )}
            </div>
          )}

          {/* Submit Action in sticky container */}
          <div className="pt-4 border-t border-[#E7E5E4] flex justify-end">
            <Button
              type="submit"
              variant="primary"
              size="md"
              loading={loading}
              disabled={Boolean(validationError)}
              icon={Send}
            >
              {loading
                ? 'Dispatching…'
                : `Send ${
                    tab === 'email'
                      ? 'Email'
                      : tab === 'sms'
                      ? 'SMS'
                      : 'Webhook'
                  }`}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
