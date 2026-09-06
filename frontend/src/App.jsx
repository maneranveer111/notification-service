import { useState, useEffect, useCallback } from "react";
import SendForm from "./components/SendForm";
import Filters from "./components/Filters";
import NotificationList from "./components/NotificationList";
import { listNotifications, retryNotification } from "./api";

function App() {
  const [notifications, setNotifications] = useState([]);
  const [status, setStatus] = useState("");
  const [channel, setChannel] = useState("");
  const [retryingId, setRetryingId] = useState(null);
  const [error, setError] = useState(null);

  const fetchNotifications = useCallback(async () => {
    try {
      const data = await listNotifications({ status, channel });
      setNotifications(data);
      setError(null);
    } catch (err) {
      setError(err.message);
    }
  }, [status, channel]);

  useEffect(() => {
    fetchNotifications();
  }, [fetchNotifications]);

  async function handleRetry(id) {
    setRetryingId(id);
    try {
      await retryNotification(id);
      await fetchNotifications();
    } catch (err) {
      setError(err.message);
    } finally {
      setRetryingId(null);
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 py-10 px-4">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-2xl font-bold text-gray-900 mb-6">Notification Service</h1>

        <SendForm onSent={fetchNotifications} />

        <Filters
          status={status}
          channel={channel}
          onStatusChange={setStatus}
          onChannelChange={setChannel}
          onRefresh={fetchNotifications}
        />

        {error && (
          <div className="bg-red-50 text-red-700 rounded-md p-3 mb-4 text-sm">{error}</div>
        )}

        <NotificationList notifications={notifications} onRetry={handleRetry} retryingId={retryingId} />
      </div>
    </div>
  );
}

export default App;