import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import type { CSSProperties, RefObject } from "react";

// ---------------------------------------------------------------------------
// Grid-level row pagination -- independent of anything on a card itself.
// Shows 2 full rows of cards, clips the next row to a top sliver faded via
// a real CSS mask-image gradient, and reveals 2 more full rows per click
// until every candidate is shown.
// ---------------------------------------------------------------------------
const GRID_INITIAL_ROWS = 2;
const GRID_ROWS_PER_CLICK = 2;
const GRID_SLIVER_FRACTION = 0.26; // 20-30% of the peeking row's own card height

interface UseGridRowPaginationResult {
  gridRef: RefObject<HTMLDivElement>;
  gridStyle: CSSProperties;
  isComplete: boolean;
  showMore: () => void;
}

export function useGridRowPagination(itemCount: number): UseGridRowPaginationResult {
  const gridRef = useRef<HTMLDivElement>(null);
  const [revealedRows, setRevealedRows] = useState(GRID_INITIAL_ROWS);
  const [gridStyle, setGridStyle] = useState<CSSProperties>({});
  const [isComplete, setIsComplete] = useState(false);

  const recompute = useCallback(() => {
    const grid = gridRef.current;
    if (!grid || grid.children.length === 0) return;

    const cards = Array.from(grid.children) as HTMLElement[];
    const gridTop = grid.getBoundingClientRect().top;

    const rows: HTMLElement[][] = [];
    let currentTop: number | null = null;
    let currentRow: HTMLElement[] = [];
    for (const el of cards) {
      const top = el.getBoundingClientRect().top - gridTop;
      if (currentTop === null || Math.abs(top - currentTop) < 3) {
        currentRow.push(el);
        if (currentTop === null) currentTop = top;
      } else {
        rows.push(currentRow);
        currentRow = [el];
        currentTop = top;
      }
    }
    if (currentRow.length) rows.push(currentRow);

    const totalRows = rows.length;
    if (revealedRows >= totalRows) {
      setGridStyle({ height: "auto", maskImage: "none", WebkitMaskImage: "none" } as CSSProperties);
      setIsComplete(true);
      return;
    }
    setIsComplete(false);

    const lastVisibleRow = rows[revealedRows - 1];
    const fullHeight = Math.max(...lastVisibleRow.map((el) => el.getBoundingClientRect().bottom - gridTop));

    const peekRow = rows[revealedRows];
    const peekRowHeight = Math.max(...peekRow.map((el) => el.getBoundingClientRect().height));
    const sliverHeight = peekRowHeight * GRID_SLIVER_FRACTION;
    const clippedHeight = fullHeight + sliverHeight;
    const fadeStartPercent = (fullHeight / clippedHeight) * 100;
    const maskGradient = `linear-gradient(to bottom, black 0%, black ${fadeStartPercent}%, transparent 100%)`;

    setGridStyle({
      height: clippedHeight,
      maskImage: maskGradient,
      WebkitMaskImage: maskGradient,
    } as CSSProperties);
  }, [revealedRows]);

  useLayoutEffect(() => {
    recompute();
  }, [recompute, itemCount]);

  useEffect(() => {
    let resizeTimer: number | undefined;
    function onResize() {
      window.clearTimeout(resizeTimer);
      resizeTimer = window.setTimeout(recompute, 150);
    }
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      window.clearTimeout(resizeTimer);
    };
  }, [recompute]);

  const showMore = useCallback(() => setRevealedRows((r) => r + GRID_ROWS_PER_CLICK), []);

  // Reset to the initial page whenever the underlying candidate list changes
  // (e.g. a fresh load) so a stale reveal state from a previous list doesn't
  // carry over.
  useEffect(() => {
    setRevealedRows(GRID_INITIAL_ROWS);
  }, [itemCount]);

  return { gridRef, gridStyle, isComplete, showMore };
}
