import { Link } from 'react-router-dom';
import { absoluteApiBase } from '../lib/api';
import CodeBlock from '../components/ui/CodeBlock';
import Card from '../components/ui/Card';

// ---------------------------------------------------------------------------
// Shared helpers
// ---------------------------------------------------------------------------
function MethodBadge({ method }) {
  const colors = {
    GET: 'bg-[#EFF6FF] text-[#1D4ED8] border-[#BFDBFE]',
    POST: 'bg-[#ECFDF5] text-[#047857] border-[#A7F3D0]',
    DELETE: 'bg-[#FEF2F2] text-[#B91C1C] border-[#FECACA]',
    PUT: 'bg-[#FFFBEB] text-[#B45309] border-[#FDE68A]',
    PATCH: 'bg-[#FFFBEB] text-[#B45309] border-[#FDE68A]',
  };
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-mono font-bold uppercase border ${
        colors[method] || 'bg-[#F5F5F4] text-[#44403C] border-[#E7E5E4]'
      }`}
    >
      {method}
    </span>
  );
}

function SchemaTable({ rows }) {
  return (
    <div className="overflow-x-auto rounded-[6px] border border-[#E7E5E4] mt-2.5">
      <table className="w-full text-xs">
        <thead>
          <tr className="bg-[#F5F5F4] text-[#78716C] border-b border-[#E7E5E4]">
            <th className="px-3.5 py-2 text-left font-semibold text-[11px] uppercase tracking-wider">Field</th>
            <th className="px-3.5 py-2 text-left font-semibold text-[11px] uppercase tracking-wider">Type</th>
            <th className="px-3.5 py-2 text-left font-semibold text-[11px] uppercase tracking-wider">Required</th>
            <th className="px-3.5 py-2 text-left font-semibold text-[11px] uppercase tracking-wider">Description</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-[#E7E5E4] bg-white">
          {rows.map((r) => (
            <tr key={r.field} className="hover:bg-[#FAFAF9] transition-colors">
              <td className="px-3.5 py-2 font-mono text-[12px] text-[#4F46E5] font-medium">{r.field}</td>
              <td className="px-3.5 py-2 font-mono text-[11px] text-[#78716C]">{r.type}</td>
              <td className="px-3.5 py-2">
                {r.required ? (
                  <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-[#FEF2F2] text-[#B91C1C]">
                    Required
                  </span>
                ) : (
                  <span className="text-[11px] text-[#A8A29E]">Optional</span>
                )}
              </td>
              <td className="px-3.5 py-2 text-[#44403C] text-[12px]">{r.description}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Section data — built inside the component so apiBase is always current
// ---------------------------------------------------------------------------
function buildSections(apiBase) {
  return [
    {
      id: 'auth',
      title: 'Authentication',
      method: 'POST',
      path: '/auth/login',
      description:
        'Obtain a bearer token by exchanging email and password credentials. Include the token as an Authorization header on all subsequent requests.',
      schema: [
        { field: 'email', type: 'string', required: true, description: 'User email address' },
        { field: 'password', type: 'string', required: true, description: 'User password' },
      ],
      curl: `curl -X POST ${apiBase}/auth/login \\
  -H "Content-Type: application/json" \\
  -d '{"email":"user@example.com","password":"secret"}'`,
      response: `{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "user": { "id": "usr_1", "email": "user@example.com" },
  "workspace": { "id": "ws_1", "name": "My Workspace", "role": "admin" }
}`,
    },
    {
      id: 'email',
      title: 'Send Email',
      method: 'POST',
      path: '/notifications/email',
      description:
        'Send a transactional email. Supports plain-text body or a template reference with Jinja2 variables. Include an Idempotency-Key header to prevent duplicate sends.',
      schema: [
        { field: 'recipient', type: 'string', required: true, description: 'Recipient email address' },
        { field: 'subject', type: 'string', required: true, description: 'Email subject line' },
        {
          field: 'body',
          type: 'string',
          required: false,
          description: 'Plain-text or HTML body (mutually exclusive with template_id)',
        },
        { field: 'template_id', type: 'string', required: false, description: 'Template ID to render (mutually exclusive with body)' },
        { field: 'template_vars', type: 'object', required: false, description: 'Variables passed to the Jinja2 template' },
        { field: 'scheduled_at', type: 'string (ISO 8601)', required: false, description: 'Schedule delivery for a future time' },
      ],
      curl: `curl -X POST ${apiBase}/notifications/email \\
  -H "Authorization: Bearer YOUR_API_KEY" \\
  -H "Content-Type: application/json" \\
  -H "Idempotency-Key: unique-key-123" \\
  -d '{
    "recipient": "user@example.com",
    "subject": "Welcome to Notify",
    "body": "Thanks for signing up!"
  }'`,
      response: `{
  "id": "notif_abc123",
  "status": "pending",
  "channel": "email",
  "recipient": "user@example.com",
  "created_at": "2024-01-15T10:30:00Z"
}`,
    },
    {
      id: 'sms',
      title: 'Send SMS',
      method: 'POST',
      path: '/notifications/sms',
      description:
        'Send an SMS message via a configured SMS provider (e.g. Twilio). The workspace must have an SMS provider credential configured.',
      schema: [
        { field: 'recipient', type: 'string', required: true, description: 'Recipient phone number in E.164 format (e.g. +15551234567)' },
        { field: 'body', type: 'string', required: false, description: 'Message text (mutually exclusive with template_id)' },
        { field: 'template_id', type: 'string', required: false, description: 'Template ID to render' },
        { field: 'template_vars', type: 'object', required: false, description: 'Variables passed to the template' },
      ],
      curl: `curl -X POST ${apiBase}/notifications/sms \\
  -H "Authorization: Bearer YOUR_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "recipient": "+15551234567",
    "body": "Your verification code is 123456"
  }'`,
      response: `{
  "id": "notif_def456",
  "status": "pending",
  "channel": "sms",
  "recipient": "+15551234567",
  "created_at": "2024-01-15T10:31:00Z"
}`,
    },
    {
      id: 'webhook',
      title: 'Send Webhook',
      method: 'POST',
      path: '/notifications/webhook',
      description:
        'Dispatch an HTTP POST to a target URL with a JSON payload. Notify handles retries with exponential backoff on non-2xx responses.',
      schema: [
        { field: 'recipient', type: 'string (URL)', required: true, description: 'Target URL to POST the webhook payload to' },
        { field: 'body', type: 'string or object', required: true, description: 'Webhook payload (sent as JSON)' },
        { field: 'template_id', type: 'string', required: false, description: 'Template ID to render the payload' },
        { field: 'template_vars', type: 'object', required: false, description: 'Variables passed to the template' },
      ],
      curl: `curl -X POST ${apiBase}/notifications/webhook \\
  -H "Authorization: Bearer YOUR_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "recipient": "https://example.com/hooks/notify",
    "body": {"event":"user.created","user_id":"u_99"}
  }'`,
      response: `{
  "id": "notif_ghi789",
  "status": "pending",
  "channel": "webhook",
  "recipient": "https://example.com/hooks/notify",
  "created_at": "2024-01-15T10:32:00Z"
}`,
    },
    {
      id: 'bulk',
      title: 'Bulk Send',
      method: 'POST',
      path: '/notifications/bulk',
      description:
        'Submit multiple notifications in a single request. Returns a batch ID you can poll for status. All items in a batch share the same channel.',
      schema: [
        { field: 'channel', type: 'string', required: true, description: 'Channel for all items: email, sms, or webhook' },
        { field: 'notifications', type: 'array', required: true, description: 'Array of notification objects (same fields as single-send)' },
      ],
      curl: `curl -X POST ${apiBase}/notifications/bulk \\
  -H "Authorization: Bearer YOUR_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "channel": "email",
    "notifications": [
      {"recipient":"a@example.com","subject":"Hello","body":"Hi A"},
      {"recipient":"b@example.com","subject":"Hello","body":"Hi B"}
    ]
  }'`,
      response: `{
  "batch_id": "batch_xyz001",
  "accepted": 2,
  "rejected": 0,
  "status": "queued"
}`,
    },
    {
      id: 'templates',
      title: 'Templates',
      method: 'POST',
      path: '/templates',
      description:
        'Create a reusable message template with Jinja2 variable syntax. Reference the template by ID when sending a notification.',
      schema: [
        { field: 'name', type: 'string', required: true, description: 'Human-readable template name' },
        { field: 'channel', type: 'string', required: true, description: 'Channel this template is for: email, sms, or webhook' },
        { field: 'subject', type: 'string', required: false, description: 'Subject line (email only); supports Jinja2 variables' },
        { field: 'body', type: 'string', required: true, description: 'Template body with Jinja2 syntax, e.g. Hello {{ name }}' },
      ],
      curl: `curl -X POST ${apiBase}/templates \\
  -H "Authorization: Bearer YOUR_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "name": "welcome-email",
    "channel": "email",
    "subject": "Welcome, {{ name }}!",
    "body": "Hi {{ name }}, thanks for joining."
  }'`,
      response: `{
  "id": "tmpl_w3lc0m3",
  "name": "welcome-email",
  "channel": "email",
  "created_at": "2024-01-15T09:00:00Z"
}`,
    },
    {
      id: 'suppressions',
      title: 'Suppressions',
      method: 'POST',
      path: '/suppressions',
      description:
        'Add a recipient to the suppression list so they will not receive notifications of the specified channel. Use GET /suppressions to list active suppressions.',
      schema: [
        { field: 'recipient', type: 'string', required: true, description: 'Email address or phone number to suppress' },
        { field: 'channel', type: 'string', required: true, description: 'Channel to suppress: email or sms' },
        { field: 'reason', type: 'string', required: false, description: 'Optional reason for suppression: opt_out or bounce' },
      ],
      curl: `curl -X POST ${apiBase}/suppressions \\
  -H "Authorization: Bearer YOUR_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "recipient": "user@example.com",
    "channel": "email",
    "reason": "opt_out"
  }'`,
      response: `{
  "id": "sup_001",
  "recipient": "user@example.com",
  "channel": "email",
  "reason": "opt_out",
  "created_at": "2024-01-15T11:00:00Z"
}`,
    },
  ];
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------
export default function DocsPage() {
  const apiBase = absoluteApiBase();
  const SECTIONS = buildSections(apiBase);
  const SIDEBAR_LINKS = SECTIONS.map((s) => ({ id: s.id, title: s.title }));

  return (
    <div className="min-h-screen bg-[#FAFAF9] text-[#1C1917] font-sans antialiased">
      {/* Top bar */}
      <header className="border-b border-[#E7E5E4] bg-white/90 backdrop-blur sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link to="/" className="flex items-center gap-2 font-semibold text-[15px] text-[#1C1917] tracking-tight">
              <span className="w-6 h-6 rounded-[5px] bg-[#4F46E5] text-white flex items-center justify-center font-bold text-[13px] shadow-sm">
                N
              </span>
              <span>Notify</span>
            </Link>
            <span className="text-[11px] font-mono px-1.5 py-0.5 rounded bg-[#F5F5F4] text-[#78716C] border border-[#E7E5E4]">
              v1.0
            </span>
          </div>

          <nav className="flex items-center gap-3">
            <Link
              to="/login"
              className="text-xs font-medium text-[#78716C] hover:text-[#1C1917] px-3 py-1.5 rounded-[6px] hover:bg-[#F5F5F4] transition-colors"
            >
              Log in
            </Link>
            <Link
              to="/signup"
              className="text-xs font-medium px-3.5 py-1.5 rounded-[6px] bg-[#4F46E5] hover:bg-[#4338CA] text-white shadow-sm transition-colors"
            >
              Sign up
            </Link>
          </nav>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-6 py-10 flex gap-10">
        {/* Sidebar */}
        <aside className="hidden md:block w-52 shrink-0">
          <div className="sticky top-24 space-y-1">
            <p className="text-[11px] font-semibold text-[#78716C] uppercase tracking-wider mb-3 px-3">
              API Reference
            </p>
            {SIDEBAR_LINKS.map((link) => (
              <a
                key={link.id}
                href={`#${link.id}`}
                className="block px-3 py-1.5 rounded-[6px] text-xs font-medium text-[#78716C] hover:text-[#1C1917] hover:bg-white hover:border-[#E7E5E4] border border-transparent transition-colors"
              >
                {link.title}
              </a>
            ))}
          </div>
        </aside>

        {/* Content */}
        <main className="flex-1 min-w-0 space-y-12">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-[#1C1917] mb-2">API Reference</h1>
            <p className="text-sm text-[#78716C] leading-relaxed">
              All endpoints require a{' '}
              <code className="bg-[#F5F5F4] text-[#4F46E5] border border-[#E7E5E4] px-1.5 py-0.5 rounded text-xs font-mono">
                Bearer
              </code>{' '}
              token in the{' '}
              <code className="bg-[#F5F5F4] text-[#4F46E5] border border-[#E7E5E4] px-1.5 py-0.5 rounded text-xs font-mono">
                Authorization
              </code>{' '}
              header, except the login endpoint. Base URL:{' '}
              <code className="bg-[#F5F5F4] text-[#047857] border border-[#E7E5E4] px-1.5 py-0.5 rounded text-xs font-mono">
                {apiBase}
              </code>
              .
            </p>
          </div>

          {SECTIONS.map((section) => (
            <Card key={section.id} id={section.id} className="scroll-mt-24 p-6">
              <div className="flex items-center gap-2 mb-2">
                <MethodBadge method={section.method} />
                <code className="text-sm font-mono font-medium text-[#1C1917]">{section.path}</code>
              </div>
              <h2 className="text-lg font-semibold text-[#1C1917] mb-1.5">{section.title}</h2>
              <p className="text-xs text-[#78716C] leading-relaxed mb-4">{section.description}</p>

              <h3 className="text-xs font-semibold text-[#1C1917] uppercase tracking-wider mb-1">Request body</h3>
              <SchemaTable rows={section.schema} />

              <div className="mt-5">
                <h3 className="text-xs font-semibold text-[#1C1917] uppercase tracking-wider mb-2">
                  Example request
                </h3>
                <CodeBlock code={section.curl} language="bash" title="cURL" />
              </div>

              <div className="mt-5">
                <h3 className="text-xs font-semibold text-[#1C1917] uppercase tracking-wider mb-2">
                  Example response
                </h3>
                <CodeBlock code={section.response} language="json" title="Response JSON" />
              </div>
            </Card>
          ))}
        </main>
      </div>
    </div>
  );
}
