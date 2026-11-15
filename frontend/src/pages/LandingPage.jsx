import { useState } from 'react';
import { Link } from 'react-router-dom';
import { absoluteApiBase } from '../lib/api';
import {
  Layers,
  FileCode,
  ShieldCheck,
  Check,
  Copy,
  ArrowRight,
  ExternalLink,
} from 'lucide-react';
import Button from '../components/ui/Button';

const FEATURES = [
  {
    title: 'One API for every channel',
    icon: Layers,
    description:
      'Send via Email, SMS, Discord, and Webhooks through one coherent schema. Route traffic optimally and configure fallback providers per channel.',
  },
  {
    title: 'Templates with variables',
    icon: FileCode,
    description:
      'Build clean Jinja2 and HTML message templates with typed variable verification. Preview in real-time or update template copies without rebuilding services.',
  },
  {
    title: 'Idempotent & reliable',
    icon: ShieldCheck,
    description:
      'Native idempotency keys prevent duplicate transmissions during timeouts. Token bucket rate limiters protect upstream quotas and ensure high-delivery throughput.',
  },
];

const HOW_IT_WORKS = [
  {
    step: '1',
    label: 'SETUP',
    title: 'Connect a provider',
    description:
      'Add SMTP, Brevo, Twilio, or custom Webhooks in the Settings console. Configure fallback failover rates with zero code changes.',
  },
  {
    step: '2',
    label: 'DESIGN',
    title: 'Create a template',
    description:
      'Define reusable templates with Jinja2 variable interpolation. Validate required schema fields directly at compile time before dispatch.',
  },
  {
    step: '3',
    label: 'DISPATCH',
    title: 'Call the API',
    description:
      'Issue simple HTTP POST calls with idempotency keys. Notify handles exponential backoff retries, rate limiting, and delivery receipt tracking.',
  },
];

const METRICS = [
  { value: '< 25ms', label: 'Average dispatch latency' },
  { value: '0%', label: 'Per-message markup cost' },
  { value: 'PostgreSQL', label: 'Single storage dependency' },
  { value: 'MIT', label: 'Permissive open source' },
];

