import { Inbox } from 'lucide-react';

export default function EmptyState({
  icon: Icon = Inbox,
  title = 'No items found',
  message = 'There are no items to display right now.',
  action,
  className = '',
}) {
  return (
    <div
      className={`p-10 text-center flex flex-col items-center justify-center bg-white rounded-[8px] border border-[#E7E5E4] ${className}`}
    >
      <div className="w-10 h-10 rounded-full bg-[#F5F5F4] flex items-center justify-center text-[#78716C] mb-3 border border-[#E7E5E4]/60">
        <Icon className="w-5 h-5" strokeWidth={1.5} />
      </div>
      <h3 className="text-sm font-semibold text-[#1C1917] mb-1">{title}</h3>
      <p className="text-xs text-[#78716C] max-w-sm mb-4 leading-relaxed">
        {message}
      </p>
      {action && <div>{action}</div>}
    </div>
  );
}
