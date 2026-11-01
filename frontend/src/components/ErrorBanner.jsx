export default function ErrorBanner({ error, onRetry }) {
  if (!error) return null;
  const msg = error?.message || String(error);
  return (
    <div className="flex items-center justify-between gap-3 px-4 py-3 rounded-lg bg-red-900/30 border border-red-700 text-red-300 text-sm">
      <span>⚠ {msg}</span>
      {onRetry && (
        <button
          onClick={onRetry}
          className="shrink-0 px-3 py-1 rounded bg-red-800 hover:bg-red-700 text-red-100 text-xs font-medium"
        >
          Retry
        </button>
      )}
    </div>
  );
}

