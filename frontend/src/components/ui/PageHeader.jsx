export default function PageHeader({
  title,
  description,
  action,
  children,
  className = '',
}) {
  return (
    <div
      className={`flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-5 border-b border-[#E7E5E4] ${className}`}
    >
      <div>
        <h1 className="text-xl sm:text-2xl font-semibold text-[#1C1917] tracking-tight">
          {title}
        </h1>
        {description && (
          <p className="text-xs sm:text-sm text-[#78716C] mt-1">{description}</p>
        )}
      </div>
      {(action || children) && (
        <div className="flex items-center gap-2.5 shrink-0">
          {action}
          {children}
        </div>
      )}
    </div>
  );
}
