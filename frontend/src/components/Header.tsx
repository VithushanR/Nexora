import { useState } from "react";
import { Link } from "react-router-dom";
import { getAuthToken, setAuthToken, clearAuthToken } from "../api/client";

export default function Header() {
  const [open, setOpen] = useState(false);
  const [tokenInput, setTokenInput] = useState(getAuthToken() ?? "");

  return (
    <header className="sticky top-0 z-40 border-b border-slate-200 bg-white/80 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-3">
        <Link to="/" className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-md bg-blue-600 text-sm font-bold text-white">
            N
          </div>
          <span className="text-lg font-semibold text-slate-900">Nexora</span>
        </Link>

        <div className="relative">
          <button
            onClick={() => setOpen((v) => !v)}
            className="rounded-full border border-slate-200 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50"
          >
            {getAuthToken() ? "API token set" : "Set API token"}
          </button>
          {open && (
            <div className="absolute right-0 mt-2 w-72 rounded-xl border border-slate-200 bg-white p-3 shadow-lg">
              <p className="mb-2 text-xs text-slate-500">
                Paste a JWT from the auth service (Part D) for testing.
              </p>
              <input
                value={tokenInput}
                onChange={(e) => setTokenInput(e.target.value)}
                placeholder="eyJhbGciOi..."
                className="mb-2 w-full rounded-md border border-slate-200 px-2 py-1.5 text-sm outline-none focus:border-blue-500"
              />
              <div className="flex gap-2">
                <button
                  onClick={() => {
                    setAuthToken(tokenInput);
                    setOpen(false);
                  }}
                  className="flex-1 rounded-md bg-blue-600 px-2 py-1.5 text-xs font-medium text-white hover:bg-blue-700"
                >
                  Save
                </button>
                <button
                  onClick={() => {
                    clearAuthToken();
                    setTokenInput("");
                    setOpen(false);
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
    </header>
  );
}