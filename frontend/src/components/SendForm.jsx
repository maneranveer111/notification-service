import { useState } from "react";
import { sendEmail, sendSMS } from "../api";

export default function SendForm({ onSent }) {
  const [channel, setChannel] = useState("email");
  const [recipient, setRecipient] = useState("");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setSuccess(null);

    try {
      let result;
      if (channel === "email") {
        result = await sendEmail({ recipient, subject, body });
      } else {
        result = await sendSMS({ recipient, message: body });
      }
      setSuccess(`Queued! ID: ${result.id}`);
      setRecipient("");
      setSubject("");
      setBody("");
      onSent?.();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="bg-white rounded-lg shadow p-6 mb-6">
      <div className="flex gap-2 mb-4">
        <button
          type="button"
          onClick={() => setChannel("email")}
          className={`px-4 py-2 rounded-md font-medium ${
            channel === "email" ? "bg-blue-600 text-white" : "bg-gray-100 text-gray-600"
          }`}
        >
          Email
        </button>
        <button
          type="button"
          onClick={() => setChannel("sms")}
          className={`px-4 py-2 rounded-md font-medium ${
            channel === "sms" ? "bg-blue-600 text-white" : "bg-gray-100 text-gray-600"
          }`}
        >
          SMS
        </button>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            {channel === "email" ? "Recipient Email" : "Recipient Phone"}
          </label>
          <input
            type="text"
            required
            value={recipient}
            onChange={(e) => setRecipient(e.target.value)}
            placeholder={channel === "email" ? "user@example.com" : "+919876543210"}
            className="w-full border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>

        {channel === "email" && (
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Subject</label>
            <input
              type="text"
              required
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              className="w-full border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
        )}

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            {channel === "email" ? "Body" : "Message"}
          </label>
          <textarea
            required
            rows={4}
            value={body}
            onChange={(e) => setBody(e.target.value)}
            className="w-full border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>

        {error && <p className="text-red-600 text-sm">{error}</p>}
        {success && <p className="text-green-600 text-sm">{success}</p>}

        <button
          type="submit"
          disabled={loading}
          className="bg-blue-600 text-white px-6 py-2 rounded-md font-medium hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? "Sending..." : `Send ${channel === "email" ? "Email" : "SMS"}`}
        </button>
      </form>
    </div>
  );
}