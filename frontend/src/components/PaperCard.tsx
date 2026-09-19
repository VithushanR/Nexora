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
    <article className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-start gap-3">
        <input
          id={checkboxId}
          type="checkbox"
          checked={selected}
          disabled={disabled}
          onChange={(event) => onSelectionChange(index, event.target.checked)}
          className="mt-1 h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
        />
        <div className="min-w-0 flex-1">
          <label htmlFor={checkboxId} className="cursor-pointer text-lg font-semibold text-slate-900">
            {displayValue(candidate.title)}
          </label>
          <p className="mt-1 text-sm text-slate-600">
            {displayValue(candidate.source)} · {displayValue(candidate.year)}
          </p>
        </div>
      </div>

      <dl className="mt-4 space-y-3 text-sm text-slate-700">
        <div>
          <dt className="font-medium text-slate-900">Abstract</dt>
          <dd className="mt-1 whitespace-pre-wrap">{displayValue(candidate.abstract)}</dd>
        </div>
        <div>
          <dt className="font-medium text-slate-900">Screening verdict</dt>
          <dd className="mt-1">{displayValue(candidate.verdict)}</dd>
        </div>
        <div>
          <dt className="font-medium text-slate-900">Screening reason</dt>
          <dd className="mt-1">{displayValue(candidate.reason)}</dd>
        </div>
        <div>
          <dt className="font-medium text-slate-900">Supporting quote</dt>
          <dd className="mt-1">{displayValue(candidate.quote)}</dd>
        </div>
        <div>
          <dt className="font-medium text-slate-900">DOI</dt>
          <dd className="mt-1 break-all">{displayValue(candidate.doi)}</dd>
        </div>
        <div>
          <dt className="font-medium text-slate-900">Pre-rank score</dt>
          <dd className="mt-1">{displayValue(candidate.prerank_score)}</dd>
        </div>
      </dl>
    </article>
  );
}