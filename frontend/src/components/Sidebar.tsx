import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import GoogleSignInButton from "../auth/GoogleSignInButton";

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
  const { status, user, signOut } = useAuth();
  const [historyOpen, setHistoryOpen] = useState(false);
  const [accountMenuOpen, setAccountMenuOpen] = useState(false);
  const history = getHistory();

  const accountLabel = user?.name || user?.email || "Signed in";
  const accountInitial = accountLabel.charAt(0).toUpperCase();

  const isHome = location.pathname === "/";

  return (
    <aside className="flex h-screen w-[260px] shrink-0 flex-col border-r border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
      {/* Logo */}
      <div className="flex items-center gap-2.5 px-5 pt-5 pb-4">
        <img
          src="/nexora-logo.png"
          alt="Nexora"
          className="h-9 w-9 rounded-xl object-cover"
        />
        <span className="text-lg font-semibold text-slate-800 dark:text-white">Nexora</span>
        <button
          onClick={() => {
            const sidebar = document.getElementById("sidebar");
            if (sidebar) sidebar.classList.add("-translate-x-full");
          }}
          className="ml-auto rounded-lg p-1 text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 lg:hidden"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <path d="M18 6L6 18M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* New search button */}
      <div className="px-4 pb-5">
        <button
          onClick={() => navigate("/")}
          className="flex w-full items-center justify-center gap-2 rounded-xl bg-violet-600 px-4 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-violet-500 active:scale-[0.98]"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
            <path d="M12 5v14M5 12h14" />
          </svg>
          New search
        </button>
      </div>

      {/* WORKSPACE section */}
      <nav className="flex-1 overflow-y-auto px-4">
        <p className="mb-2 px-2 text-[11px] font-semibold uppercase tracking-[0.15em] text-slate-400 dark:text-slate-500">
          Workspace
        </p>

        <Link
          to="/"
          className={`mb-0.5 flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition ${
            isHome
              ? "border-l-[3px] border-violet-500 bg-violet-50 pl-[9px] text-slate-900 dark:bg-violet-950/40 dark:text-white"
              : "text-slate-600 hover:bg-slate-50 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-white"
          }`}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <circle cx="11" cy="11" r="8" />
            <path d="M21 21l-4.35-4.35" />
          </svg>
          Evidence review
        </Link>

        <button
          onClick={() => setHistoryOpen((v) => !v)}
          className="mb-0.5 flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-slate-600 transition hover:bg-slate-50 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-white"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <rect x="2" y="3" width="20" height="18" rx="2" />
            <path d="M2 9h20" />
          </svg>
          Saved research
          <svg
            width="12"
            height="12"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.5"
            strokeLinecap="round"
            className={`ml-auto transition ${historyOpen ? "rotate-180" : ""}`}
          >
            <path d="M6 9l6 6 6-6" />
          </svg>
        </button>

        {historyOpen && (
          <div className="mb-2 ml-3 space-y-0.5 border-l border-slate-200 pl-3 dark:border-slate-700">
            {history.length === 0 ? (
              <p className="py-2 text-xs text-slate-400">No searches yet</p>
            ) : (
              history.slice(0, 20).map((h) => (
                <button
                  key={h.threadId}
                  onClick={() => navigate(`/report/${h.threadId}`)}
                  className="block w-full truncate rounded-md px-2 py-1.5 text-left text-xs text-slate-500 transition hover:bg-slate-50 hover:text-slate-800 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-200"
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
          className={`mb-0.5 flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition ${
            location.pathname === "/upload"
              ? "border-l-[3px] border-violet-500 bg-violet-50 pl-[9px] text-slate-900 dark:bg-violet-950/40 dark:text-white"
              : "text-slate-600 hover:bg-slate-50 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-white"
          }`}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8l-6-6z" />
            <path d="M14 2v6h6" />
          </svg>
          Uploaded sources
        </Link>
      </nav>

      {/* CURRENT PROJECT */}
      <div className="border-t border-slate-100 px-4 py-4 dark:border-slate-800">
        <p className="mb-2 px-2 text-[11px] font-semibold uppercase tracking-[0.15em] text-slate-400 dark:text-slate-500">
          Current Project
        </p>
        <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 dark:border-slate-700 dark:bg-slate-800">
          <div className="flex items-center gap-2.5">
            <img src="/nexora-logo.png" alt="Nexora" className="h-8 w-8 rounded-lg object-cover" />
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium text-slate-800 dark:text-white">Research</p>
              <p className="text-xs text-slate-400 dark:text-slate-500">Ready to explore</p>
            </div>
          </div>
        </div>
      </div>

      {/* Account */}
      <div className="border-t border-slate-200 px-3 py-3 dark:border-slate-800">
        {status === "signed-in" ? (
          <div className="relative">
            <button
              onClick={() => setAccountMenuOpen((v) => !v)}
              className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-slate-600 transition hover:bg-slate-50 dark:text-slate-400 dark:hover:bg-slate-800"
            >
              {user?.picture ? (
                <img
                  src={user.picture}
                  alt=""
                  referrerPolicy="no-referrer"
                  className="h-7 w-7 rounded-full object-cover"
                />
              ) : (
                <div className="flex h-7 w-7 items-center justify-center rounded-full bg-violet-100 text-xs font-semibold text-violet-700 dark:bg-violet-900 dark:text-violet-300">
                  {accountInitial}
                </div>
              )}
              <span className="flex-1 truncate text-left">{accountLabel}</span>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <path d="M7 10l5-5 5 5M7 14l5 5 5-5" />
              </svg>
            </button>

            {accountMenuOpen && (
              <div className="absolute bottom-full left-0 mb-2 w-full rounded-xl border border-slate-200 bg-white p-1.5 shadow-lg dark:border-slate-700 dark:bg-slate-800">
                <button
                  onClick={() => {
                    signOut();
                    setAccountMenuOpen(false);
                  }}
                  className="w-full rounded-md px-3 py-2 text-left text-sm text-slate-600 hover:bg-slate-50 dark:text-slate-400 dark:hover:bg-slate-700"
                >
                  Sign out
                </button>
              </div>
            )}
          </div>
        ) : (
          <div className="flex justify-center px-1">
            <GoogleSignInButton width={210} />
          </div>
        )}
      </div>
    </aside>
  );
}
