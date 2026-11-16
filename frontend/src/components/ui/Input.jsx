import { forwardRef } from 'react';

const Input = forwardRef(function Input(
  {
    label,
    id,
    error,
    helper,
    className = '',
    type = 'text',
    mono = false,
    leftIcon: LeftIcon,
    rightElement,
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
      <div className="relative flex items-center">
        {LeftIcon && (
          <div className="absolute left-3 text-[#78716C] pointer-events-none">
            <LeftIcon className="w-4 h-4" strokeWidth={1.5} />
          </div>
        )}
        <input
          ref={ref}
          id={id}
          type={type}
          className={`block w-full bg-white border rounded-[6px] text-sm text-[#1C1917] placeholder:text-[#A8A29E] transition-colors focus:outline-none focus:ring-2 focus:ring-[#4F46E5]/20 focus:border-[#4F46E5] disabled:bg-[#F5F5F4] disabled:text-[#78716C] disabled:cursor-not-allowed ${
            LeftIcon ? 'pl-9' : 'pl-3'
          } ${rightElement ? 'pr-10' : 'pr-3'} py-2 ${
            error
              ? 'border-[#B91C1C] focus:ring-red-500/20 focus:border-[#B91C1C]'
              : 'border-[#E7E5E4]'
          } ${mono ? 'font-mono text-[13px]' : ''} ${className}`}
          {...props}
        />
        {rightElement && (
          <div className="absolute right-2.5 flex items-center">
            {rightElement}
          </div>
        )}
      </div>
      {error ? (
        <p className="text-xs text-[#B91C1C]">{error}</p>
      ) : helper ? (
        <p className="text-xs text-[#78716C]">{helper}</p>
      ) : null}
    </div>
  );
});

export default Input;
