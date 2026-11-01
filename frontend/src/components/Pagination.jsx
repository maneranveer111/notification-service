const PAGE_SIZES = [25, 50, 100];

export default function Pagination({ total, page, pageSize, onPageChange, onPageSizeChange }) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const to = Math.min(page * pageSize, total);

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 text-sm text-gray-400">
      <span>
        {total === 0 ? 'No results' : `Showing ${from}–${to} of ${total}`}
      </span>
      <div className="flex items-center gap-3">
        <label className="flex items-center gap-1">
          Rows:
          <select
            value={pageSize}
            onChange={(e) => onPageSizeChange(Number(e.target.value))}
            className="ml-1 bg-gray-800 border border-gray-600 rounded px-2 py-0.5 text-gray-200"
          >
            {PAGE_SIZES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </label>
        <div className="flex items-center gap-1">
          <button
            disabled={page <= 1}
            onClick={() => onPageChange(page - 1)}
            className="px-2 py-1 rounded bg-gray-800 border border-gray-600 disabled:opacity-40 hover:bg-gray-700"
          >
            ‹
          </button>
          <span className="px-2">{page} / {totalPages}</span>
          <button
            disabled={page >= totalPages}
            onClick={() => onPageChange(page + 1)}
            className="px-2 py-1 rounded bg-gray-800 border border-gray-600 disabled:opacity-40 hover:bg-gray-700"
          >
            ›
          </button>
        </div>
      </div>
    </div>
  );
}

