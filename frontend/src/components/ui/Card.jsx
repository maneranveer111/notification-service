export default function Card({
  children,
  className = '',
  title,
  subtitle,
  action,
  headerClassName = '',
  bodyClassName = '',
  ...props
}) {
  return (
    <div
      className={`bg-white border border-[#E7E5E4] rounded-[8px] overflow-hidden ${className}`}
      {...props}
    >
      {(title || subtitle || action) && (
        <div
          className={`px-5 py-4 border-b border-[#E7E5E4] flex items-center justify-between gap-4 ${headerClassName}`}
        >
          <div>
            {title && (
              <h3 className="text-sm font-semibold text-[#1C1917]">{title}</h3>
            )}
            {subtitle && (
              <p className="text-xs text-[#78716C] mt-0.5">{subtitle}</p>
            )}
          </div>
          {action && <div className="shrink-0">{action}</div>}
        </div>
      )}
      <div className={`p-5 ${bodyClassName}`}>{children}</div>
    </div>
  );
}
