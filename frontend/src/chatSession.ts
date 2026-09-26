// A chat session is one continuous conversation in this browser. Its id is
// generated client-side and kept in localStorage so a refresh finds the same
// session again: the server stores each message and uploaded document under
// it, which is what lets the conversation and the folder panel be restored.
// "New search" starts a fresh session (new id, empty thread and documents).

const SESSION_STORAGE_KEY = "nexora_chat_session_id";

export const NEW_SESSION_EVENT = "nexora-new-session";

export function createSessionId(): string {
  return crypto.randomUUID();
}

export function getOrCreateSessionId(): string {
  try {
    const existing = localStorage.getItem(SESSION_STORAGE_KEY);
    if (existing) return existing;
    const created = createSessionId();
    localStorage.setItem(SESSION_STORAGE_KEY, created);
    return created;
  } catch {
    // Storage unavailable (private mode): a per-page-load id still lets this
    // page's messages and uploads group together; they just won't survive a
    // refresh.
    return createSessionId();
  }
}

export function storeSessionId(sessionId: string): void {
  try {
    localStorage.setItem(SESSION_STORAGE_KEY, sessionId);
  } catch {
    // ignore -- same non-fatal storage failure as above
  }
}
