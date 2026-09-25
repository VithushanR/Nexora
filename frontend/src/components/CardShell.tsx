// Part B: the same centered, rounded-card container across every stage of
// the search/selection/report flow. As of items 4/5/7, that whole flow --
// chat, screening progress, the paper-selection popup, synthesis progress,
// and the final report -- lives inside SearchPage as one persistent thread,
// so this shell now really only wraps SearchPage. The shell itself is
// fixed to the available height (App.tsx's <main> is overflow-hidden for
// exactly this reason); scrolling happens inside the card, supplied by
// each page's own content.
import type { ReactNode } from "react";

interface CardShellProps {
  children: ReactNode;
  /** Wider pages (the paper-selection grid) can opt into more width. */
  maxWidthClassName?: string;
  /**
   * An optional persistent element rendered as its OWN separate rounded
   * box below the main card -- not nested inside the card's border. Only
   * SearchPage uses this today (its message input bar); omitted, CardShell
   * behaves exactly as before (a single card filling the available height).
   */
  footer?: ReactNode;
  /**
   * Overrides the footer box's own border/background classes (e.g. for a
   * mode-dependent accent tint). The caller supplies the whole border/bg
   * treatment here rather than nesting another bordered box inside the
   * footer -- that nesting is exactly the double-border look this shell
   * exists to avoid.
   */
  footerClassName?: string;
}

const DEFAULT_FOOTER_CLASSNAME = "border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900";

export default function CardShell({
  children,
  maxWidthClassName = "max-w-5xl",
  footer,
  footerClassName = DEFAULT_FOOTER_CLASSNAME,
}: CardShellProps) {
  return (
    <div className="flex h-full items-center justify-center bg-gradient-to-b from-violet-50/70 via-slate-50 to-white p-3 dark:from-slate-950 dark:via-slate-950 dark:to-slate-900 sm:p-6 lg:p-8">
      <div className={`flex h-full w-full ${maxWidthClassName} flex-col gap-3`}>
        <div className="flex flex-1 flex-col overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
          {children}
        </div>
        {footer && (
          <div className={`shrink-0 overflow-hidden rounded-2xl border shadow-sm transition-colors ${footerClassName}`}>
            {footer}
          </div>
        )}
      </div>
    </div>
  );
}
