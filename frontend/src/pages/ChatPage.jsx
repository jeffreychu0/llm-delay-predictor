import { useMemo, useState } from "react";

import SelectionInterface from "../components/SelectionInterface";
import { apiGet } from "../utils/api";
import { useStations } from "../utils/useStations";
import "../App.css";

function MessageBubble({ role, children }) {
  return <div className={`chat-bubble chat-bubble--${role}`}>{children}</div>;
}

export default function ChatPage() {
  const { stations, lines, loading, error } = useStations();
  const [selection, setSelection] = useState({
    selectedLine: "",
    direction: "north",
    station1: "",
    station2: "",
    filteredStations: [],
  });
  const [message, setMessage] = useState("");
  const [conversation, setConversation] = useState([
    {
      role: "assistant",
      content: "Pick a line and station, then ask about delays, weather, or how the ride looks.",
    },
  ]);
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState("");

  const selectedStation = useMemo(
    () => selection.filteredStations.find((station) => station["GTFS Stop ID"] === selection.station1),
    [selection.filteredStations, selection.station1],
  );

  const canSend = Boolean(selection.selectedLine && selection.station1 && message.trim() && !sending);

  const handleSend = async () => {
    if (!canSend || !selectedStation) {
      return;
    }

    const userMessage = message.trim();
    setConversation((current) => [...current, { role: "user", content: userMessage }]);
    setMessage("");
    setSendError("");
    setSending(true);

    try {
      const response = await apiGet("/chatbot/response", {
        stop_name: selectedStation["Stop Name"],
        stop_id: selection.station1,
        train: selection.selectedLine,
        direction: selection.direction === "south" ? 1 : 0,
        message: userMessage,
      });

      setConversation((current) => [
        ...current,
        {
          role: "assistant",
          content: response.response || "No response returned.",
        },
      ]);
    } catch (error) {
      setSendError(error.message);
      setConversation((current) => [
        ...current,
        {
          role: "assistant",
          content: `I couldn\'t reach the chatbot: ${error.message}`,
        },
      ]);
    } finally {
      setSending(false);
    }
  };

  if (loading) return <div className="loading">Loading stations...</div>;
  if (error) return <div className="error">Error: {error.message}</div>;

  return (
    <div className="page page--chat">
      <div className="page-grid page-grid--chat">
        <section className="panel panel--stacked">
          <SelectionInterface
            stations={stations}
            lines={lines}
            onSelectionChange={setSelection}
            showToStation={false}
          />

          <label className="chat-input-label" htmlFor="chat-message">
            Message
          </label>
          <textarea
            id="chat-message"
            className="chat-input"
            value={message}
            onChange={(event) => setMessage(event.target.value)}
            placeholder="Example: Will this train be late and what should I expect?"
            rows={4}
          />

          <button className="primary-button" onClick={handleSend} disabled={!canSend}>
            {sending ? "Sending..." : "Send"}
          </button>

          {sendError ? <p className="inline-error">{sendError}</p> : null}

          <div className="chat-context">
            <div>
              <span>Line</span>
              <strong>{selection.selectedLine || "None"}</strong>
            </div>
            <div>
              <span>Station</span>
              <strong>{selectedStation ? `${selectedStation["Stop Name"]} (${selectedStation["GTFS Stop ID"]})` : "None"}</strong>
            </div>
            <div>
              <span>Direction</span>
              <strong>{selection.direction || "None"}</strong>
            </div>
          </div>
        </section>

        <section className="panel chat-panel">
          <div className="panel-heading">
          </div>

          <div className="chat-thread">
            {conversation.map((entry, index) => (
              <MessageBubble key={`${entry.role}-${index}`} role={entry.role}>
                {entry.content}
              </MessageBubble>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}