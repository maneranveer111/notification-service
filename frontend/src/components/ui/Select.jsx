import { forwardRef } from 'react';
import { ChevronDown } from 'lucide-react';

const Select = forwardRef(function Select(
  {
    label,
    id,
    error,
    helper,
    className = '',
    children,
    ...props
  },
  ref
) {
  return (
    <div className="space-y-1.5 w-full">
      {label && (
        <label
          htmlFor={id}
          className="block text-xs font-medium text-[#1C1917]"
        >
          {label}
        </label>
      )}
      <div className="relative">
        <select
          ref={ref}
          id={id}
          className={`block w-full appearance-none bg-white border border-[#E7E5E4] rounded-[6px] text-sm text-[#1C1917] px-3 py-2 pr-8 transition-colors focus:outline-none focus:ring-2 focus:ring-[#4F46E5]/20 focus:border-[#4F46E5] disabled:bg-[#F5F5F4] disabled:text-[#78716C] disabled:cursor-not-allowed ${
            error
              ? 'border-[#B91C1C] focus:ring-red-500/20 focus:border-[#B91C1C]'
              : 'border-[#E7E5E4]'
          } ${className}`}
          {...props}
        >
          {children}
        </select>
        <div className="absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none text-[#78716C]">
          <ChevronDown className="w-4 h-4" strokeWidth={1.5} />
        </div>
      </div>
      {error ? (
        <p className="text-xs text-[#B91C1C]">{error}</p>
      ) : helper ? (
        <p className="text-xs text-[#78716C]">{helper}</p>
      ) : null}
    </div>
  );
});

export default Select;
