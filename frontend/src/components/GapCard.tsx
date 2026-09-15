// Displays a single research gap surfaced by Agent 4 (gap_discovery).
// TODO: define props from types/index.ts Gap type, implement markup.

import type { Gap } from "../types";

export default function GapCard({ gap }: { gap: Gap }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="font-medium text-slate-900">{gap.theme}</h3>
        <span className="rounded-full bg-blue-50 px-2 py-0.5 text-xs font-medium text-blue-700 ring-1 ring-inset ring-blue-200">
          {gap.support_count} papers
        </span>
      </div>
      <ul className="list-disc space-y-1 pl-4 text-xs text-slate-500">
        {gap.supporting_paper_titles.map((t, i) => (
          <li key={i}>{t}</li>
        ))}
      </ul>
    </div>
  );
}