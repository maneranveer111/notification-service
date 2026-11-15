import StatusBadge from './StatusBadge';
import EmptyState from './EmptyState';
import Button from './ui/Button';
import { Bell } from 'lucide-react';

export default function NotificationList({ notifications, onRetry, retryingId }) {
  if (notifications.length === 0) {
    return (
      <EmptyState
        icon={Bell}
        title="No notifications yet"
        description="Notifications dispatched through the API or console will appear here."
      />
    );
  }

  return (
    <div className="bg-white rounded-[8px] border border-[#E7E5E4] overflow-hidden shadow-sm">
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="bg-[#F5F5F4] text-[#78716C] border-b border-[#E7E5E4]">
              <th className="px-4 py-3 text-left font-semibold text-[11px] uppercase tracking-wider">Channel</th>
              <th className="px-4 py-3 text-left font-semibold text-[11px] uppercase tracking-wider">Recipient</th>
              <th className="px-4 py-3 text-left font-semibold text-[11px] uppercase tracking-wider">Status</th>
              <th className="px-4 py-3 text-left font-semibold text-[11px] uppercase tracking-wider">Attempts</th>
              <th className="px-4 py-3 text-left font-semibold text-[11px] uppercase tracking-wider">Created</th>
              <th className="px-4 py-3 text-right font-semibold text-[11px] uppercase tracking-wider">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#E7E5E4] bg-white">
            {notifications.map((n) => (
              <tr key={n.id} className="hover:bg-[#FAFAF9] transition-colors">
                <td className="px-4 py-3 capitalize text-[#1C1917] font-medium">
                  {n.channel}
                </td>
                <td className="px-4 py-3 font-mono text-[11px] text-[#44403C]">{n.recipient}</td>
                <td className="px-4 py-3">
                  <StatusBadge status={n.status} />
                </td>
                <td className="px-4 py-3 text-[#78716C]">
                  {n.attempt_count}/{n.max_attempts}
                </td>
                <td className="px-4 py-3 text-[#78716C]">
                  {new Date(n.created_at).toLocaleString()}
                </td>
                <td className="px-4 py-3 text-right">
                  {(n.status === 'failed' || n.status === 'retrying') && (
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => onRetry(n.id)}
                      loading={retryingId === n.id}
                    >
                      Retry
                    </Button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
