export default function Filters({ status, channel, onStatusChange, onChannelChange, onRefresh }) {
  return (
    <div className="bg-white rounded-lg shadow p-4 mb-4 flex flex-wrap gap-4 items-end">
      <div>
        <label className="block text-xs font-medium text-gray-600 mb-1">Status</label>
        <select
          value={status}
          onChange={(e) => onStatusChange(e.target.value)}
          className="border border-gray-300 rounded-md px-3 py-2 text-sm"
        >
          <option value="">All</option>
          <option value="pending">Pending</option>
          <option value="sent">Sent</option>
          <option value="failed">Failed</option>
          <option value="retrying">Retrying</option>
        </select>
      </div>

      <div>
        <label className="block text-xs font-medium text-gray-600 mb-1">Channel</label>
        <select
          value={channel}
          onChange={(e) => onChannelChange(e.target.value)}
          className="border border-gray-300 rounded-md px-3 py-2 text-sm"
        >
          <option value="">All</option>
          <option value="email">Email</option>
          <option value="sms">SMS</option>
        </select>
      </div>

      <button
        onClick={onRefresh}
        className="bg-gray-100 text-gray-700 px-4 py-2 rounded-md text-sm font-medium hover:bg-gray-200"
      >
        Refresh
      </button>
    </div>
  );
}