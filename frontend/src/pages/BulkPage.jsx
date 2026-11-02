import { useState, useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import { sendBulk, getBatchStatus, listTemplates } from '../lib/api';
import { useAuth } from '../lib/auth';
import { parseRecipientsData } from '../lib/csv';
import { describeError } from '../lib/errors';
import StatusBadge from '../components/StatusBadge';
import ErrorBanner from '../components/ErrorBanner';

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
  const [batchInfo, setBatchInfo] = useState(null); // { batch_id, queued, suppressed, ids }
  const [batchStatus, setBatchStatus] = useState(null); // { batch_id, total, counts_by_status }
  const pollTimerRef = useRef(null);

  // Fetch templates once on mount
  useEffect(() => {
    listTemplates({ limit: 200 })
      .then((res) => setAllTemplates(res.data || []))
      .catch(() => {});
  }, []);

  const channelTemplates = allTemplates.filter((t) => t.channel === channel);
  const selectedTemplate = channelTemplates.find((t) => t.id === selectedTemplateId);
  const templateVariables = selectedTemplate?.variables || [];

  // Reset selected template if channel changes
  useEffect(() => {
    setSelectedTemplateId('');
  }, [channel]);

  // Handle CSV file upload
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

  // Parse recipients
  const parsed = parseRecipientsData(rawText, {
    channel,
    hasTemplate: useTemplate,
    templateVariables,
  });

  // Validation
  let formError = null;
  if (useTemplate && !selectedTemplate) {
    formError = 'Please select a template.';
  } else if (!useTemplate && channel === 'email') {
    if (!subject.trim()) formError = 'Subject is required.';
    else if (!body.trim()) formError = 'Body is required.';
  } else if (!useTemplate && channel === 'sms') {
    if (!body.trim()) formError = 'Message is required.';
    else if (body.length > 1600) formError = 'Message cannot exceed 1600 characters.';
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

  const isBlocked = Boolean(formError) || parsed.errors.length > 0 || parsed.validRows.length === 0;

  // Poll batch status
  useEffect(() => {
    if (!batchInfo?.batch_id) return;

    async function poll() {
      try {
        const status = await getBatchStatus(batchInfo.batch_id);
        setBatchStatus(status);

        // Check if all items finished
        const counts = status.counts_by_status || {};
        const activeStatuses = ['pending', 'processing', 'retrying', 'scheduled'];
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
      // Clear inputs
      setRawText('');
      setFileName('');
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
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">Bulk Notifications</h1>
      </div>

      {error && (
        <div className="flex items-center justify-between gap-3 px-4 py-3 rounded-lg bg-red-900/30 border border-red-700 text-red-300 text-sm">
          <span>⚠ {typeof error === 'string' ? error : error?.message || String(error)}</span>
          {errorAction && (
            <Link
              to={errorAction.to}
              className="shrink-0 px-3 py-1 rounded bg-red-800 hover:bg-red-700 text-red-100 text-xs font-medium"
            >
              {errorAction.label}
            </Link>
          )}
        </div>
      )}

      {/* Batch Summary Card */}
      {batchInfo && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 shadow-xl space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-gray-800 pb-4">
            <div>
              <h2 className="text-lg font-semibold text-emerald-400">Batch Queued Successfully!</h2>
              <p className="text-xs font-mono text-gray-400 mt-0.5">Batch ID: {batchInfo.batch_id}</p>
            </div>
            <Link
              to={`/notifications?batch_id=${encodeURIComponent(batchInfo.batch_id)}`}
              className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-medium transition-colors"
            >
              View Notifications &rarr;
            </Link>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 text-sm">
            <div className="p-3 bg-gray-950 rounded-lg border border-gray-800">
              <span className="text-xs text-gray-500 block">Queued</span>
              <span className="text-xl font-bold text-emerald-400">{batchInfo.queued}</span>
            </div>
            <div className="p-3 bg-gray-950 rounded-lg border border-gray-800">
              <span className="text-xs text-gray-500 block">Suppressed</span>
              <span className="text-xl font-bold text-amber-400">{batchInfo.suppressed}</span>
            </div>
            <div className="p-3 bg-gray-950 rounded-lg border border-gray-800 col-span-2 sm:col-span-1">
              <span className="text-xs text-gray-500 block">Total In Batch</span>
              <span className="text-xl font-bold text-white">{batchStatus?.total ?? batchInfo.queued + batchInfo.suppressed}</span>
            </div>
          </div>

          {batchStatus?.counts_by_status && (
            <div className="space-y-2 pt-2">
              <p className="text-xs font-medium text-gray-400 uppercase tracking-wider">Live Status Breakdown</p>
              <div className="flex flex-wrap gap-2">
                {Object.entries(batchStatus.counts_by_status).map(([st, count]) => (
                  <div key={st} className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-gray-950 border border-gray-800 text-xs">
                    <StatusBadge status={st} />
                    <span className="font-semibold text-gray-200">{count}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Bulk Form */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 shadow-xl space-y-6">
        {/* Channel Selector */}
        <div className="flex gap-2 border-b border-gray-800 pb-4">
          <button
            type="button"
            onClick={() => setChannel('email')}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              channel === 'email' ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-300 hover:bg-gray-700'
            }`}
          >
            Email
          </button>
          <button
            type="button"
            onClick={() => setChannel('sms')}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              channel === 'sms' ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-300 hover:bg-gray-700'
            }`}
          >
            SMS
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-6">
          {/* Template toggle */}
          <div>
            <label className="flex items-center gap-2 cursor-pointer text-sm text-gray-300">
              <input
                type="checkbox"
                checked={useTemplate}
                onChange={(e) => setUseTemplate(e.target.checked)}
                className="rounded bg-gray-800 border-gray-700 text-blue-600 focus:ring-0"
              />
              Use a template for bulk sending
            </label>
          </div>

          {/* Template Selection */}
          {useTemplate && (
            <div className="p-4 rounded-xl bg-gray-950/60 border border-gray-800 space-y-2">
              <label className="block text-sm font-medium text-gray-300">Choose Template</label>
              {channelTemplates.length === 0 ? (
                <p className="text-xs text-gray-500">No {channel.toUpperCase()} templates available.</p>
              ) : (
                <select
                  value={selectedTemplateId}
                  onChange={(e) => setSelectedTemplateId(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 text-white text-sm"
                >
                  <option value="">-- Choose a template --</option>
                  {channelTemplates.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name} (Variables: {t.variables?.length ? t.variables.join(', ') : 'none'})
                    </option>
                  ))}
                </select>
              )}
              {selectedTemplate && (
                <div className="pt-2 text-xs text-gray-400">
                  <p className="font-semibold text-gray-300">Required CSV Columns:</p>
                  <p className="font-mono mt-0.5 text-blue-400">
                    recipient{templateVariables.length ? `, ${templateVariables.join(', ')}` : ''}
                  </p>
                </div>
              )}
            </div>
          )}

          {/* Shared Content (when NOT using template) */}
          {!useTemplate && channel === 'email' && (
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1" htmlFor="bulk-subject">
                Subject
              </label>
              <input
                id="bulk-subject"
                type="text"
                required
                maxLength={255}
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
                placeholder="Shared email subject"
                className="w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 text-sm"
              />
            </div>
          )}

          {!useTemplate && (
            <div>
              <div className="flex justify-between items-center mb-1">
                <label className="block text-sm font-medium text-gray-300" htmlFor="bulk-body">
                  {channel === 'email' ? 'Body' : 'Message'}
                </label>
                {channel === 'sms' && (
                  <span className={`text-xs ${body.length > 1600 ? 'text-red-400' : 'text-gray-400'}`}>
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
                placeholder={
                  channel === 'email'
                    ? 'Shared email body content...'
                    : 'Shared SMS message content...'
                }
                className="w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 text-sm"
              />
            </div>
          )}

          {/* Recipients Section */}
          <div className="space-y-3 pt-2 border-t border-gray-800">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <label className="block text-sm font-medium text-gray-300">
                Recipients (Max 200 total)
              </label>
              <label className="px-3 py-1.5 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-300 text-xs font-medium cursor-pointer border border-gray-700">
                <span>📁 Upload CSV</span>
                <input
                  type="file"
                  accept=".csv,text/csv"
                  onChange={handleFileUpload}
                  className="hidden"
                />
              </label>
            </div>
            {fileName && (
              <p className="text-xs text-blue-400">Uploaded file: {fileName}</p>
            )}
            <textarea
              rows={6}
              value={rawText}
              onChange={(e) => setRawText(e.target.value)}
              placeholder={
                useTemplate
                  ? `recipient,${templateVariables.join(',') || 'var1'}\nuser1@example.com,John\nuser2@example.com,Sarah`
                  : `user1@example.com\nuser2@example.com`
              }
              className="w-full font-mono px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 text-xs"
            />
          </div>

          {/* Counts & Preview */}
          {rawText.trim() && (
            <div className="space-y-3 p-4 rounded-xl bg-gray-950 border border-gray-800">
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                <div className="p-2.5 rounded-lg bg-gray-900 border border-gray-800">
                  <span className="text-gray-500 block">Parsed Rows</span>
                  <span className={`text-base font-bold ${parsed.totalParsed > 200 ? 'text-red-400' : 'text-white'}`}>
                    {parsed.totalParsed}
                  </span>
                </div>
                <div className="p-2.5 rounded-lg bg-gray-900 border border-gray-800">
                  <span className="text-gray-500 block">Duplicates (Dropped)</span>
                  <span className="text-base font-bold text-amber-400">{parsed.duplicateCount}</span>
                </div>
                <div className="p-2.5 rounded-lg bg-gray-900 border border-gray-800">
                  <span className="text-gray-500 block">Invalid Format</span>
                  <span className={`text-base font-bold ${parsed.invalidCount > 0 ? 'text-red-400' : 'text-white'}`}>
                    {parsed.invalidCount}
                  </span>
                </div>
                <div className="p-2.5 rounded-lg bg-gray-900 border border-gray-800">
                  <span className="text-gray-500 block">Missing Variables</span>
                  <span className={`text-base font-bold ${parsed.missingVarCount > 0 ? 'text-red-400' : 'text-white'}`}>
                    {parsed.missingVarCount}
                  </span>
                </div>
              </div>

              {/* Blocking Errors in Red */}
              {parsed.errors.length > 0 && (
                <div className="space-y-1">
                  {parsed.errors.map((err, i) => (
                    <p key={i} className="text-xs text-red-400 font-medium">
                      ✕ {err}
                    </p>
                  ))}
                </div>
              )}

              {/* Preview Table: First 20 rows */}
              {parsed.rows.length > 0 && (
                <div className="overflow-x-auto rounded-lg border border-gray-800 max-h-60 overflow-y-auto">
                  <table className="w-full text-xs text-left">
                    <thead className="bg-gray-900 text-gray-400 sticky top-0">
                      <tr>
                        <th className="px-3 py-2">#</th>
                        <th className="px-3 py-2">Recipient</th>
                        <th className="px-3 py-2">Status</th>
                        {useTemplate && <th className="px-3 py-2">Variables</th>}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-800 font-mono">
                      {parsed.rows.slice(0, 20).map((r) => (
                        <tr key={r.index} className="bg-gray-950 hover:bg-gray-900/50">
                          <td className="px-3 py-1.5 text-gray-500">{r.index}</td>
                          <td className="px-3 py-1.5 truncate max-w-xs">{r.recipient || '<empty>'}</td>
                          <td className="px-3 py-1.5">
                            {!r.isValid ? (
                              <span className="text-red-400">Invalid</span>
                            ) : r.isDuplicate ? (
                              <span className="text-amber-400">Duplicate</span>
                            ) : r.missingVars?.length > 0 ? (
                              <span className="text-red-400">Missing vars</span>
                            ) : (
                              <span className="text-emerald-400">Valid</span>
                            )}
                          </td>
                          {useTemplate && (
                            <td className="px-3 py-1.5 text-gray-400 truncate max-w-xs">
                              {r.missingVars?.length > 0 ? (
                                <span className="text-red-400">Missing: {r.missingVars.join(', ')}</span>
                              ) : (
                                JSON.stringify(r.variables || {})
                              )}
                            </td>
                          )}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              {parsed.rows.length > 20 && (
                <p className="text-xs text-gray-500 text-right">Showing first 20 of {parsed.rows.length} rows</p>
              )}
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
          </div>

          {/* Scheduling */}
          <div className="space-y-2 pt-2 border-t border-gray-800">
            <label className="flex items-center gap-2 cursor-pointer text-sm text-gray-300">
              <input
                type="checkbox"
                checked={isScheduled}
                onChange={(e) => setIsScheduled(e.target.checked)}
                className="rounded bg-gray-800 border-gray-700 text-blue-600 focus:ring-0"
              />
              Schedule bulk delivery
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

          {/* Submit */}
          <div className="pt-4">
            <button
              type="submit"
              disabled={loading || isBlocked}
              className="w-full sm:w-auto px-6 py-2.5 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm font-medium transition-colors"
            >
              {loading ? 'Queuing Batch...' : `Send Bulk (${parsed.validRows.length} valid recipients)`}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

