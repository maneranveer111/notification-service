const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;
const API_KEY = import.meta.env.VITE_API_KEY;

const headers = {
  "Content-Type": "application/json",
  "X-API-Key": API_KEY,
};

export async function sendEmail(payload) {
  const res = await fetch(`${API_BASE_URL}/notifications/email`, {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error((await res.json()).detail || "Failed to send email");
  return res.json();
}

export async function sendSMS(payload) {
  const res = await fetch(`${API_BASE_URL}/notifications/sms`, {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error((await res.json()).detail || "Failed to send SMS");
  return res.json();
}

export async function listNotifications({ status, channel, limit = 50, offset = 0 } = {}) {
  const params = new URLSearchParams();
  if (status) params.append("status", status);
  if (channel) params.append("channel", channel);
  params.append("limit", limit);
  params.append("offset", offset);

  const res = await fetch(`${API_BASE_URL}/notifications?${params.toString()}`, { headers });
  if (!res.ok) throw new Error("Failed to fetch notifications");
  return res.json();
}

export async function retryNotification(id) {
  const res = await fetch(`${API_BASE_URL}/notifications/${id}/retry`, {
    method: "POST",
    headers,
  });
  if (!res.ok) throw new Error((await res.json()).detail || "Failed to retry");
  return res.json();
}