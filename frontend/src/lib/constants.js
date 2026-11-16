export const POLL_INTERVAL_MS = 5000;

export const STATUSES = [
  'pending', 'processing', 'sent', 'retrying', 'failed',
  'delivered', 'bounced', 'undelivered', 'scheduled', 'cancelled', 'suppressed',
];

export const CHANNELS = ['email', 'sms', 'webhook'];

export const STATUS_COLORS = {
  pending: 'yellow',
  processing: 'blue',
  sent: 'green',
  retrying: 'amber',
  failed: 'red',
  delivered: 'emerald',
  bounced: 'red',
  undelivered: 'orange',
  scheduled: 'purple',
  cancelled: 'gray',
  suppressed: 'slate',
};

export const IN_PROGRESS_STATUSES = new Set(['pending', 'processing', 'retrying', 'scheduled']);

