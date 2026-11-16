export default function Switch({
  checked = false,
  onChange,
  disabled = false,
  label,
  description,
  id,
}) {
  return (
    <label
      htmlFor={id}
      className={`inline-flex items-start gap-3 cursor-pointer select-none ${
        disabled ? 'opacity-50 cursor-not-allowed' : ''
      }`}
    >
      <div className="relative inline-flex items-center shrink-0 mt-0.5">
        <input
          id={id}
          type="checkbox"
          checked={checked}
          onChange={(e) => onChange?.(e.target.checked)}
          disabled={disabled}
          className="sr-only peer"
        />
        <div className="w-9 h-5 bg-[#E7E5E4] peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-[#4F46E5]/20 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-[#4F46E5]"></div>
      </div>
      {(label || description) && (
        <div className="flex flex-col">
          {label && (
            <span className="text-sm font-medium text-[#1C1917]">{label}</span>
          )}
          {description && (
            <span className="text-xs text-[#78716C]">{description}</span>
          )}
        </div>
      )}
    </label>
  );
}
