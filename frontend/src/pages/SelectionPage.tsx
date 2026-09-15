// Ranked paper list with tick-to-select, submits to POST /select to resume
// the backend's interrupt() checkpoint, then navigates to ReportPage.
// TODO: render candidates via PaperCard, track selection state, call api/client.ts.

import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { getStatus, getCandidates, submitSelection, ApiError } from "../api/client";
import type { Candidate } from "../types";
import PaperCard from "../components/PaperCard";

const DEFAULT_PRESELECT = 20;
const POLL_MS = 2500;

export default function SelectionPage() {
  const { runId } = useParams<{ runId: string }>();
  const navigate = useNavigate();

  const [statusDetail, setStatusDetail] = useState("Screening candidate papers…");
  const [candidates, setCandidates] = useState<Candidate[] | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!runId) return;
    let cancelled = false;

    async function poll() {
      try {
        const status = await getStatus(runId!);
        if (cancelled) return;
        setStatusDetail(status.detail || status.status);

        if (status.status === "paused_for_selection") {
          const { eligible_candidates } = await getCandidates(runId!);
          if (cancelled) return;
          setCandidates(eligible_candidates);
          setSelected(
            new Set(
              eligible_candidates
                .slice(0, Math.min(DEFAULT_PRESELECT, eligible_candidates.length))
                .map((_, i) => i)
            )
          );
          return; // candidates are in, stop polling
        }

        if (status.status === "error") {
          setError(status.detail || "The pipeline hit an error.");
          return;
        }

        setTimeout(poll, POLL_MS);
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof ApiError ? e.message : "Could not reach the server.");
        }
      }
    }

    poll();
    return () => {
      cancelled = true;
    };
  }, [runId]);

  const toggle = useCallback((index: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });
  }, []);

  async function confirm() {
    if (!runId) return;
    setSubmitting(true);
    setError(null);
    try {
      await submitSelection(runId, Array.from(selected).sort((a, b) => a - b));

      let status = await getStatus(runId);
      while (status.status !== "done" && status.status !== "error") {
        await new Promise((r) => setTimeout(r, POLL_MS));
        status = await getStatus(runId);
      }
      if (status.status === "error") {
        setError(status.detail || "Report generation failed.");
        setSubmitting(false);
        return;
      }
      navigate(`/report/${runId}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not submit your selection.");
      setSubmitting(false);
    }
  }

  if (error) {
    return (
      <div className="flex h-full items-center justify-center px-6">
        <p className="text-rose-600">{error}</p>
      </div>
    );
  }

  if (!candidates) {
    return (
      <div className="flex h-full flex-col items-center justify-center">
        <div className="mx-auto mb-4 h-8 w-8 animate-spin rounded-full border-2 border-slate-200 border-t-blue-600" />
        <p className="text-slate-500">{statusDetail}</p>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto px-6 py-10"><div className="mx-auto max-w-4xl">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Select papers</h1>
          <p className="text-sm text-slate-500">
            {selected.size} of {candidates.length} selected — ranked by relevance, verdicts shown
            for guidance.
          </p>
        </div>
        <button
          onClick={confirm}
          disabled={submitting || selected.size === 0}
          className="rounded-xl bg-blue-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {submitting ? "Building report…" : `Continue with ${selected.size}`}
        </button>
      </div>

      <div className="space-y-3">
        {candidates.map((c, i) => (
          <PaperCard key={i} candidate={c} selected={selected.has(i)} onToggle={() => toggle(i)} />
        ))}
      </div>
    </div></div>
  );
}
