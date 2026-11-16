export default function Badge({
  children,
  variant = 'neutral',
  size = 'sm',
  className = '',
  dot = false,
}) {
  const variants = {
    neutral: 'bg-[#F5F5F4] text-[#57534E] border-[#E7E5E4]',
    success: 'bg-[#F0FDF4] text-[#15803D] border-[#BBF7D0]',
    error: 'bg-[#FEF2F2] text-[#B91C1C] border-[#FECACA]',
    warning: 'bg-[#FEFCE8] text-[#A16207] border-[#FEF08A]',
    accent: 'bg-[#EEF2FF] text-[#4F46E5] border-[#C7D2FE]',
  };

  const dotColors = {
    neutral: 'bg-[#78716C]',
    success: 'bg-[#15803D]',
    error: 'bg-[#B91C1C]',
    warning: 'bg-[#A16207]',
    accent: 'bg-[#4F46E5]',
  };

  const sizes = {
    sm: 'text-[11px] px-2 py-0.5 rounded-[4px]',
    md: 'text-xs px-2.5 py-1 rounded-[5px]',
  };

  return (
    <span
      className={`inline-flex items-center gap-1.5 font-medium border ${
        variants[variant] || variants.neutral
      } ${sizes[size] || sizes.sm} ${className}`}
    >
      {dot && (
        <span
          className={`w-1.5 h-1.5 rounded-full shrink-0 ${
            dotColors[variant] || dotColors.neutral
          }`}
        />
      )}
      {children}
    </span>
  );
}
