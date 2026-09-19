import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import {
  ApiClientError,
  ApiConfigurationError,
  ApiNetworkError,
  getCandidates,
  getResearchStatus,
  submitSelection,
} from "../api/client";
import PaperCard from "../components/PaperCard";
import type { CandidatePaper, ResearchStatus, ResearchStatusResponse } from "../types";

function safeStatusMessage(status: ResearchStatusResponse): string {
  if (status.status === "error") {
    return status.detail || "The research session encountered an error.";
  }
  return status.detail;
}

function selectionErrorMessage(error: unknown): string {
  if (error instanceof ApiClientError) {
    switch (error.status) {
      case 404:
        return "The research session could not be found.";
      case 409:
        return "Research is no longer waiting for paper selection.";
      case 422:
        return "Please select at least one valid paper.";
      case 503:
        return "Authentication/setup is not currently configured.";
      case 500:
        return "Paper selection could not be submitted.";
      default:
        return "Paper selection could not be submitted.";
    }
  }
  if (error instanceof ApiConfigurationError) {
    return "The frontend backend connection is not configured.";
  }
  if (error instanceof ApiNetworkError) {
    return "Unable to connect to the research service. Please try again.";
  }
  return "Paper selection could not be submitted.";
}

export default function SelectionPage() {
  const { runId } = useParams<{ runId: string }>();
  const navigate = useNavigate();
  const [status, setStatus] = useState<ResearchStatus | undefined>();
  const [statusMessage, setStatusMessage] = useState("");
  const [candidates, setCandidates] = useState<CandidatePaper[]>([]);
  const [selectedIndices, setSelectedIndices] = useState<number[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingCandidates, setIsLoadingCandidates] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submissionError, setSubmissionError] = useState("");

  useEffect(() => {
    let isCurrent = true;

    async function loadSelection(): Promise<void> {
      if (!runId) {
        if (isCurrent) {
          setLoadError("The research session ID is missing.");
          setIsLoading(false);
        }
        return;
      }

      setIsLoading(true);
      setLoadError("");
      setSubmissionError("");
      try {
        const response = await getResearchStatus(runId);
        if (!isCurrent) return;

        setStatus(response.status);
        setStatusMessage(safeStatusMessage(response));

        if (response.status !== "paused_for_selection") {
          return;
        }

        setIsLoadingCandidates(true);
        try {
          const candidateResponse = await getCandidates(runId);
          if (isCurrent) {
            setCandidates(candidateResponse.eligible_candidates);
          }
        } catch (error) {
          if (isCurrent) {
            setLoadError(selectionErrorMessage(error));
          }
        } finally {
          if (isCurrent) {
            setIsLoadingCandidates(false);
          }
        }
      } catch (error) {
        if (isCurrent) {
          setLoadError(selectionErrorMessage(error));
        }
      } finally {
        if (isCurrent) {
          setIsLoading(false);
        }
      }
    }

    void loadSelection();
    return () => {
      isCurrent = false;
    };
  }, [runId]);

  function updateSelection(index: number, selected: boolean): void {
    setSelectedIndices((current) => {
      if (selected) {
        return current.includes(index) ? current : [...current, index];
      }
      return current.filter((selectedIndex) => selectedIndex !== index);
    });
  }

  async function handleSubmit(): Promise<void> {
    if (!runId || selectedIndices.length === 0 || isSubmitting || isLoadingCandidates) {
      return;
    }

    const orderedIndices = [...selectedIndices].sort((left, right) => left - right);
    setSubmissionError("");
    setIsSubmitting(true);
    try {
      const response = await submitSelection(runId, {
        selected_indices: orderedIndices,
      });
      if (response.status === "running_synthesis") {
        setStatus("running_synthesis");
        setStatusMessage("Paper selection was submitted. Synthesis has started.");
        navigate(`/report/${encodeURIComponent(runId)}`);
      }
    } catch (error) {
      setSubmissionError(selectionErrorMessage(error));
    } finally {
      setIsSubmitting(false);
    }
  }

  if (isLoading) {
    return <main className="mx-auto max-w-3xl p-6 text-slate-700">Loading research status…</main>;
  }

  if (loadError) {
    return (
      <main className="mx-auto max-w-3xl space-y-4 p-6">
        <p role="alert" className="rounded-md bg-red-50 p-4 text-red-800">{loadError}</p>
        <Link className="text-indigo-700 underline" to="/">Start a new research request</Link>
      </main>
    );
  }

  if (status === "running_agent2") {
    return <StatusView message="Research is still retrieving and screening papers." />;
  }

  if (status === "running_synthesis") {
    return <StatusView message="Paper selection has been submitted and synthesis is already running." />;
  }

  if (status === "done") {
    return (
      <StatusView
        message="This research session is already complete."
        reportPath={runId ? `/report/${encodeURIComponent(runId)}` : undefined}
      />
    );
  }

  if (status === "error") {
    return <StatusView message={statusMessage || "The research session encountered an error."} />;
  }

  return (
    <main className="mx-auto max-w-4xl space-y-6 p-6">
      <header>
        <h1 className="text-3xl font-bold text-slate-900">Select research papers</h1>
        <p className="mt-2 text-slate-600">Choose the screened papers to use for synthesis.</p>
      </header>

      {isLoadingCandidates ? <p className="text-slate-700">Loading candidate papers…</p> : null}
      {candidates.length === 0 && !isLoadingCandidates ? (
        <p className="rounded-md bg-amber-50 p-4 text-amber-900">No eligible candidate papers are available for this research session.</p>
      ) : null}

      <section aria-label="Candidate papers" className="space-y-4">
        {candidates.map((candidate, index) => (
          <PaperCard
            key={index}
            candidate={candidate}
            index={index}
            selected={selectedIndices.includes(index)}
            disabled={isSubmitting}
            onSelectionChange={updateSelection}
          />
        ))}
      </section>

      <section className="flex flex-wrap items-center gap-4 border-t border-slate-200 pt-4">
        <p className="text-slate-700" aria-live="polite">
          {selectedIndices.length} {selectedIndices.length === 1 ? "paper" : "papers"} selected
        </p>
        <button
          type="button"
          onClick={() => void handleSubmit()}
          disabled={selectedIndices.length === 0 || isSubmitting || isLoadingCandidates}
          className="rounded-md bg-indigo-600 px-4 py-2 font-medium text-white disabled:cursor-not-allowed disabled:bg-slate-400"
        >
          {isSubmitting ? "Submitting selection…" : "Submit selection"}
        </button>
        <Link className="text-indigo-700 underline" to="/">Start new research</Link>
      </section>

      {submissionError ? <p role="alert" className="rounded-md bg-red-50 p-4 text-red-800">{submissionError}</p> : null}
    </main>
  );
}

interface StatusViewProps {
  message: string;
  reportPath?: string;
}

function StatusView({ message, reportPath }: StatusViewProps) {
  return (
    <main className="mx-auto max-w-3xl space-y-4 p-6">
      <p className="rounded-md bg-slate-100 p-4 text-slate-800">{message}</p>
      {reportPath ? <Link className="text-indigo-700 underline" to={reportPath}>View report</Link> : null}
      <Link className="block text-indigo-700 underline" to="/">Start a new research request</Link>
    </main>
  );
}
