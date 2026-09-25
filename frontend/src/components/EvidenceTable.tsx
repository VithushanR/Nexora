import { useState } from "react";
import type { EvidenceRow } from "../types";

export default function EvidenceTable({ rows }: { rows: EvidenceRow[] }) {
  const [collapsed, setCollapsed] = useState(false);

  if (rows.length === 0) {
    return <p className="text-sm text-slate-500 dark:text-slate-400">No evidence rows available.</p>;
  }

  return (
    <div className="my-6 overflow-hidden rounded-2xl border border-slate-200 bg-slate-50/50 shadow-sm dark:border-slate-700 dark:bg-slate-800/30">
      {/* Section header */}
      <div className="px-6 pt-5 pb-4">
        <div className="flex items-start justify-between">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.15em] text-slate-400 dark:text-slate-500">
              Source Synthesis
            </p>
            <h3 className="mt-1 text-xl font-semibold text-slate-900 dark:text-white">Evidence table</h3>
          </div>
          <button
            onClick={() => setCollapsed((v) => !v)}
            className="flex items-center gap-1 rounded-md px-2 py-1 text-sm text-slate-500 transition hover:bg-slate-100 hover:text-slate-700 dark:text-slate-400 dark:hover:bg-slate-700 dark:hover:text-slate-200"
          >
            {collapsed ? "Expand" : "Collapse"}
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
              className={`transition ${collapsed ? "rotate-180" : ""}`}
            >
              <path d="M18 15l-6-6-6 6" />
            </svg>
          </button>
        </div>
      </div>

      {/* Table body */}
      {!collapsed && (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="bg-gradient-to-r from-violet-600 via-violet-500 to-purple-500">
                <th className="px-6 py-3.5 text-xs font-bold uppercase tracking-wider text-white">Paper</th>
                <th className="px-6 py-3.5 text-xs font-bold uppercase tracking-wider text-white">Methodology</th>
                <th className="px-6 py-3.5 text-xs font-bold uppercase tracking-wider text-white">Results</th>
                <th className="px-6 py-3.5 text-xs font-bold uppercase tracking-wider text-white">Full Text</th>
              </tr>
            </thead>
            <tbody className="bg-white dark:bg-slate-800/50">
              {rows.map((row, i) => (
                <tr
                  key={i}
                  className={`align-top transition ${
                    i < rows.length - 1 ? "border-b border-slate-100 dark:border-slate-700" : ""
                  }`}
                >
                  <td className="max-w-[220px] px-6 py-4">
                    <p className="font-medium text-slate-800 dark:text-slate-200">{row.title}</p>
                    <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
                      {row.source} ({row.year ?? "n.d."})
                    </p>
                    {row.retracted && (
                      <span className="mt-1.5 inline-block rounded-full bg-rose-50 px-2 py-0.5 text-xs font-medium text-rose-700 ring-1 ring-inset ring-rose-200 dark:bg-rose-900/30 dark:text-rose-400 dark:ring-rose-800">
                        Retracted
                      </span>
                    )}
                  </td>
                  <td className="max-w-[280px] px-6 py-4 text-slate-600 dark:text-slate-300">{row.methodology_summary}</td>
                  <td className="max-w-[320px] px-6 py-4 text-slate-600 dark:text-slate-300">{row.results_summary}</td>
                  <td className="px-6 py-4">
                    {row.full_text_available ? (
                      <span className="inline-flex items-center gap-1 font-medium text-violet-600 dark:text-violet-400">
                        Open PDF
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M7 17L17 7M7 7h10v10" />
                        </svg>
                      </span>
                    ) : (
                      <span className="text-slate-400 dark:text-slate-500">Abstract only</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
