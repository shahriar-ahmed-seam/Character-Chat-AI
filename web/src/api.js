// Thin Backend_API client. Contains NO persona injection, memory, or model-routing
// logic — it only forwards requests and returns responses (Requirements 8.8, 9.7).

const BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8099";
const API_KEY = import.meta.env.VITE_API_KEY || "";
// Must exceed the backend's LLM timeout so the browser never aborts a request the
// server is still working on. Configurable via VITE_API_TIMEOUT_MS.
const TIMEOUT_MS = Number(import.meta.env.VITE_API_TIMEOUT_MS) || 130000;

function authHeaders() {
  const headers = { "Content-Type": "application/json" };
  if (API_KEY) headers["Authorization"] = `Bearer ${API_KEY}`;
  return headers;
}

async function request(path, options = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const resp = await fetch(`${BASE_URL}${path}`, {
      ...options,
      headers: { ...authHeaders(), ...(options.headers || {}) },
      signal: controller.signal,
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      const err = new Error(data.message || `Request failed (${resp.status})`);
      err.errorId = data.error_id || "http_error";
      err.status = resp.status;
      throw err;
    }
    return data;
  } catch (e) {
    if (e.name === "AbortError") {
      const err = new Error("The request timed out. Please try again.");
      err.errorId = "timeout";
      throw err;
    }
    throw e;
  } finally {
    clearTimeout(timer);
  }
}

export const api = {
  listPersonas: () => request("/personas"),
  createSession: (personaId) =>
    request("/sessions", {
      method: "POST",
      body: JSON.stringify({ persona_id: personaId }),
    }),
  getHistory: (sessionId) => request(`/sessions/${sessionId}/history`),
  sendMessage: (sessionId, content) =>
    request(`/sessions/${sessionId}/messages`, {
      method: "POST",
      body: JSON.stringify({ content }),
    }),
};
