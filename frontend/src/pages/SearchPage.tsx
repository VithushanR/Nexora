import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { startResearch, ApiError } from "../api/client";
import { addHistory } from "../components/Sidebar";

const EXAMPLES = [
  "AI for early crop disease detection",
  "Machine learning for sepsis prediction",
  "Transformer models for low-resource languages",
  "Wearable sensors for fall detection in the elderly",
];

export default function SearchPage() {
  const [domain, setDomain] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  async function runSearch(value: string) {
    const trimmed = value.trim();
    if (!trimmed) return;
    setLoading(true);
    setError(null);
    try {
      const { thread_id } = await startResearch(trimmed);
      addHistory(thread_id, trimmed);
      navigate(`/select/${thread_id}`);
    } catch (e) {
      setError(
        e instanceof ApiError ? e.message : "Could not start the search. Please try again."
      );
      setLoading(false);
    }
  }

  return (
    <div className="flex h-full flex-col items-center px-6 pt-[18vh]">
      {/* Logo + tagline */}
      <div className="mb-2 flex items-center gap-2">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-600 text-lg font-bold text-white">
          N
        </div>
        <span className="text-2xl font-semibold text-slate-900">Nexora</span>
      </div>
      <h1 className="mb-10 text-center text-3xl font-bold text-slate-900">
        Research starts here
      </h1>

      {/* Search bar */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          runSearch(domain);
        }}
        className="w-full max-w-2xl"
      >
        <div className="flex items-center gap-2 rounded-2xl border border-slate-200 bg-white px-5 py-4 shadow-sm ring-1 ring-slate-900/5 transition-all focus-within:border-blue-400 focus-within:ring-2 focus-within:ring-blue-100">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" className="shrink-0 text-slate-400">
            <circle cx="11" cy="11" r="7" stroke="currentColor" strokeWidth="2" />
            <path d="M21 21l-4.3-4.3" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
          </svg>
          <input
            value={domain}
            onChange={(e) => setDomain(e.target.value)}
            placeholder="e.g. AI for early crop disease detection"
            className="flex-1 bg-transparent text-base text-slate-900 outline-none placeholder:text-slate-400"
          />
          <button
            type="submit"
            disabled={loading || !domain.trim()}
            className="rounded-xl bg-blue-600 px-5 py-2 text-sm font-medium text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? "Searching..." : "Search"}
          </button>
        </div>
      </form>

      {error && <p className="mt-4 text-sm text-rose-600">{error}</p>}

      {/* Example chips */}
      <div className="mt-8 flex max-w-2xl flex-wrap justify-center gap-2">
        {EXAMPLES.map((ex) => (
          <button
            key={ex}
            onClick={() => {
              setDomain(ex);
              runSearch(ex);
            }}
            className="flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-4 py-2 text-sm text-slate-600 transition hover:border-blue-300 hover:text-blue-700"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" className="text-blue-400">
              <circle cx="11" cy="11" r="7" />
              <path d="M21 21l-4.3-4.3" />
            </svg>
            {ex}
          </button>
        ))}
      </div>

      {/* Bottom tagline */}
      <div className="mt-auto pb-8 pt-16">
        <div className="flex items-center gap-4">
          <div className="h-px w-16 bg-slate-200" />
          <p className="text-sm text-slate-400">The new standard for academic research</p>
          <div className="h-px w-16 bg-slate-200" />
        </div>
      </div>
    </div>
  );
}
