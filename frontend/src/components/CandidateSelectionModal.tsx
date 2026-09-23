// Item 4: paper selection as a popup over the still-visible chat thread,
// not a full-page navigation. Reuses the same grid/PaperCard/pagination
// pieces the old full-page SelectionPage used -- only the framing changed.
//
// This is the ONLY modal element for the whole select-then-expand flow:
// expanding a card morphs this same panel's content from the grid into
// CandidateDetailView and back, rather than mounting a second `fixed
// inset-0` overlay on top of this one (that used to visibly stack two
// popups). "expandedIndex" is what's actually rendered; morphTo() is the
// only way it changes, and always drives it through a brief crossfade.
import { useEffect, useRef, useState } from "react";
import PaperCard from "./PaperCard";
import CandidateDetailView from "./CandidateDetailView";
import { useGridRowPagination } from "../hooks/useGridRowPagination";
import type { CandidatePaper } from "../types";

interface CandidateSelectionModalProps {
  candidates: CandidatePaper[];
  selectedIndices: number[];
  onSelectionChange: (index: number, selected: boolean) => void;
  onSubmit: () => void;
  onClose: () => void;
  isSubmitting: boolean;
  submissionError: string;
}

// A gentle ease-out curve (decelerate into rest, no bounce/overshoot) --
// the same shape used for panel/sheet transitions on polished, "premium"
// sites. Exit is quicker than entrance: content leaving reads as a flick,
// content arriving reads as a settle.
const MORPH_EASE = "cubic-bezier(0.16, 1, 0.3, 1)";
const EXIT_MS = 160;
const ENTER_MS = 280;

