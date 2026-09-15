// Displays a single candidate/selected paper (title, authors, abstract snippet)
// with a select checkbox, used by SelectionPage.
// TODO: define props from types/index.ts Paper type, implement markup.

import type { Candidate } from "../types";
import VerdictBadge from "./VerdictBadge";

interface Props {
  candidate: Candidate;
  selected: boolean;
  onToggle: () => void;
}

export default function PaperCard({ candidate, selected, onToggle }: Props) {
  return (
    <label
      className={`flex cursor-pointer gap-3 rounded-xl border p-4 transition ${
        selected ? "border-blue-300 bg-blue-50/40" : "border-slate-200 bg-white hover:border-slate-300"
      }`}
    >
      <input
        type="checkbox"
        checked={selected}
        onChange={onToggle}
        className="mt-1 h-4 w-4 shrink-0 rounded border-slate-300 text-blue-600 focus:ring-blue-500"
      />
      <div className="min-w-0 flex-1">
        <div className="mb-1 flex flex-wrap items-center gap-2">
          <h3 className="font-medium text-slate-900">{candidate.title || "(untitled)"}</h3>
          <VerdictBadge verdict={candidate.verdict} />
        </div>
        <p className="mb-2 text-xs text-slate-500">
          {candidate.source} · {candidate.year ?? "n.d."}
          {candidate.doi ? ` · ${candidate.doi}` : ""}
        </p>
        {candidate.abstract && (
          <p className="mb-2 line-clamp-3 text-sm text-slate-600">{candidate.abstract}</p>
        )}
        {candidate.quote && (
          <blockquote className="border-l-2 border-blue-200 pl-3 text-xs italic text-slate-500">
            "{candidate.quote}"
          </blockquote>
        )}
      </div>
    </label>
  );
}