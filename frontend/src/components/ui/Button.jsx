export default function Button({
  children,
  variant = 'secondary',
  size = 'md',
  className = '',
  disabled = false,
  loading = false,
  type = 'button',
  icon: Icon,
  ...props
}) {
  const base =
    'inline-flex items-center justify-center font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-[#4F46E5]/20 disabled:opacity-50 disabled:pointer-events-none cursor-pointer';

  const variants = {
    primary:
      'bg-[#4F46E5] hover:bg-[#4338CA] text-white shadow-xs focus:border-[#4F46E5]',
    secondary:
      'bg-white hover:bg-[#F5F5F4] text-[#1C1917] border border-[#E7E5E4] shadow-xs focus:border-[#4F46E5]',
    destructive:
      'bg-white hover:bg-[#FEF2F2] text-[#B91C1C] border border-[#FECACA] focus:ring-red-500/20 focus:border-red-500',
    'destructive-filled':
      'bg-[#B91C1C] hover:bg-[#991B1B] text-white shadow-xs focus:border-red-600',
    ghost:
      'bg-transparent hover:bg-[#F5F5F4] text-[#78716C] hover:text-[#1C1917]',
    link:
      'bg-transparent p-0 text-[#4F46E5] hover:text-[#4338CA] underline-offset-2 hover:underline focus:ring-0',
  };

  const sizes = {
    sm: 'text-xs px-2.5 py-1.5 rounded-[6px] gap-1.5',
    md: 'text-sm px-3.5 py-2 rounded-[6px] gap-2',
    lg: 'text-base px-4 py-2.5 rounded-[6px] gap-2.5',
    icon: 'p-1.5 rounded-[6px] text-[#78716C] hover:text-[#1C1917]',
  };

  return (
    <button
      type={type}
      disabled={disabled || loading}
      className={`${base} ${variants[variant] || variants.secondary} ${sizes[size] || sizes.md} ${className}`}
      {...props}
    >
      {loading ? (
        <span className="inline-block animate-spin rounded-full h-3.5 w-3.5 border-2 border-current border-t-transparent" />
      ) : (
        Icon && <Icon className="w-4 h-4 shrink-0" strokeWidth={1.5} />
      )}
      {children}
    </button>
  );
}
