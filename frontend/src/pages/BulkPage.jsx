import { useState, useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import {
  Mail,
  MessageSquare,
  Upload,
  Send,
  Check,
  AlertCircle,
} from 'lucide-react';
import { sendBulk, getBatchStatus, listTemplates, getEmailPreference } from '../lib/api';
import { useAuth } from '../lib/auth';
import { parseRecipientsData } from '../lib/csv';
import { describeError } from '../lib/errors';
import StatusBadge from '../components/StatusBadge';
import Button from '../components/ui/Button';
import Input from '../components/ui/Input';
import Select from '../components/ui/Select';
import Switch from '../components/ui/Switch';

export default function BulkPage() {
  const { canWrite } = useAuth();
  const [channel, setChannel] = useState('email'); // 'email' | 'sms'

  // Templates
  const [allTemplates, setAllTemplates] = useState([]);
  const [useTemplate, setUseTemplate] = useState(false);
  const [selectedTemplateId, setSelectedTemplateId] = useState('');

  // Common direct content
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  const [priority, setPriority] = useState('normal');
  const [category, setCategory] = useState('transactional');

  // Scheduling
  const [isScheduled, setIsScheduled] = useState(false);
  const [scheduledAtRaw, setScheduledAtRaw] = useState('');

  // Recipients input
  const [rawText, setRawText] = useState('');
  const [fileName, setFileName] = useState('');

  // Submission & Batch polling
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [errorAction, setErrorAction] = useState(null);
  const [batchInfo, setBatchInfo] = useState(null);
  const [batchStatus, setBatchStatus] = useState(null);
  const pollTimerRef = useRef(null);

  // Email provider choice
  const [emailProvider, setEmailProvider] = useState('');
  const [availableEmailProviders, setAvailableEmailProviders] = useState([]);

  // Fetch templates once on mount
  useEffect(() => {
    listTemplates({ limit: 200 })
      .then((res) => setAllTemplates(res.data || []))
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (channel === 'email') {
      getEmailPreference()
        .then((res) => setAvailableEmailProviders(res.available || []))
        .catch(() => {});
    }
  }, [channel]);

  const channelTemplates = allTemplates.filter((t) => t.channel === channel);
  const selectedTemplate = channelTemplates.find(
    (t) => t.id === selectedTemplateId
  );
  const templateVariables = selectedTemplate?.variables || [];

  useEffect(() => {
    setSelectedTemplateId('');
  }, [channel]);

  function handleFileUpload(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setFileName(file.name);
    const reader = new FileReader();
    reader.onload = (event) => {
      const content = event.target?.result;
      if (typeof content === 'string') {
        setRawText(content);
      }
    };
    reader.readAsText(file);
  }

  const parsed = parseRecipientsData(rawText, {
    channel,
    hasTemplate: useTemplate,
    templateVariables,
  });

  let formError = null;
  if (useTemplate && !selectedTemplate) {
    formError = 'Please select a template.';
  } else if (!useTemplate && channel === 'email') {
    if (!subject.trim()) formError = 'Subject is required.';
    else if (!body.trim()) formError = 'Body is required.';
  } else if (!useTemplate && channel === 'sms') {
    if (!body.trim()) formError = 'Message is required.';
    else if (body.length > 1600)
      formError = 'Message cannot exceed 1600 characters.';
  }

  let scheduleIso = null;
  if (!formError && isScheduled) {
    if (!scheduledAtRaw) {
      formError = 'Please choose a schedule date and time.';
    } else {
      const schedDate = new Date(scheduledAtRaw);
      const now = new Date();
      const maxDate = new Date(now.getTime() + 30 * 24 * 60 * 60 * 1000);
      if (schedDate <= now) {
        formError = 'Scheduled time must be in the future.';
      } else if (schedDate > maxDate) {
        formError = 'Scheduled time cannot be more than 30 days ahead.';
      } else {
        scheduleIso = schedDate.toISOString();
      }
    }
  }

  const isBlocked =
    Boolean(formError) ||
    parsed.errors.length > 0 ||
    parsed.validRows.length === 0;

  useEffect(() => {
    if (!batchInfo?.batch_id) return;

    async function poll() {
      try {
        const status = await getBatchStatus(batchInfo.batch_id);
        setBatchStatus(status);

        const counts = status.counts_by_status || {};
        const activeStatuses = [
          'pending',
          'processing',
          'retrying',
          'scheduled',
        ];
        const hasActive = activeStatuses.some((st) => (counts[st] || 0) > 0);

        if (!hasActive && pollTimerRef.current) {
          clearInterval(pollTimerRef.current);
          pollTimerRef.current = null;
        }
      } catch (_) {}
    }

    poll();
    pollTimerRef.current = setInterval(poll, 5000);

    return () => {
      if (pollTimerRef.current) {
        clearInterval(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    };
  }, [batchInfo]);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!canWrite) {
      setError(new Error('Write access required.'));
      return;
    }
    if (isBlocked) {
      setError(new Error(formError || parsed.errors[0]));
      return;
    }

    setLoading(true);
    setError(null);
    setErrorAction(null);
    setBatchInfo(null);
    setBatchStatus(null);

    try {
      const payload = {
        channel,
        recipients: parsed.validRows,
        priority,
        category,
        scheduled_at: scheduleIso || undefined,
        provider: channel === 'email' ? (emailProvider || undefined) : undefined,
      };

      if (useTemplate) {
        payload.template_id = selectedTemplate.id;
      } else if (channel === 'email') {
        payload.subject = subject.trim();
        payload.body = body;
      } else {
        payload.message = body;
      }

      const res = await sendBulk(payload);
      setBatchInfo(res);
      setRawText('');
      setFileName('');
      setEmailProvider('');
      setSubject('');
      setBody('');
      setScheduledAtRaw('');
      setIsScheduled(false);
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
          Bulk Notifications
        </h1>
        <p className="text-xs sm:text-sm text-[#78716C] mt-0.5">
          Dispatch a single message to up to 200 recipients simultaneously.
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

      {/* Batch Summary Card */}
      {batchInfo && (
        <div className="bg-white border border-[#E7E5E4] rounded-[8px] p-5 shadow-xs space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#E7E5E4] pb-3">
            <div>
              <h3 className="text-sm font-semibold text-[#15803D] flex items-center gap-1.5">
                <Check className="w-4 h-4" strokeWidth={2} />
                Batch Queued Successfully
              </h3>
              <p className="text-xs font-mono text-[#78716C] mt-0.5">
                Batch ID: {batchInfo.batch_id}
              </p>
            </div>
            <Link
              to={`/notifications?batch_id=${encodeURIComponent(
                batchInfo.batch_id
              )}`}
            >
              <Button variant="secondary" size="sm">
                View in Notifications →
              </Button>
            </Link>
          </div>

          <div className="grid grid-cols-3 gap-3 text-xs">
            <div className="p-3 bg-[#FAFAF9] rounded-[6px] border border-[#E7E5E4]">
              <span className="text-[#78716C] block">Queued</span>
              <span className="text-lg font-semibold text-[#15803D]">
                {batchInfo.queued}
              </span>
            </div>
            <div className="p-3 bg-[#FAFAF9] rounded-[6px] border border-[#E7E5E4]">
              <span className="text-[#78716C] block">Suppressed</span>
              <span className="text-lg font-semibold text-[#A16207]">
                {batchInfo.suppressed}
              </span>
            </div>
            <div className="p-3 bg-[#FAFAF9] rounded-[6px] border border-[#E7E5E4]">
              <span className="text-[#78716C] block">Total In Batch</span>
              <span className="text-lg font-semibold text-[#1C1917]">
                {batchStatus?.total ?? batchInfo.queued + batchInfo.suppressed}
              </span>
            </div>
          </div>

          {batchStatus?.counts_by_status && (
            <div className="space-y-1.5 pt-1">
              <p className="text-[11px] font-semibold text-[#78716C] uppercase tracking-wider">
                Live Status Breakdown
              </p>
              <div className="flex flex-wrap gap-2">
                {Object.entries(batchStatus.counts_by_status).map(
                  ([st, count]) => (
                    <div
                      key={st}
                      className="flex items-center gap-1.5 px-2.5 py-1 rounded-[4px] bg-[#FAFAF9] border border-[#E7E5E4] text-xs"
                    >
                      <StatusBadge status={st} />
                      <span className="font-semibold text-[#1C1917]">
                        {count}
                      </span>
                    </div>
                  )
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Bulk Form Card */}
      <div className="bg-white border border-[#E7E5E4] rounded-[8px] p-6 shadow-xs space-y-6">
        {/* Underline Tabs */}
        <div className="border-b border-[#E7E5E4] -mt-1 pb-px">
          <div className="flex gap-6">
            <button
              type="button"
              onClick={() => setChannel('email')}
              className={`pb-2.5 text-xs sm:text-sm font-medium border-b-2 flex items-center gap-2 cursor-pointer transition-colors ${
                channel === 'email'
                  ? 'border-[#4F46E5] text-[#1C1917]'
                  : 'border-transparent text-[#78716C] hover:text-[#1C1917]'
              }`}
            >
              <Mail className="w-4 h-4" strokeWidth={1.5} />
              Email
            </button>
            <button
              type="button"
              onClick={() => setChannel('sms')}
              className={`pb-2.5 text-xs sm:text-sm font-medium border-b-2 flex items-center gap-2 cursor-pointer transition-colors ${
                channel === 'sms'
                  ? 'border-[#4F46E5] text-[#1C1917]'
                  : 'border-transparent text-[#78716C] hover:text-[#1C1917]'
              }`}
            >
              <MessageSquare className="w-4 h-4" strokeWidth={1.5} />
              SMS
            </button>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-5">
          {/* Template Switch */}
          <div className="pt-1">
            <Switch
              id="bulk-toggle-template"
              label="Use a pre-built template"
              description="Populate parameters dynamically per row from your CSV."
              checked={useTemplate}
              onChange={setUseTemplate}
            />
          </div>

          {/* Template dropdown */}
          {useTemplate && (
            <div className="p-4 rounded-[6px] bg-[#FAFAF9] border border-[#E7E5E4] space-y-2">
              <Select
                id="bulk-template-select"
                label="Choose Template"
                value={selectedTemplateId}
                onChange={(e) => setSelectedTemplateId(e.target.value)}
              >
                <option value="">-- Choose a template --</option>
                {channelTemplates.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name} (Variables:{' '}
                    {t.variables?.length ? t.variables.join(', ') : 'none'})
                  </option>
                ))}
              </Select>
              {selectedTemplate && (
                <div className="pt-1 text-xs text-[#78716C]">
                  <span className="font-semibold text-[#1C1917]">
                    Required CSV columns:
                  </span>{' '}
                  <code className="text-[#4F46E5] font-mono">
                    recipient
                    {templateVariables.length
                      ? `, ${templateVariables.join(', ')}`
                      : ''}
                  </code>
                </div>
              )}
            </div>
          )}

          {/* Shared Content */}
          {!useTemplate && channel === 'email' && (
            <Input
              id="bulk-subject"
              label="Subject *"
              type="text"
              required
              maxLength={255}
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              placeholder="Product Announcement"
            />
          )}

          {!useTemplate && (
            <div className="space-y-1.5">
              <div className="flex justify-between items-center">
                <label
                  htmlFor="bulk-body"
                  className="block text-xs font-medium text-[#1C1917]"
                >
                  {channel === 'email' ? 'Body Message *' : 'SMS Message *'}
                </label>
                {channel === 'sms' && (
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
                id="bulk-body"
                required
                rows={4}
                maxLength={channel === 'sms' ? 1600 : undefined}
                value={body}
                onChange={(e) => setBody(e.target.value)}
                placeholder="Message markdown or text..."
                className="w-full text-xs px-3 py-2 rounded-[6px] bg-white border border-[#E7E5E4] text-[#1C1917] placeholder:text-[#A8A29E] focus:outline-none focus:ring-2 focus:ring-[#4F46E5]/20 focus:border-[#4F46E5]"
              />
            </div>
          )}

          {/* Recipients Section */}
          <div className="space-y-3 pt-3 border-t border-[#E7E5E4]">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <label className="block text-xs font-medium text-[#1C1917]">
                Recipients List (Max 200 total)
              </label>
              <label className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-[6px] bg-white hover:bg-[#F5F5F4] border border-[#E7E5E4] text-xs font-medium text-[#1C1917] cursor-pointer shadow-xs transition-colors">
                <Upload className="w-3.5 h-3.5 text-[#78716C]" strokeWidth={1.5} />
                <span>Upload CSV</span>
                <input
                  type="file"
                  accept=".csv,text/csv"
                  onChange={handleFileUpload}
                  className="hidden"
                />
              </label>
            </div>

            {fileName && (
              <p className="text-xs text-[#4F46E5]">Uploaded file: {fileName}</p>
            )}

            <textarea
              rows={6}
              value={rawText}
              onChange={(e) => setRawText(e.target.value)}
              placeholder={
                useTemplate
                  ? `recipient,${templateVariables.join(',') || 'var1'}\nalex@example.com,Alex\nsarah@example.com,Sarah`
                  : `alex@example.com\nsarah@example.com`
              }
              className="w-full font-mono text-xs px-3 py-2 rounded-[6px] bg-white border border-[#E7E5E4] text-[#1C1917] placeholder:text-[#A8A29E] focus:outline-none focus:ring-2 focus:ring-[#4F46E5]/20 focus:border-[#4F46E5]"
            />
          </div>

          {/* Counts & Preview */}
          {rawText.trim() && (
            <div className="space-y-3 p-4 rounded-[6px] bg-[#FAFAF9] border border-[#E7E5E4]">
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
                <div className="p-2.5 rounded-[4px] bg-white border border-[#E7E5E4]">
                  <span className="text-[#78716C] block text-[11px]">Parsed Rows</span>
                  <span
                    className={`text-sm font-semibold ${
                      parsed.totalParsed > 200 ? 'text-[#B91C1C]' : 'text-[#1C1917]'
                    }`}
                  >
                    {parsed.totalParsed}
                  </span>
                </div>
                <div className="p-2.5 rounded-[4px] bg-white border border-[#E7E5E4]">
                  <span className="text-[#78716C] block text-[11px]">Valid</span>
                  <span className="text-sm font-semibold text-[#15803D]">
                    {parsed.validRows.length}
                  </span>
                </div>
                <div className="p-2.5 rounded-[4px] bg-white border border-[#E7E5E4]">
                  <span className="text-[#78716C] block text-[11px]">Duplicates</span>
                  <span className="text-sm font-semibold text-[#A16207]">
                    {parsed.duplicateCount}
                  </span>
                </div>
                <div className="p-2.5 rounded-[4px] bg-white border border-[#E7E5E4]">
                  <span className="text-[#78716C] block text-[11px]">Invalid Format</span>
                  <span
                    className={`text-sm font-semibold ${
                      parsed.invalidCount > 0 ? 'text-[#B91C1C]' : 'text-[#1C1917]'
                    }`}
                  >
                    {parsed.invalidCount}
                  </span>
                </div>
              </div>

              {parsed.errors.length > 0 && (
                <div className="space-y-1 pt-1">
                  {parsed.errors.map((err, i) => (
                    <p key={i} className="text-xs text-[#B91C1C] flex items-center gap-1">
                      <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                      {err}
                    </p>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Options: Priority & Category */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-3 border-t border-[#E7E5E4]">
            <Select
              id="bulk-priority"
              label="Priority Level"
              value={priority}
              onChange={(e) => setPriority(e.target.value)}
            >
              <option value="high">High</option>
              <option value="normal">Normal</option>
              <option value="low">Low</option>
            </Select>

            <div className="space-y-1.5">
              <label className="block text-xs font-medium text-[#1C1917]">
                Category
              </label>
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
            </div>
          </div>

          {/* Send with email provider choice */}
          {channel === 'email' && (
            <div className="pt-3 border-t border-[#E7E5E4]">
              <Select
                id="bulk-send-with-provider"
                label="Send with"
                value={emailProvider}
                onChange={(e) => setEmailProvider(e.target.value)}
                helper="Choose a specific email provider or let workspace defaults decide."
              >
                <option value="">Workspace default</option>
                {['brevo', 'smtp'].map((p) => {
                  const isAvailable = availableEmailProviders.includes(p);
                  return (
                    <option key={p} value={p} disabled={!isAvailable}>
                      {p === 'brevo' ? 'Brevo' : 'SMTP'}{!isAvailable ? ' (not configured)' : ''}
                    </option>
                  );
                })}
              </Select>
            </div>
          )}

          {/* Scheduling Switch */}
          <div className="space-y-3 pt-3 border-t border-[#E7E5E4]">
            <Switch
              id="bulk-toggle-schedule"
              label="Schedule bulk delivery for later"
              checked={isScheduled}
              onChange={setIsScheduled}
            />
            {isScheduled && (
              <div className="pl-12 max-w-xs">
                <Input
                  id="bulk-schedule-time"
                  type="datetime-local"
                  value={scheduledAtRaw}
                  onChange={(e) => setScheduledAtRaw(e.target.value)}
                />
              </div>
            )}
          </div>

          {/* Submit */}
          <div className="pt-4 border-t border-[#E7E5E4] flex justify-end">
            <Button
              type="submit"
              variant="primary"
              size="md"
              loading={loading}
              disabled={loading || isBlocked}
              icon={Send}
            >
              {loading
                ? 'Queuing batch…'
                : `Send to ${parsed.validRows.length} recipients`}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
