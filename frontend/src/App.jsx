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
        <div className="mb-8">
          <div className="flex items-center gap-3 mb-1">
            <div className="bg-blue-600 rounded-lg p-2">
              <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
              </svg>
            </div>
            <h1 className="text-3xl font-bold text-gray-900 tracking-tight">Notification Service</h1>
          </div>
          <p className="text-gray-500 text-sm ml-[52px]">Send emails and SMS, track delivery status in real time</p>
        </div>

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