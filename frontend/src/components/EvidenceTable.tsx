// Renders the structured evidence table produced by Agent 3 (synthesis_integrity).
// TODO: define props from types/index.ts EvidenceRow type, implement table markup.

import type { EvidenceRow } from "../types";

export default function EvidenceTable({ rows }: { rows: EvidenceRow[] }) {
  if (rows.length === 0) {
    return <p className="text-sm text-slate-500">No evidence rows available.</p>;
  }

  return (
    <div className="overflow-x-auto rounded-xl border border-slate-200">
      <table className="w-full text-left text-sm">
        <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th className="px-4 py-3">Paper</th>
            <th className="px-4 py-3">Methodology</th>
            <th className="px-4 py-3">Results</th>
            <th className="px-4 py-3">Full text</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((row, i) => (
            <tr key={i} className="align-top">
              <td className="max-w-[220px] px-4 py-3">
                <p className="font-medium text-slate-900">{row.title}</p>
                <p className="mt-1 text-xs text-slate-500">
                  {row.source} · {row.year ?? "n.d."}
                </p>
                {row.retracted && (
                  <span className="mt-1 inline-block rounded-full bg-rose-50 px-2 py-0.5 text-xs font-medium text-rose-700 ring-1 ring-inset ring-rose-200">
                    Retracted
                  </span>
                )}
                {row.retracted === null && (
                  <span className="mt-1 inline-block rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-500 ring-1 ring-inset ring-slate-200">
                    Retraction status unknown
                  </span>
                )}
              </td>
              <td className="max-w-[280px] px-4 py-3 text-slate-600">{row.methodology_summary}</td>
              <td className="max-w-[280px] px-4 py-3 text-slate-600">{row.results_summary}</td>
              <td className="px-4 py-3">
                {row.full_text_available ? (
                  <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-700 ring-1 ring-inset ring-emerald-200">
                    {row.full_text_strategy}
                  </span>
                ) : (
                  <span className="rounded-full bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-700 ring-1 ring-inset ring-amber-200">
                    Abstract only
                  </span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}