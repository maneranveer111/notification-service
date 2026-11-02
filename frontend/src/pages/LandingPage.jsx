import { useState } from 'react';
import { Link } from 'react-router-dom';
import { absoluteApiBase } from '../lib/api';

const FEATURES = [
  {
    title: 'Multi-channel',
    icon: '📬',
    description: 'Send via email, SMS, and webhook from a single unified API. Connect multiple providers per channel with automatic fallback.',
  },
  {
    title: 'Templates',
    icon: '🧩',
    description: 'Build reusable message templates with Jinja2 variable interpolation. Render dynamic content at send time.',
  },
  {
    title: 'API-first',
    icon: '⚡',
    description: 'REST API with idempotency keys, workspace isolation, and API key auth. Works wherever you can make an HTTP request.',
  },
];

const HOW_IT_WORKS = [
  {
    step: '1',
    title: 'Connect a provider',
    description: 'Add your email (SMTP / SendGrid / SES), SMS (Twilio), or webhook credentials in the Settings panel.',
  },
  {
    step: '2',
    title: 'Create a template',
    description: 'Define reusable message templates with Jinja2 variables, or send one-off messages directly.',
  },
  {
    step: '3',
    title: 'Call the API',
    description: 'POST to /notifications/email, /sms, or /webhook with your payload. Notify handles retry logic and delivery tracking.',
  },
];

export default function LandingPage() {
  const [copied, setCopied] = useState(false);
  const curlExample = `curl -X POST ${absoluteApiBase()}/notifications/email \\
  -H "Authorization: Bearer YOUR_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "recipient": "user@example.com",
    "subject": "Hello from Notify",
    "body": "Your notification is delivered."
  }'`;

  function handleCopy() {
    navigator.clipboard.writeText(curlExample).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  return (
    <div className="min-h-screen bg-gray-950 text-white">
      {/* Navbar */}
      <header className="border-b border-gray-800 bg-gray-950/80 backdrop-blur sticky top-0 z-50">
        <div className="max-w-6xl mx-auto px-4 py-4 flex items-center justify-between">
          <span className="font-bold text-blue-400 text-xl">Notify</span>
          <nav className="flex items-center gap-4">
            <Link
              to="/docs"
              className="text-sm text-gray-300 hover:text-white transition-colors"
            >
              Docs
            </Link>
            <Link
              to="/login"
              className="text-sm text-gray-300 hover:text-white transition-colors"
            >
              Log in
            </Link>
            <Link
              to="/signup"
              className="text-sm px-4 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-medium transition-colors"
            >
              Sign up
            </Link>
          </nav>
        </div>
      </header>

      {/* Hero */}
      <section className="max-w-6xl mx-auto px-4 py-24 text-center">
        <h1 className="text-4xl md:text-5xl font-bold text-white mb-4 leading-tight">
          Open-source notification infrastructure
        </h1>
        <p className="text-lg text-gray-400 max-w-2xl mx-auto mb-8">
          Send email, SMS, and webhooks from a single API. Self-host it, own your data, and scale without vendor lock-in.
        </p>
        <div className="flex flex-col sm:flex-row gap-3 justify-center">
          <Link
            to="/signup"
            className="px-6 py-3 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-semibold text-sm transition-colors"
          >
            Get started free
          </Link>
          <Link
            to="/docs"
            className="px-6 py-3 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-200 font-semibold text-sm border border-gray-700 transition-colors"
          >
            View docs
          </Link>
        </div>
      </section>

      {/* Features grid */}
      <section className="max-w-6xl mx-auto px-4 py-16">
        <h2 className="text-2xl font-bold text-center text-white mb-10">Everything you need to notify</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {FEATURES.map((f) => (
            <div
              key={f.title}
              className="bg-gray-900 border border-gray-800 rounded-xl p-6 space-y-3"
            >
              <div className="text-3xl">{f.icon}</div>
              <h3 className="text-lg font-semibold text-white">{f.title}</h3>
              <p className="text-sm text-gray-400 leading-relaxed">{f.description}</p>
            </div>
          ))}
        </div>
      </section>

      {/* How it works */}
      <section className="max-w-6xl mx-auto px-4 py-16">
        <h2 className="text-2xl font-bold text-center text-white mb-10">How it works</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {HOW_IT_WORKS.map((item) => (
            <div key={item.step} className="flex flex-col items-center text-center space-y-3">
              <div className="w-10 h-10 rounded-full bg-blue-600 flex items-center justify-center text-white font-bold text-sm">
                {item.step}
              </div>
              <h3 className="text-base font-semibold text-white">{item.title}</h3>
              <p className="text-sm text-gray-400 leading-relaxed">{item.description}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Live API example */}
      <section className="max-w-6xl mx-auto px-4 py-16">
        <h2 className="text-2xl font-bold text-center text-white mb-3">Try it in seconds</h2>
        <p className="text-center text-gray-400 text-sm mb-8">
          One request is all it takes. No SDK required.
        </p>
        <div className="relative max-w-3xl mx-auto">
          <pre className="bg-gray-900 border border-gray-800 rounded-xl p-5 text-green-300 text-xs overflow-x-auto whitespace-pre-wrap break-all leading-relaxed">
            {curlExample}
          </pre>
          <button
            type="button"
            onClick={handleCopy}
            className="absolute top-3 right-3 px-3 py-1.5 rounded-lg bg-gray-700 hover:bg-gray-600 text-gray-200 text-xs font-medium transition-colors"
          >
            {copied ? 'Copied!' : 'Copy'}
          </button>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-gray-800 mt-8">
        <div className="max-w-6xl mx-auto px-4 py-8 flex flex-col sm:flex-row items-center justify-between gap-3 text-sm text-gray-500">
          <span>
            Released under the{' '}
            <span className="text-gray-400 font-medium">MIT License</span>.
            Free to use, self-host, and modify.
          </span>
          <a
            href="https://github.com"
            target="_blank"
            rel="noopener noreferrer"
            className="text-gray-400 hover:text-white transition-colors"
          >
            GitHub ↗
          </a>
        </div>
      </footer>
    </div>
  );
}