export default function CandidateSelectionModal({
  candidates,
  selectedIndices,
  onSelectionChange,
  onSubmit,
  onClose,
  isSubmitting,
  submissionError,
}: CandidateSelectionModalProps) {
  const { gridRef, gridStyle, isComplete, showMore } = useGridRowPagination(candidates.length);
  const [expandedIndex, setExpandedIndex] = useState<number | null>(null);
  const [morphedOut, setMorphedOut] = useState(false);
  const morphTimeoutRef = useRef<number | undefined>(undefined);

  useEffect(() => {
    return () => window.clearTimeout(morphTimeoutRef.current);
  }, []);

  function morphTo(next: number | null) {
    if (next === expandedIndex) return;
    window.clearTimeout(morphTimeoutRef.current);
    setMorphedOut(true);
    morphTimeoutRef.current = window.setTimeout(() => {
      setExpandedIndex(next);
      // Swap the content while it's still invisible, then release it back
      // to visible on the NEXT painted frame -- doing this in the same
      // tick would let React coalesce "new content" and "visible" into
      // one commit, so the browser would never paint the hidden state and
      // there'd be nothing to transition FROM.
      requestAnimationFrame(() => {
        requestAnimationFrame(() => setMorphedOut(false));
      });
    }, EXIT_MS);
  }

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      if (expandedIndex !== null) morphTo(null);
      else onClose();
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [onClose, expandedIndex]);

  const expandedCandidate = expandedIndex !== null ? candidates[expandedIndex] : null;

  return (
    <div
      // Fixed to the viewport (not the card's own content area) so the
      // blur genuinely covers everything behind the modal -- sidebar
      // included -- not just the message list it used to be scoped to.
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4 backdrop-blur-md dark:bg-black/50"
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="flex h-[78vh] w-[78vw] flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-xl dark:border-slate-700 dark:bg-slate-900">
        <div
          style={{
            opacity: morphedOut ? 0 : 1,
            transform: morphedOut ? "scale(0.985) translateY(6px)" : "scale(1) translateY(0)",
            transition: morphedOut
              ? `opacity ${EXIT_MS}ms ${MORPH_EASE}, transform ${EXIT_MS}ms ${MORPH_EASE}`
              : `opacity ${ENTER_MS}ms ${MORPH_EASE}, transform ${ENTER_MS}ms ${MORPH_EASE}`,
          }}
          className="flex min-h-0 flex-1 flex-col"
        >
          {expandedCandidate ? (
            <>
              <div className="flex shrink-0 items-center gap-3 border-b border-slate-200 px-5 py-3.5 dark:border-slate-700">
                <button
                  type="button"
                  onClick={() => morphTo(null)}
                  className="flex shrink-0 items-center gap-1.5 rounded-lg px-2 py-1.5 text-xs font-medium text-slate-500 transition hover:bg-slate-100 hover:text-slate-700 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-200"
                >
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M19 12H5M12 19l-7-7 7-7" />
                  </svg>
                  Back to results
                </button>
                <h2 className="min-w-0 flex-1 truncate text-sm font-semibold text-slate-900 dark:text-white">
                  {expandedCandidate.title ?? "Untitled"}
                </h2>
                <button
                  type="button"
                  onClick={onClose}
                  aria-label="Close"
                  className="shrink-0 rounded-lg p-1.5 text-slate-400 transition hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-800 dark:hover:text-slate-300"
                >
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                    <path d="M18 6L6 18M6 6l12 12" />
                  </svg>
                </button>
              </div>
              <div className="thin-scroll min-h-0 flex-1 overflow-y-auto">
                <CandidateDetailView candidate={expandedCandidate} />
              </div>
            </>
          ) : (
            <>
              <div className="flex shrink-0 items-center justify-between border-b border-slate-200 px-5 py-3.5 dark:border-slate-700">
                <div>
                  <h2 className="text-base font-semibold text-slate-900 dark:text-white">Select research papers</h2>
                  <p className="text-xs text-slate-500 dark:text-slate-400">
                    Select the papers you&rsquo;d like to include in your report.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={onClose}
                  aria-label="Close"
                  className="shrink-0 rounded-lg p-1.5 text-slate-400 transition hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-800 dark:hover:text-slate-300"
                >
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                    <path d="M18 6L6 18M6 6l12 12" />
                  </svg>
                </button>
              </div>

              <div className="thin-scroll min-h-0 flex-1 overflow-y-auto">
                <div className="p-5">
                  {candidates.length === 0 ? (
                    <p className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-amber-900 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-200">
                      No eligible candidate papers are available for this research session.
                    </p>
                  ) : (
                    <>
                      <div style={{ overflow: "hidden", transition: "height 0.35s ease", ...gridStyle }}>
                        <div
                          ref={gridRef}
                          aria-label="Candidate papers"
                          className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3"
                        >
                          {candidates.map((candidate, index) => (
                            <PaperCard
                              key={index}
                              candidate={candidate}
                              index={index}
                              selected={selectedIndices.includes(index)}
                              disabled={isSubmitting}
                              onSelectionChange={onSelectionChange}
                              onExpand={morphTo}
                            />
                          ))}
                        </div>
                      </div>
                      {!isComplete && (
                        <div className="mt-4 flex justify-center">
                          <button
                            type="button"
                            onClick={showMore}
                            className="rounded-full border border-slate-200 bg-white px-5 py-2 text-sm font-medium text-violet-600 shadow-sm transition hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-violet-400 dark:hover:bg-slate-700"
                          >
                            Show more
                          </button>
                        </div>
                      )}
                    </>
                  )}
                </div>
              </div>

              <div className="flex shrink-0 flex-wrap items-center gap-4 border-t border-slate-200 px-5 py-3.5 dark:border-slate-700">
                <p className="text-sm text-slate-700 dark:text-slate-300" aria-live="polite">
                  {selectedIndices.length} {selectedIndices.length === 1 ? "paper" : "papers"} selected
                </p>
                <button
                  type="button"
                  onClick={onSubmit}
                  disabled={selectedIndices.length === 0 || isSubmitting || candidates.length === 0}
                  className="rounded-xl bg-violet-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-violet-500 active:scale-[0.98] disabled:cursor-not-allowed disabled:bg-slate-300 dark:disabled:bg-slate-700 dark:disabled:text-slate-500"
                >
                  {isSubmitting ? "Submitting selection…" : "Submit selection"}
                </button>
                {submissionError && (
                  <p role="alert" className="w-full text-sm text-red-700 dark:text-red-400">
                    {submissionError}
                  </p>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
