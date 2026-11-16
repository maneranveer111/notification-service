import { ChevronLeft, ChevronRight } from 'lucide-react';

const PAGE_SIZES = [25, 50, 100];

export default function Pagination({
  total,
  page,
  pageSize,
  onPageChange,
  onPageSizeChange,
  className = '',
}) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const start = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const end = Math.min(total, page * pageSize);

  return (
    <div
      className={`flex flex-col sm:flex-row items-center justify-between gap-4 px-4 py-3 bg-white border-t border-[#E7E5E4] text-xs text-[#78716C] ${className}`}
    >
      <div className="flex items-center gap-2">
        <span>
          Showing <span className="font-medium text-[#1C1917]">{start}</span>–
          <span className="font-medium text-[#1C1917]">{end}</span> of{' '}
          <span className="font-medium text-[#1C1917]">{total}</span>
        </span>
      </div>

      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <span>Rows per page:</span>
          <select
            value={pageSize}
            onChange={(e) => onPageSizeChange(Number(e.target.value))}
            className="rounded-[4px] border border-[#E7E5E4] bg-white px-2 py-1 text-xs text-[#1C1917] focus:outline-none focus:border-[#4F46E5]"
          >
            {PAGE_SIZES.map((size) => (
              <option key={size} value={size}>
                {size}
              </option>
            ))}
          </select>
        </div>

        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => onPageChange(page - 1)}
            disabled={page <= 1}
            className="p-1 rounded-[4px] border border-[#E7E5E4] text-[#1C1917] hover:bg-[#F5F5F4] disabled:opacity-40 disabled:pointer-events-none transition-colors"
            aria-label="Previous page"
          >
            <ChevronLeft className="w-4 h-4" strokeWidth={1.5} />
          </button>
          <span className="px-2 font-mono text-[11px] text-[#1C1917]">
            {page} / {totalPages}
          </span>
          <button
            type="button"
            onClick={() => onPageChange(page + 1)}
            disabled={page >= totalPages}
            className="p-1 rounded-[4px] border border-[#E7E5E4] text-[#1C1917] hover:bg-[#F5F5F4] disabled:opacity-40 disabled:pointer-events-none transition-colors"
            aria-label="Next page"
          >
            <ChevronRight className="w-4 h-4" strokeWidth={1.5} />
          </button>
        </div>
      </div>
    </div>
  );
}
