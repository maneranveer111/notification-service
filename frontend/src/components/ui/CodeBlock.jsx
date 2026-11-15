import { useState } from 'react';
import { Copy, Check } from 'lucide-react';

export default function CodeBlock({
  code,
  language,
  className = '',
  title,
}) {
  const [copied, setCopied] = useState(false);

  function handleCopy() {
    navigator.clipboard.writeText(code).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  return (
    <div
      className={`rounded-[8px] bg-[#18181B] border border-[#27272A] overflow-hidden text-xs ${className}`}
    >
      <div className="flex items-center justify-between px-3.5 py-2 bg-[#27272A]/40 border-b border-[#27272A]">
        <div className="flex items-center gap-2">
          <div className="flex gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-[#3F3F46]" />
            <span className="w-2.5 h-2.5 rounded-full bg-[#3F3F46]" />
            <span className="w-2.5 h-2.5 rounded-full bg-[#3F3F46]" />
          </div>
          {title && (
            <span className="text-[11px] font-mono text-[#A1A1AA] ml-2">
              {title}
            </span>
          )}
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
      <div className="p-4 overflow-x-auto font-mono text-[#E4E4E7] leading-relaxed">
        <pre className="whitespace-pre" data-language={language}>{code}</pre>
      </div>
    </div>
  );
}
