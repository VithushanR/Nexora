import type { CandidatePaper } from "../types";

interface PaperCardProps {
  candidate: CandidatePaper;
  index: number;
  selected: boolean;
  disabled?: boolean;
  onSelectionChange: (index: number, selected: boolean) => void;
}

function displayValue(value: string | number | null): string | number {
  return value ?? "Not available";
}

export default function PaperCard({
  candidate,
  index,
  selected,
  disabled = false,
  onSelectionChange,
}: PaperCardProps) {
  const checkboxId = `candidate-${index}`;

  return (
    <article
      className={`rounded-2xl border p-5 shadow-sm transition ${
        selected
          ? "border-violet-300 bg-violet-50/50 dark:border-violet-700 dark:bg-violet-950/30"
          : "border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-800/50"
      }`}
    >
      <div className="flex items-start gap-3">
        <input
          id={checkboxId}
          type="checkbox"
          checked={selected}
          disabled={disabled}
          onChange={(event) => onSelectionChange(index, event.target.checked)}
          className="mt-1 h-4 w-4 rounded border-slate-300 text-violet-600 accent-violet-600 focus:ring-violet-500 dark:border-slate-600"
        />
        <div className="min-w-0 flex-1">
          <label htmlFor={checkboxId} className="cursor-pointer text-lg font-semibold text-slate-900 dark:text-white">
            {displayValue(candidate.title)}
          </label>
          <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">
            {displayValue(candidate.source)} · {displayValue(candidate.year)}
          </p>
        </div>
      </div>

      <dl className="mt-4 space-y-3 text-sm text-slate-700 dark:text-slate-300">
        <div>
          <dt className="font-medium text-slate-900 dark:text-slate-200">Abstract</dt>
          <dd className="mt-1 whitespace-pre-wrap">{displayValue(candidate.abstract)}</dd>
        </div>
        <div>
          <dt className="font-medium text-slate-900 dark:text-slate-200">Screening verdict</dt>
          <dd className="mt-1">{displayValue(candidate.verdict)}</dd>
        </div>
        <div>
          <dt className="font-medium text-slate-900 dark:text-slate-200">Screening reason</dt>
          <dd className="mt-1">{displayValue(candidate.reason)}</dd>
        </div>
        <div>
          <dt className="font-medium text-slate-900 dark:text-slate-200">Supporting quote</dt>
          <dd className="mt-1">{displayValue(candidate.quote)}</dd>
        </div>
        <div>
          <dt className="font-medium text-slate-900 dark:text-slate-200">DOI</dt>
          <dd className="mt-1 break-all">{displayValue(candidate.doi)}</dd>
        </div>
        <div>
          <dt className="font-medium text-slate-900 dark:text-slate-200">Pre-rank score</dt>
          <dd className="mt-1">{displayValue(candidate.prerank_score)}</dd>
        </div>
      </dl>
    </article>
  );
}
