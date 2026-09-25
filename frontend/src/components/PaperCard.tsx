import type { CandidatePaper } from "../types";

type RelevanceTier = "high" | "mid" | "low";

// Same tier bands as the card tint uses to derive the badge color --
// keeping this in one place is what guarantees they always agree.
// Bands: >=70 high (green), >=40 and <70 mid (yellow), <40 low (red).
function relevanceTier(percent: number | null): RelevanceTier {
  if (percent === null) return "low";
  if (percent >= 70) return "high";
  if (percent >= 40) return "mid";
  return "low";
}

const TIER_STYLES: Record<RelevanceTier, { card: string; badge: string; ring: string }> = {
  high: {
    card: "border-emerald-200 bg-emerald-50 dark:border-emerald-800/50 dark:bg-emerald-950/20",
    badge: "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800/50 dark:bg-emerald-950/30 dark:text-emerald-300",
    ring: "ring-emerald-400 dark:ring-emerald-600",
  },
  mid: {
    card: "border-amber-200 bg-amber-50 dark:border-amber-800/50 dark:bg-amber-950/20",
    badge: "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-800/50 dark:bg-amber-950/30 dark:text-amber-300",
    ring: "ring-amber-400 dark:ring-amber-600",
  },
  low: {
    card: "border-red-200 bg-red-50 dark:border-red-800/50 dark:bg-red-950/20",
    badge: "border-red-200 bg-red-50 text-red-700 dark:border-red-800/50 dark:bg-red-950/30 dark:text-red-300",
    ring: "ring-red-400 dark:ring-red-600",
  },
};

interface PaperCardProps {
  candidate: CandidatePaper;
  index: number;
  selected: boolean;
  disabled?: boolean;
  onSelectionChange: (index: number, selected: boolean) => void;
  onExpand: (index: number) => void;
}

export default function PaperCard({
  candidate,
  index,
  selected,
  disabled = false,
  onSelectionChange,
  onExpand,
}: PaperCardProps) {
  const tier = relevanceTier(candidate.relevance_percent);
  const style = TIER_STYLES[tier];
  const checkboxId = `candidate-${index}`;

  return (
    <article
      className={`flex flex-col gap-3 rounded-2xl border p-4 shadow-sm transition hover:shadow-md ${style.card} ${
        selected ? `ring-2 ${style.ring}` : ""
      }`}
    >
      <div className="flex items-start gap-2.5">
        <input
          id={checkboxId}
          type="checkbox"
          checked={selected}
          disabled={disabled}
          onChange={(event) => onSelectionChange(index, event.target.checked)}
          className="mt-1 h-4 w-4 shrink-0 rounded border-slate-300 text-violet-600 accent-violet-600 focus:ring-violet-500 dark:border-slate-600"
        />
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-2">
            <label
              htmlFor={checkboxId}
              className="min-w-0 cursor-pointer text-sm font-semibold leading-snug text-slate-900 dark:text-white"
              style={{
                display: "-webkit-box",
                WebkitBoxOrient: "vertical",
                WebkitLineClamp: 2,
                overflow: "hidden",
              }}
            >
              {candidate.title ?? "Untitled"}
            </label>
            <div className="flex shrink-0 items-center gap-1">
              <span
                title="Relevance is relative to this search's own results only -- not comparable across different searches."
                className={`whitespace-nowrap rounded-full border px-2 py-0.5 text-[10px] font-semibold ${style.badge}`}
              >
                {candidate.relevance_percent !== null ? `${candidate.relevance_percent}% relevant` : "No strong match"}
              </span>
              <button
                type="button"
                onClick={() => onExpand(index)}
                title="Expand full details"
                aria-label="Expand full details"
                className="shrink-0 rounded-lg p-1.5 text-slate-500 transition hover:bg-black/5 dark:text-slate-400 dark:hover:bg-white/5"
              >
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7" />
                </svg>
              </button>
            </div>
          </div>
          <p className="mt-1 text-[11px] text-slate-400 dark:text-slate-500">
            {candidate.source ?? "unknown source"} &middot; {candidate.year ?? "n/a"}
          </p>
        </div>
      </div>

      {/* Teaser: reason text, fixed 4-line clamp, no in-card expansion --
          the fullscreen modal (expand icon above) is the only "read more"
          path. Ellipsis rather than a fade on overflow: a fade with no
          follow-up control right at the cut point reads as a dead end. */}
      <p
        className="text-xs italic leading-snug text-slate-600 dark:text-slate-400"
        style={{
          display: "-webkit-box",
          WebkitBoxOrient: "vertical",
          WebkitLineClamp: 4,
          overflow: "hidden",
          textOverflow: "ellipsis",
        }}
      >
        &ldquo;{candidate.reason ?? "No screening rationale available."}&rdquo;
      </p>
    </article>
  );
}
