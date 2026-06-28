import { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import Avatar from "./Avatar.jsx";
import { themeFor } from "../theme.js";
import { getStoredSession, setStoredSession, clearStoredSession } from "../storage.js";

// Chat view for a conversation with the selected persona. On error/timeout it shows
// an error indication AND keeps the user's unsent text so they can retry
// (Requirements 8.3, 8.4, 8.5, 8.6). The session id is remembered per character on the
// device so reopening continues the same conversation and reloads its history.
export default function ChatView({ persona, onBack }) {
  const [sessionId, setSessionId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [starting, setStarting] = useState(true);
  const endRef = useRef(null);

  async function openSession() {
    setStarting(true);
    setError("");
    // Reuse a remembered session and reload its history if one exists.
    const stored = getStoredSession(persona.id);
    if (stored) {
      try {
        const hist = await api.getHistory(stored);
        setSessionId(stored);
        setMessages((hist.messages || []).map((m) => ({
          id: m.id, role: m.role, content: m.content,
        })));
        setStarting(false);
        return;
      } catch {
        // Stored session no longer exists (e.g., server data reset) -> start fresh.
        clearStoredSession(persona.id);
      }
    }
    try {
      const s = await api.createSession(persona.id);
      setSessionId(s.session_id);
      setStoredSession(persona.id, s.session_id);
      setMessages([]);
    } catch (e) {
      setError(e.message || "Could not start the conversation.");
    } finally {
      setStarting(false);
    }
  }

  async function startNewChat() {
    clearStoredSession(persona.id);
    setMessages([]);
    setDraft("");
    await openSession();
  }

  useEffect(() => {
    let active = true;
    setMessages([]);
    openSession().catch(() => {});
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [persona.id]);

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ behavior: "smooth" });
  }, [messages, sending]);

  async function handleSend(e) {
    e.preventDefault();
    const content = draft.trim();
    if (!content || sending || !sessionId) return;
    setSending(true);
    setError("");
    // Optimistically show the user's message.
    setMessages((prev) => [...prev, { role: "user", content, id: `local-${Date.now()}` }]);
    try {
      const res = await api.sendMessage(sessionId, content);
      setMessages((prev) => [...prev, res.message]);
      setDraft(""); // clear only on success
    } catch (err) {
      // Keep the draft so the user can resend (Requirement 8.6).
      setError(err.message || "Message could not be delivered.");
      // Roll back the optimistic user bubble to avoid duplicates on resend.
      setMessages((prev) => prev.filter((m) => m.content !== content || m.role !== "user"));
      setDraft(content);
    } finally {
      setSending(false);
    }
  }

  const theme = themeFor(persona);

  return (
    <div className="chat" style={{ "--accent": theme.accent, "--accent2": theme.accent2, "--glow": theme.glow }}>
      <header className="chat-header">
        <button className="back" onClick={onBack} aria-label="Back to characters">←</button>
        <Avatar persona={persona} size={40} />
        <div className="chat-header-meta">
          <div className="persona-name">{persona.name}</div>
          <div className="persona-archetype">{persona.archetype}</div>
        </div>
        <button className="new-chat" onClick={startNewChat} title="Start a new conversation">
          New chat
        </button>
        <img className="chat-header-logo" src="/logo.webp" alt="Character Chat" />
      </header>

      <div className="messages">
        {starting && <p className="status" role="status">Starting conversation…</p>}
        {!starting && messages.length === 0 && (
          <div className="chat-intro">
            <Avatar persona={persona} size={72} />
            <p>Say hello to {persona.name}.</p>
          </div>
        )}
        {messages.map((m) => (
          <div key={m.id} className={`bubble ${m.role}`}>
            {m.content}
          </div>
        ))}
        {sending && (
          <div className="bubble assistant pending" aria-label="typing">
            <span className="dot" /><span className="dot" /><span className="dot" />
          </div>
        )}
        <div ref={endRef} />
      </div>

      {error && (
        <div className="status error" role="alert">
          {error}
        </div>
      )}

      <form className="composer" onSubmit={handleSend}>
        <input
          type="text"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={`Message ${persona.name}…`}
          disabled={starting}
          aria-label="Message"
        />
        <button type="submit" disabled={sending || starting || !draft.trim()}>
          Send
        </button>
      </form>
    </div>
  );
}
