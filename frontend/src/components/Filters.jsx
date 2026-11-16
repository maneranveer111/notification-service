import Select from './ui/Select';
import Button from './ui/Button';
import { RefreshCw } from 'lucide-react';

export default function Filters({ status, channel, onStatusChange, onChannelChange, onRefresh }) {
  const statusOptions = [
    { value: '', label: 'All statuses' },
    { value: 'pending', label: 'Pending' },
    { value: 'processing', label: 'Processing' },
    { value: 'sent', label: 'Sent' },
    { value: 'delivered', label: 'Delivered' },
    { value: 'retrying', label: 'Retrying' },
    { value: 'failed', label: 'Failed' },
    { value: 'bounced', label: 'Bounced' },
    { value: 'undelivered', label: 'Undelivered' },
    { value: 'scheduled', label: 'Scheduled' },
    { value: 'cancelled', label: 'Cancelled' },
    { value: 'suppressed', label: 'Suppressed' },
  ];

  const channelOptions = [
    { value: '', label: 'All channels' },
    { value: 'email', label: 'Email' },
    { value: 'sms', label: 'SMS' },
    { value: 'webhook', label: 'Webhook' },
  ];

  return (
    <div className="bg-white rounded-[8px] border border-[#E7E5E4] p-3.5 mb-4 flex flex-wrap items-center gap-3 shadow-sm">
      <div className="w-44">
        <Select
          value={status}
          onChange={(e) => onStatusChange(e.target.value)}
          options={statusOptions}
        />
      </div>

      <div className="w-40">
        <Select
          value={channel}
          onChange={(e) => onChannelChange(e.target.value)}
          options={channelOptions}
        />
      </div>

      <Button
        variant="secondary"
        size="md"
        icon={RefreshCw}
        onClick={onRefresh}
        className="ml-auto"
      >
        Refresh
      </Button>
    </div>
  );
}