export default function LandingPage() {
  const [activeTab, setActiveTab] = useState('curl');
  const [copied, setCopied] = useState(false);
  const apiBase = absoluteApiBase();

  const codeSnippets = {
    curl: `curl -X POST ${apiBase}/notifications/email \\
  -H "Authorization: Bearer ntfy_live_k8s9d" \\
  -H "Content-Type: application/json" \\
  -H "Idempotency-Key: req_7781a" \\
  -d '{
    "channel": "email",
    "recipient": "elena.rostova@linear.app",
    "template": "tmpl_welcome_v2",
    "variables": {
      "name": "Elena Rostova",
      "company": "Acme Corp"
    }
  }'`,
    node: `import { Notify } from '@notify/sdk';

const notify = new Notify({ apiKey: 'ntfy_live_k8s9d' });

const response = await notify.send({
  channel: 'email',
  recipient: 'elena.rostova@linear.app',
  template: 'tmpl_welcome_v2',
  variables: {
    name: 'Elena Rostova',
    company: 'Acme Corp',
  },
});`,
    python: `from notify import NotifyClient

client = NotifyClient(api_key="ntfy_live_k8s9d")

response = client.send(
    channel="email",
    recipient="elena.rostova@linear.app",
    template="tmpl_welcome_v2",
    variables={
        "name": "Elena Rostova",
        "company": "Acme Corp"
    }
)`,
  };

  const responseJson = `{
  "id": "notif_01J8F2P3X4Y5Z6",
  "status": "delivered",
  "provider": "brevo-eu",
  "attempts": 1,
  "recipient": "elena.rostova@linear.app",
  "template_version": 2,
  "created_at": "2026-11-14T10:30:00Z"
}`;

  function handleCopy() {
    navigator.clipboard.writeText(codeSnippets[activeTab]).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  return (
    <div className="min-h-screen bg-[#FAFAF9] text-[#1C1917] font-sans antialiased selection:bg-[#EEF2FF] selection:text-[#4F46E5]">
      {/* Sticky top navigation bar */}
      <header className="sticky top-0 z-50 bg-white/90 backdrop-blur border-b border-[#E7E5E4]">
        <div className="max-w-6xl mx-auto px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-6">
            <Link to="/" className="flex items-center gap-2 font-semibold text-[15px] text-[#1C1917] tracking-tight">
              <span className="w-6 h-6 rounded-[5px] bg-[#4F46E5] text-white flex items-center justify-center font-bold text-[13px] shadow-sm">
                N
              </span>
              <span>Notify</span>
            </Link>
            <span className="text-[11px] font-mono px-1.5 py-0.5 rounded bg-[#F5F5F4] text-[#78716C] border border-[#E7E5E4] hidden sm:inline-block">
              v1.0
            </span>
          </div>

          <nav className="flex items-center gap-1 sm:gap-4 text-xs font-medium text-[#78716C]">
            <a href="#how-it-works" className="px-3 py-1.5 rounded-[6px] hover:text-[#1C1917] hover:bg-[#F5F5F4] transition-colors hidden md:block">
              How it works
            </a>
            <a href="#features" className="px-3 py-1.5 rounded-[6px] hover:text-[#1C1917] hover:bg-[#F5F5F4] transition-colors hidden md:block">
              Features
            </a>
            <Link to="/docs" className="px-3 py-1.5 rounded-[6px] hover:text-[#1C1917] hover:bg-[#F5F5F4] transition-colors">
              Docs
            </Link>
            <Link to="/login" className="px-3 py-1.5 rounded-[6px] hover:text-[#1C1917] hover:bg-[#F5F5F4] transition-colors">
              Log in
            </Link>
            <Link
              to="/signup"
              className="px-3.5 py-1.5 rounded-[6px] bg-[#4F46E5] hover:bg-[#4338CA] text-white shadow-sm transition-colors font-medium text-xs ml-1"
            >
              Get started free
            </Link>
          </nav>
        </div>
      </header>

      {/* Hero */}
      <section className="max-w-6xl mx-auto px-6 pt-20 pb-16 text-center">
        {/* Release Pill */}
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white border border-[#E7E5E4] text-[11px] font-medium text-[#78716C] shadow-sm mb-6">
          <span className="w-1.5 h-1.5 rounded-full bg-[#10B981]" />
          <span>Released under MIT License</span>
          <span className="text-[#D6D3D1]">•</span>
          <span className="font-mono text-[#44403C]">v1.0</span>
          <span className="text-[#D6D3D1]">•</span>
          <span>Self-hostable</span>
        </div>

        <h1 className="text-4xl sm:text-5xl md:text-6xl font-bold tracking-tight text-[#1C1917] max-w-4xl mx-auto leading-[1.1] mb-6">
          Notification infrastructure you can self-host
        </h1>

        <p className="text-base sm:text-lg text-[#78716C] max-w-2xl mx-auto leading-relaxed mb-8">
          Send email, SMS, and webhooks from a single unified API. Self-host it, own your customer data, and scale reliably without vendor lock-in.
        </p>

        <div className="flex flex-wrap items-center justify-center gap-3 mb-16">
          <Link to="/signup">
            <Button size="lg" icon={ArrowRight}>
              Get started free
            </Button>
          </Link>
          <Link to="/docs">
            <Button variant="secondary" size="lg">
              Read the docs
            </Button>
          </Link>
        </div>

        {/* Code Terminal Mockup */}
        <div className="max-w-4xl mx-auto rounded-[10px] bg-[#18181B] border border-[#27272A] shadow-xl overflow-hidden text-left">
          {/* Window Header */}
          <div className="flex items-center justify-between px-4 py-2.5 bg-[#27272A]/40 border-b border-[#27272A]">
            <div className="flex items-center gap-2">
              <div className="flex gap-1.5">
                <span className="w-2.5 h-2.5 rounded-full bg-[#3F3F46]" />
                <span className="w-2.5 h-2.5 rounded-full bg-[#3F3F46]" />
                <span className="w-2.5 h-2.5 rounded-full bg-[#3F3F46]" />
              </div>
              <span className="text-[11px] font-mono text-[#A1A1AA] ml-2 hidden sm:inline">
                POST /notifications/email
              </span>
            </div>

            <div className="flex items-center gap-3">
              <div className="flex items-center rounded-[5px] bg-[#27272A] p-0.5 text-[11px] font-mono">
                {['curl', 'node', 'python'].map((tab) => (
                  <button
                    key={tab}
                    type="button"
                    onClick={() => setActiveTab(tab)}
                    className={`px-2.5 py-0.5 rounded-[4px] capitalize transition-colors ${
                      activeTab === tab
                        ? 'bg-[#3F3F46] text-white'
                        : 'text-[#A1A1AA] hover:text-white'
                    }`}
                  >
                    {tab === 'curl' ? 'cURL' : tab === 'node' ? 'Node.js' : 'Python'}
                  </button>
                ))}
              </div>

              <button
                type="button"
                onClick={handleCopy}
                className="flex items-center gap-1.5 px-2 py-1 rounded-[4px] bg-[#27272A] hover:bg-[#3F3F46] text-[#D4D4D8] transition-colors text-[11px]"
              >
                {copied ? (
                  <>
                    <Check className="w-3.5 h-3.5 text-emerald-400" strokeWidth={2} />
                    <span className="text-emerald-400">Copied</span>
                  </>
                ) : (
                  <>
                    <Copy className="w-3.5 h-3.5" strokeWidth={1.5} />
                    <span>Copy</span>
                  </>
                )}
              </button>
            </div>
          </div>

          {/* Code Window Split */}
          <div className="grid grid-cols-1 md:grid-cols-12 divide-y md:divide-y-0 md:divide-x divide-[#27272A]">
            <div className="md:col-span-7 p-4 sm:p-5 font-mono text-xs leading-relaxed text-[#A1A1AA] overflow-x-auto">
              <pre className="text-[#38BDF8] whitespace-pre font-mono">
                {codeSnippets[activeTab]}
              </pre>
            </div>
            <div className="md:col-span-5 p-4 sm:p-5 font-mono text-xs leading-relaxed bg-[#141416] overflow-x-auto">
              <div className="text-[10px] uppercase font-bold tracking-wider text-[#71717A] mb-2 flex items-center gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                <span>200 OK — Delivery Response</span>
              </div>
              <pre className="text-emerald-400/90 whitespace-pre font-mono">
                {responseJson}
              </pre>
            </div>
          </div>
        </div>
      </section>

      {/* How it works */}
      <section id="how-it-works" className="max-w-6xl mx-auto px-6 py-20 border-t border-[#E7E5E4]">
        <div className="mb-12">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-[#4F46E5] mb-1">
            WORKFLOW
          </p>
          <h2 className="text-2xl sm:text-3xl font-bold tracking-tight text-[#1C1917]">
            How it works
          </h2>
          <p className="text-sm text-[#78716C] mt-1 max-w-xl">
            Three predictable building blocks to decouple customer communications from application business logic.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          {HOW_IT_WORKS.map((item) => (
            <div
              key={item.step}
              className="p-6 rounded-[8px] bg-white border border-[#E7E5E4] shadow-sm flex flex-col justify-between"
            >
              <div>
                <div className="flex items-center gap-2.5 mb-4">
                  <span className="w-6 h-6 rounded-full bg-[#EEF2FF] text-[#4F46E5] flex items-center justify-center font-bold text-xs">
                    {item.step}
                  </span>
                  <span className="text-[10px] font-mono uppercase font-bold tracking-wider text-[#A8A29E]">
                    {item.label}
                  </span>
                </div>
                <h3 className="text-base font-semibold text-[#1C1917] mb-2">{item.title}</h3>
                <p className="text-xs text-[#78716C] leading-relaxed">{item.description}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Everything you need */}
      <section id="features" className="max-w-6xl mx-auto px-6 py-20 border-t border-[#E7E5E4]">
        <div className="mb-12">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-[#4F46E5] mb-1">
            CORE CAPABILITIES
          </p>
          <h2 className="text-2xl sm:text-3xl font-bold tracking-tight text-[#1C1917]">
            Everything you need to notify
          </h2>
          <p className="text-sm text-[#78716C] mt-1 max-w-xl">
            No telemetry lock-in, no per-seat pricing penalties. Built strictly for engineers who care about uptime and privacy.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-12">
          {FEATURES.map((f) => {
            const Icon = f.icon;
            return (
              <div
                key={f.title}
                className="p-6 rounded-[8px] bg-white border border-[#E7E5E4] shadow-sm space-y-3"
              >
                <div className="w-9 h-9 rounded-[6px] bg-[#EEF2FF] text-[#4F46E5] flex items-center justify-center">
                  <Icon className="w-5 h-5" strokeWidth={1.5} />
                </div>
                <h3 className="text-base font-semibold text-[#1C1917]">{f.title}</h3>
                <p className="text-xs text-[#78716C] leading-relaxed">{f.description}</p>
              </div>
            );
          })}
        </div>

        {/* 4 Metrics Strip */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 p-6 rounded-[8px] bg-white border border-[#E7E5E4] shadow-sm">
          {METRICS.map((m) => (
            <div key={m.label} className="space-y-1">
              <div className="text-2xl font-bold text-[#1C1917] tracking-tight">{m.value}</div>
              <div className="text-xs text-[#78716C]">{m.label}</div>
            </div>
          ))}
        </div>
      </section>

      {/* Call to action */}
      <section className="max-w-6xl mx-auto px-6 py-20 border-t border-[#E7E5E4] text-center">
        <h2 className="text-2xl sm:text-3xl font-bold tracking-tight text-[#1C1917] mb-3">
          Ready to take control of your notification stack?
        </h2>
        <p className="text-sm text-[#78716C] max-w-lg mx-auto mb-8">
          Spin up an instance in under 3 minutes with Docker or deploy directly to your preferred cloud provider.
        </p>
        <div className="flex items-center justify-center gap-3">
          <Link to="/signup">
            <Button size="lg" icon={ArrowRight}>
              Get started free
            </Button>
          </Link>
          <Link to="/docs">
            <Button variant="secondary" size="lg">
              Explore API
            </Button>
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-[#E7E5E4] bg-white py-8">
        <div className="max-w-6xl mx-auto px-6 flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-[#78716C]">
          <div className="flex items-center gap-2">
            <span className="w-5 h-5 rounded-[4px] bg-[#4F46E5] text-white flex items-center justify-center font-bold text-[11px]">
              N
            </span>
            <span>
              Released under the <strong className="text-[#1C1917] font-medium">MIT License</strong>. Free to use, self-host, and modify.
            </span>
          </div>

          <div className="flex items-center gap-6">
            <Link to="/docs" className="hover:text-[#1C1917] transition-colors">
              Documentation
            </Link>
            <a
              href="https://github.com"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1 hover:text-[#1C1917] transition-colors"
            >
              <span>GitHub</span>
              <ExternalLink className="w-3 h-3" strokeWidth={1.5} />
            </a>
          </div>
        </div>
      </footer>
    </div>
  );
}
