const statusColors = {
  pending: "bg-yellow-100 text-yellow-800",
  sent: "bg-green-100 text-green-800",
  failed: "bg-red-100 text-red-800",
  retrying: "bg-orange-100 text-orange-800",
};

export default function NotificationList({ notifications, onRetry, retryingId }) {
  if (notifications.length === 0) {
    return (
      <div className="bg-white rounded-lg shadow p-6 text-center text-gray-500">
        No notifications yet.
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg shadow overflow-hidden">
      <table className="w-full text-sm">
        <thead className="bg-gray-50 text-gray-600 text-left">
          <tr>
            <th className="px-4 py-3">Channel</th>
            <th className="px-4 py-3">Recipient</th>
            <th className="px-4 py-3">Status</th>
            <th className="px-4 py-3">Attempts</th>
            <th className="px-4 py-3">Created</th>
            <th className="px-4 py-3">Action</th>
          </tr>
        </thead>
        <tbody>
          {notifications.map((n) => (
            <tr key={n.id} className="border-t border-gray-100">
              <td className="px-4 py-3 capitalize">{n.channel}</td>
              <td className="px-4 py-3">{n.recipient}</td>
              <td className="px-4 py-3">
                <span
                  className={`px-2 py-1 rounded-full text-xs font-medium ${
                    statusColors[n.status] || "bg-gray-100 text-gray-800"
                  }`}
                >
                  {n.status}
                </span>
              </td>
              <td className="px-4 py-3">
                {n.attempt_count}/{n.max_attempts}
              </td>
              <td className="px-4 py-3 text-gray-500">
                {new Date(n.created_at).toLocaleString()}
              </td>
              <td className="px-4 py-3">
                {(n.status === "failed" || n.status === "retrying") && (
                  <button
                    onClick={() => onRetry(n.id)}
                    disabled={retryingId === n.id}
                    className="text-blue-600 hover:underline text-xs font-medium disabled:opacity-50"
                  >
                    {retryingId === n.id ? "Retrying..." : "Retry"}
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}