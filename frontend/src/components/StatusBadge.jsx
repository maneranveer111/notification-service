const LABELS = {
  pending: 'Pending',
  processing: 'Processing',
  sent: 'Sent',
  retrying: 'Retrying',
  failed: 'Failed',
  delivered: 'Delivered',
  bounced: 'Bounced',
  undelivered: 'Undelivered',
  scheduled: 'Scheduled',
  cancelled: 'Cancelled',
  suppressed: 'Suppressed',
};

const STYLES = {
  delivered: 'bg-[#F0FDF4] text-[#15803D] border-[#BBF7D0]',
  sent: 'bg-[#F0FDF4] text-[#15803D] border-[#BBF7D0]',
  failed: 'bg-[#FEF2F2] text-[#B91C1C] border-[#FECACA]',
  bounced: 'bg-[#FEF2F2] text-[#B91C1C] border-[#FECACA]',
  undelivered: 'bg-[#FEF2F2] text-[#B91C1C] border-[#FECACA]',
  retrying: 'bg-[#FEFCE8] text-[#A16207] border-[#FEF08A]',
  pending: 'bg-[#F5F5F4] text-[#78716C] border-[#E7E5E4]',
  processing: 'bg-[#EFF6FF] text-[#1D4ED8] border-[#BFDBFE]',
  scheduled: 'bg-[#FAF5FF] text-[#7E22CE] border-[#E9D5FF]',
  cancelled: 'bg-[#F5F5F4] text-[#78716C] border-[#E7E5E4]',
  suppressed: 'bg-[#FEFCE8] text-[#A16207] border-[#FEF08A]',
};

const DOT_COLORS = {
  delivered: 'bg-[#15803D]',
  sent: 'bg-[#15803D]',
  failed: 'bg-[#B91C1C]',
  bounced: 'bg-[#B91C1C]',
  undelivered: 'bg-[#B91C1C]',
  retrying: 'bg-[#A16207]',
  pending: 'bg-[#78716C]',
  processing: 'bg-[#1D4ED8]',
  scheduled: 'bg-[#7E22CE]',
  cancelled: 'bg-[#78716C]',
  suppressed: 'bg-[#A16207]',
};

export default function StatusBadge({ status, className = '' }) {
  const norm = (status || '').toLowerCase();
  const label = LABELS[norm] || status;
  const style = STYLES[norm] || 'bg-[#F5F5F4] text-[#78716C] border-[#E7E5E4]';
  const dot = DOT_COLORS[norm] || 'bg-[#78716C]';

  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-[4px] text-[11px] font-medium border ${style} ${className}`}
    >
      <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${dot}`} />
      <span>{label}</span>
    </span>
  );
}
