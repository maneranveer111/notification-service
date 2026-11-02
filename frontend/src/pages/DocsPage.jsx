import { useState } from 'react';
import { Link } from 'react-router-dom';
import { absoluteApiBase } from '../lib/api';

// ---------------------------------------------------------------------------
// Shared helpers
// ---------------------------------------------------------------------------
function MethodBadge({ method }) {
  const colors = {
    GET: 'bg-blue-700 text-blue-100',
    POST: 'bg-green-700 text-green-100',
    DELETE: 'bg-red-700 text-red-100',
    PUT: 'bg-yellow-700 text-yellow-100',
    PATCH: 'bg-orange-700 text-orange-100',
  };
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-xs font-bold uppercase mr-2 ${colors[method] || 'bg-gray-700 text-gray-100'}`}>
      {method}
    </span>
  );
}

function SchemaTable({ rows }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-gray-800 mt-3">
      <table className="w-full text-xs">
        <thead>
          <tr className="bg-gray-800 text-gray-400">
            <th className="px-3 py-2 text-left font-medium">Field</th>
            <th className="px-3 py-2 text-left font-medium">Type</th>
            <th className="px-3 py-2 text-left font-medium">Required</th>
            <th className="px-3 py-2 text-left font-medium">Description</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={r.field} className={i % 2 === 0 ? 'bg-gray-900' : 'bg-gray-950'}>
              <td className="px-3 py-2 font-mono text-blue-300">{r.field}</td>
              <td className="px-3 py-2 text-gray-400">{r.type}</td>
              <td className="px-3 py-2 text-gray-400">{r.required ? 'Yes' : 'No'}</td>
              <td className="px-3 py-2 text-gray-300">{r.description}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CodeBlock({ code, language = 'bash' }) {
  const [copied, setCopied] = useState(false);
  function handleCopy() {
    navigator.clipboard.writeText(code).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }
  return (
    <div className="relative mt-3">
      <pre className={`bg-gray-900 border border-gray-800 rounded-lg p-4 text-xs overflow-x-auto whitespace-pre-wrap break-all leading-relaxed ${language === 'bash' ? 'text-green-300' : 'text-gray-300'}`}>
        {code}
      </pre>
      <button
        type="button"
        onClick={handleCopy}
        className="absolute top-2 right-2 px-2 py-1 rounded bg-gray-700 hover:bg-gray-600 text-gray-200 text-xs transition-colors"
      >
        {copied ? 'Copied!' : 'Copy'}
      </button>
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
      description: 'Obtain a bearer token by exchanging email and password credentials. Include the token as an Authorization header on all subsequent requests.',
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
      description: 'Send a transactional email. Supports plain-text body or a template reference with Jinja2 variables. Include an Idempotency-Key header to prevent duplicate sends.',
      schema: [
        { field: 'recipient', type: 'string', required: true, description: 'Recipient email address' },
        { field: 'subject', type: 'string', required: true, description: 'Email subject line' },
        { field: 'body', type: 'string', required: false, description: 'Plain-text or HTML body (mutually exclusive with template_id)' },
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
      description: 'Send an SMS message via a configured SMS provider (e.g. Twilio). The workspace must have an SMS provider credential configured.',
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
      description: 'Dispatch an HTTP POST to a target URL with a JSON payload. Notify handles retries with exponential backoff on non-2xx responses.',
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
      description: 'Submit multiple notifications in a single request. Returns a batch ID you can poll for status. All items in a batch share the same channel.',
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
      description: 'Create a reusable message template with Jinja2 variable syntax. Reference the template by ID when sending a notification.',
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
      description: 'Add a recipient to the suppression list so they will not receive notifications of the specified channel. Use GET /suppressions to list active suppressions.',
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
    <div className="min-h-screen bg-gray-950 text-white">
      {/* Top bar */}
      <header className="border-b border-gray-800 bg-gray-950/80 backdrop-blur sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 py-4 flex items-center justify-between">
          <Link to="/" className="font-bold text-blue-400 text-xl">Notify</Link>
          <nav className="flex items-center gap-4">
            <Link to="/login" className="text-sm text-gray-300 hover:text-white transition-colors">Log in</Link>
            <Link to="/signup" className="text-sm px-4 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-medium transition-colors">
              Sign up
            </Link>
          </nav>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 py-10 flex gap-8">
        {/* Sidebar */}
        <aside className="hidden md:block w-52 shrink-0">
          <div className="sticky top-24 space-y-1">
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3 px-3">
              API Reference
            </p>
            {SIDEBAR_LINKS.map((link) => (
              <a
                key={link.id}
                href={`#${link.id}`}
                className="block px-3 py-2 rounded-lg text-sm text-gray-400 hover:text-white hover:bg-gray-800 transition-colors"
              >
                {link.title}
              </a>
            ))}
          </div>
        </aside>

        {/* Content */}
        <main className="flex-1 min-w-0 space-y-16">
          <div>
            <h1 className="text-3xl font-bold text-white mb-2">API Reference</h1>
            <p className="text-gray-400 text-sm">
              All endpoints require a{' '}
              <code className="bg-gray-800 text-blue-300 px-1.5 py-0.5 rounded text-xs">Bearer</code>{' '}
              token in the{' '}
              <code className="bg-gray-800 text-blue-300 px-1.5 py-0.5 rounded text-xs">Authorization</code>{' '}
              header, except the login endpoint. Base URL:{' '}
              <code className="bg-gray-800 text-green-300 px-1.5 py-0.5 rounded text-xs">{apiBase}</code>.
            </p>
          </div>

          {SECTIONS.map((section) => (
            <section key={section.id} id={section.id} className="scroll-mt-24">
              <div className="flex items-center gap-2 mb-2">
                <MethodBadge method={section.method} />
                <code className="text-blue-300 text-sm font-mono">{section.path}</code>
              </div>
              <h2 className="text-xl font-bold text-white mb-2">{section.title}</h2>
              <p className="text-gray-400 text-sm leading-relaxed mb-4">{section.description}</p>

              <h3 className="text-sm font-semibold text-gray-300 mb-1">Request body</h3>
              <SchemaTable rows={section.schema} />

              <h3 className="text-sm font-semibold text-gray-300 mt-5 mb-1">Example request</h3>
              <CodeBlock code={section.curl} language="bash" />

              <h3 className="text-sm font-semibold text-gray-300 mt-5 mb-1">Example response</h3>
              <CodeBlock code={section.response} language="json" />
            </section>
          ))}
        </main>
      </div>
    </div>
  );
}
