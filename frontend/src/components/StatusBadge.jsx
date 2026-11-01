import { STATUS_COLORS } from '../lib/constants';

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

const COLOR_CLASSES = {
  yellow: 'bg-yellow-900/40 text-yellow-300 border-yellow-700',
  blue: 'bg-blue-900/40 text-blue-300 border-blue-700',
  green: 'bg-green-900/40 text-green-300 border-green-700',
  amber: 'bg-amber-900/40 text-amber-300 border-amber-700',
  red: 'bg-red-900/40 text-red-300 border-red-700',
  emerald: 'bg-emerald-900/40 text-emerald-300 border-emerald-700',
  orange: 'bg-orange-900/40 text-orange-300 border-orange-700',
  purple: 'bg-purple-900/40 text-purple-300 border-purple-700',
  gray: 'bg-gray-700/40 text-gray-300 border-gray-600',
  slate: 'bg-slate-700/40 text-slate-300 border-slate-600',
};

export default function StatusBadge({ status }) {
  const color = STATUS_COLORS[status] || 'gray';
  const cls = COLOR_CLASSES[color] || COLOR_CLASSES.gray;
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border ${cls}`}>
      {LABELS[status] || status}
    </span>
  );
}

