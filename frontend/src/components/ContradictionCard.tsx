// Displays a single contradiction flagged by Agent 3 between two or more papers.
// TODO: define props from types/index.ts Contradiction type, implement markup.

import type { Contradiction } from "../types";

export default function ContradictionCard({ item }: { item: Contradiction }) {
  return (
    <div className="rounded-xl border border-amber-200 bg-amber-50/40 p-4">
      <p className="mb-2 text-sm text-slate-700">{item.description}</p>
      <div className="grid gap-2 sm:grid-cols-2">
        <div className="rounded-lg bg-white p-3 text-xs">
          <p className="mb-1 font-medium text-slate-900">{item.paper_a_title}</p>
          <p className="text-slate-600">{item.paper_a_claim}</p>
        </div>
        <div className="rounded-lg bg-white p-3 text-xs">
          <p className="mb-1 font-medium text-slate-900">{item.paper_b_title}</p>
          <p className="text-slate-600">{item.paper_b_claim}</p>
        </div>
      </div>
    </div>
  );
}