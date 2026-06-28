// Remembers which backend session belongs to each character on this device, so
// reopening a character continues the same conversation instead of starting fresh.
const key = (personaId) => `cc:session:${personaId}`;

export function getStoredSession(personaId) {
  try {
    return localStorage.getItem(key(personaId));
  } catch {
    return null;
  }
}

export function setStoredSession(personaId, sessionId) {
  try {
    localStorage.setItem(key(personaId), sessionId);
  } catch {
    /* ignore storage failures (private mode etc.) */
  }
}

export function clearStoredSession(personaId) {
  try {
    localStorage.removeItem(key(personaId));
  } catch {
    /* ignore */
  }
}
