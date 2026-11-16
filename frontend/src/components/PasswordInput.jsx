import { useState } from 'react';
import { Eye, EyeOff } from 'lucide-react';

export default function PasswordInput({ id, label, error, helper, ...rest }) {
  const [show, setShow] = useState(false);
  return (
    <div className="space-y-1.5 w-full">
      {label && (
        <label htmlFor={id} className="block text-xs font-medium text-[#1C1917]">
          {label}
        </label>
      )}
      <div className="relative flex items-center">
        <input
          {...rest}
          id={id}
          type={show ? 'text' : 'password'}
          className={`block w-full bg-white border border-[#E7E5E4] rounded-[6px] text-xs text-[#1C1917] px-3 py-2 pr-9 placeholder:text-[#A8A29E] transition-colors focus:outline-none focus:ring-2 focus:ring-[#4F46E5]/20 focus:border-[#4F46E5] disabled:bg-[#F5F5F4] disabled:text-[#78716C] disabled:cursor-not-allowed ${
            error ? 'border-[#FECACA] focus:border-[#B91C1C] focus:ring-red-500/20' : ''
          }`}
        />
        <button
          type="button"
          onClick={() => setShow((s) => !s)}
          className="absolute right-2.5 p-1 text-[#78716C] hover:text-[#1C1917] transition-colors cursor-pointer"
          tabIndex={-1}
          aria-label={show ? 'Hide password' : 'Show password'}
        >
          {show ? (
            <EyeOff className="w-4 h-4" strokeWidth={1.5} />
          ) : (
            <Eye className="w-4 h-4" strokeWidth={1.5} />
          )}
        </button>
      </div>
      {error && <p className="text-[11px] text-[#B91C1C]">{error}</p>}
      {helper && !error && <p className="text-[11px] text-[#78716C]">{helper}</p>}
    </div>
  );
}
