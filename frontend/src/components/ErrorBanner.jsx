import { AlertCircle } from 'lucide-react';

export default function ErrorBanner({ error, onRetry, className = '' }) {
  if (!error) return null;
  const msg = error?.message || String(error);
  return (
    <div
      className={`flex items-center justify-between gap-3 px-3.5 py-2.5 rounded-[6px] bg-[#FEF2F2] border border-[#FECACA] text-[#B91C1C] text-xs ${className}`}
    >
      <div className="flex items-center gap-2 min-w-0">
        <AlertCircle className="w-4 h-4 shrink-0 text-[#B91C1C]" strokeWidth={1.5} />
        <span className="truncate">{msg}</span>
      </div>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="text-xs font-medium text-[#B91C1C] hover:underline shrink-0"
        >
          Retry
        </button>
      )}
    </div>
  );
}
