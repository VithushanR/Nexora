import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { getAuthToken, setAuthToken, clearAuthToken } from "../api/client";

interface HistoryEntry {
  threadId: string;
  domain: string;
  timestamp: number;
}

export function getHistory(): HistoryEntry[] {
  try {
    return JSON.parse(localStorage.getItem("nexora_history") || "[]");
  } catch {
    return [];
  }
}

export function addHistory(threadId: string, domain: string) {
  const history = getHistory().filter((h) => h.threadId !== threadId);
  history.unshift({ threadId, domain, timestamp: Date.now() });
  if (history.length > 50) history.length = 50;
  localStorage.setItem("nexora_history", JSON.stringify(history));
}

export default function Sidebar() {
  const location = useLocation();
  const navigate = useNavigate();
  const [historyOpen, setHistoryOpen] = useState(false);
  const [tokenOpen, setTokenOpen] = useState(false);
  const [tokenInput, setTokenInput] = useState(getAuthToken() ?? "");
  const history = getHistory();

  const isHome = location.pathname === "/";

  return (
    <aside className="flex h-screen w-[240px] shrink-0 flex-col border-r border-slate-200 bg-white">
      {/* Logo */}
      <div className="flex items-center gap-2 px-5 pt-5 pb-2">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-600 text-sm font-bold text-white">
          N
        </div>
        <button
          onClick={() => {
            const sidebar = document.getElementById("mobile-sidebar");
            if (sidebar) sidebar.classList.add("hidden");
          }}
          className="ml-auto rounded-lg p-1 text-slate-400 hover:bg-slate-100 lg:hidden"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <path d="M18 6L6 18M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* Nav items */}
      <nav className="mt-4 flex-1 overflow-y-auto px-3">
        <button
          onClick={() => navigate("/")}
          className="mb-1 flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-blue-600 transition hover:bg-blue-50"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <path d="M12 5v14M5 12h14" />
          </svg>
          New Thread
        </button>

        <Link
          to="/"
          className={`mb-1 flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition ${
            isHome
              ? "bg-slate-100 text-slate-900"
              : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
          }`}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M3 9.5L12 4l9 5.5" />
            <path d="M19 13v6a1 1 0 01-1 1H6a1 1 0 01-1-1v-6" />
          </svg>
          Home
        </Link>

        <button
          onClick={() => setHistoryOpen((v) => !v)}
          className="mb-1 flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-slate-600 transition hover:bg-slate-50 hover:text-slate-900"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <circle cx="12" cy="12" r="10" />
            <path d="M12 6v6l4 2" />
          </svg>
          History
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            className={`ml-auto transition ${historyOpen ? "rotate-180" : ""}`}
          >
            <path d="M6 9l6 6 6-6" />
          </svg>
        </button>

        {historyOpen && (
          <div className="mb-2 ml-3 space-y-0.5 border-l border-slate-200 pl-3">
            {history.length === 0 ? (
              <p className="py-2 text-xs text-slate-400">No searches yet</p>
            ) : (
              history.slice(0, 20).map((h) => (
                <button
                  key={h.threadId}
                  onClick={() => navigate(`/report/${h.threadId}`)}
                  className="block w-full truncate rounded-md px-2 py-1.5 text-left text-xs text-slate-500 transition hover:bg-slate-50 hover:text-slate-800"
                  title={h.domain}
                >
                  {h.domain}
                </button>
              ))
            )}
          </div>
        )}

        <Link
          to="/upload"
          className={`mb-1 flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition ${
            location.pathname === "/upload"
              ? "bg-slate-100 text-slate-900"
              : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
          }`}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8l-6-6z" />
            <path d="M14 2v6h6" />
          </svg>
          Upload Paper
        </Link>
      </nav>

      {/* Bottom section */}
      <div className="border-t border-slate-200 px-3 py-3">
        <div className="relative">
          <button
            onClick={() => setTokenOpen((v) => !v)}
            className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-slate-600 transition hover:bg-slate-50"
          >
            <div className="flex h-7 w-7 items-center justify-center rounded-full bg-blue-100 text-xs font-semibold text-blue-700">
              J
            </div>
            <span className="flex-1 truncate text-left">Janeesha</span>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <path d="M7 10l5-5 5 5M7 14l5 5 5-5" />
            </svg>
          </button>

          {tokenOpen && (
            <div className="absolute bottom-full left-0 mb-2 w-full rounded-xl border border-slate-200 bg-white p-3 shadow-lg">
              <p className="mb-2 text-xs text-slate-500">API token for testing</p>
              <input
                value={tokenInput}
                onChange={(e) => setTokenInput(e.target.value)}
                placeholder="eyJhbGciOi..."
                className="mb-2 w-full rounded-md border border-slate-200 px-2 py-1.5 text-xs outline-none focus:border-blue-500"
              />
              <div className="flex gap-2">
                <button
                  onClick={() => {
                    setAuthToken(tokenInput);
                    setTokenOpen(false);
                  }}
                  className="flex-1 rounded-md bg-blue-600 px-2 py-1.5 text-xs font-medium text-white hover:bg-blue-700"
                >
                  Save
                </button>
                <button
                  onClick={() => {
                    clearAuthToken();
                    setTokenInput("");
                    setTokenOpen(false);
                  }}
                  className="flex-1 rounded-md border border-slate-200 px-2 py-1.5 text-xs text-slate-600 hover:bg-slate-50"
                >
                  Clear
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </aside>
  );
}
