// The escape hatch for a user who wants to read everything about one
// candidate at once -- full abstract plus every screening detail.
// Content only: no backdrop, no fixed positioning, no own Escape/close
// handling. It renders INSIDE CandidateSelectionModal's single shared
// panel, which owns the modal shell, the header (back + close), and the
// grid/detail crossfade -- this used to be its own separate `fixed
// inset-0` modal, which stacked a second popup on top of the selection
// grid's popup instead of transforming it in place.
import type { CandidatePaper } from "../types";

interface CandidateDetailViewProps {
  candidate: CandidatePaper;
}

const VERDICT_LABELS: Record<string, string> = {
  INCLUDE: "Include",
  EXCLUDE: "Exclude",
  UNCERTAIN: "Uncertain",
};

export default function CandidateDetailView({ candidate }: CandidateDetailViewProps) {
  return (
    <div className="p-6">
      <div className="mb-5 flex flex-wrap items-center gap-2 text-xs">
        <span className="rounded-full bg-violet-100 px-2.5 py-1 font-semibold text-violet-700 dark:bg-violet-900/40 dark:text-violet-300">
          {candidate.relevance_percent !== null ? `${candidate.relevance_percent}% relevant` : "No strong match found"}
        </span>
        {candidate.verdict && (
          <span className="rounded-full bg-slate-100 px-2.5 py-1 font-semibold text-slate-600 dark:bg-slate-700 dark:text-slate-300">
            {VERDICT_LABELS[candidate.verdict] ?? candidate.verdict}
          </span>
        )}
        <span className="text-slate-400 dark:text-slate-500">
          {candidate.source ?? "unknown source"} &middot; {candidate.year ?? "n/a"}
        </span>
      </div>

      <dl className="space-y-4 text-sm">
        <div>
          <dt className="mb-1 font-medium text-slate-900 dark:text-slate-200">Abstract</dt>
          <dd className="whitespace-pre-wrap leading-relaxed text-slate-600 dark:text-slate-400">
            {candidate.abstract ?? "Not available"}
          </dd>
        </div>
        <div>
          <dt className="mb-1 font-medium text-slate-900 dark:text-slate-200">Screening reason</dt>
          <dd className="text-slate-600 dark:text-slate-400">{candidate.reason ?? "Not available"}</dd>
        </div>
        <div>
          <dt className="mb-1 font-medium text-slate-900 dark:text-slate-200">Supporting quote</dt>
          <dd className="italic text-slate-600 dark:text-slate-400">
            {candidate.quote ? `“${candidate.quote}”` : "Not available"}
          </dd>
        </div>
        <div>
          <dt className="mb-1 font-medium text-slate-900 dark:text-slate-200">DOI</dt>
          <dd className="break-all text-slate-600 dark:text-slate-400">{candidate.doi ?? "Not available"}</dd>
        </div>
        <div>
          <dt className="mb-1 font-medium text-slate-900 dark:text-slate-200">Source link</dt>
          <dd>
            {candidate.paper_url ? (
              <a
                href={candidate.paper_url}
                target="_blank"
                rel="noreferrer"
                className="break-all text-violet-600 underline hover:text-violet-500 dark:text-violet-400 dark:hover:text-violet-300"
              >
                {candidate.paper_url}
              </a>
            ) : (
              <span className="text-slate-400 dark:text-slate-500">No link available</span>
            )}
          </dd>
        </div>
      </dl>
    </div>
  );
}
