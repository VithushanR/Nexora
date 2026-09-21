import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

import {
  ApiClientError,
  ApiConfigurationError,
  ApiNetworkError,
  getResearchReport,
  getResearchStatus,
} from "../api/client";
import type { ResearchStatus, ResearchStatusResponse } from "../types";

const POLL_INTERVAL_MS = 2_000;

const REPORT_MARKDOWN_COMPONENTS: Components = {
  h1: ({ children }) => (
    <h2 className="mb-3 text-2xl font-bold text-slate-900 dark:text-white">{children}</h2>
  ),
  h2: ({ children }) => (
    <h3 className="mb-2 mt-8 border-b border-slate-200 pb-1 text-xl font-semibold text-slate-900 dark:border-slate-700 dark:text-white">
      {children}
    </h3>
  ),
  h3: ({ children }) => (
    <h4 className="mb-1 mt-5 text-base font-semibold text-slate-900 dark:text-white">{children}</h4>
  ),
  p: ({ children }) => <p className="my-2">{children}</p>,
  ul: ({ children }) => <ul className="my-2 list-disc space-y-1 pl-6">{children}</ul>,
  ol: ({ children }) => <ol className="my-2 list-decimal space-y-1 pl-6">{children}</ol>,
  blockquote: ({ children }) => (
    <blockquote className="my-3 rounded-md border-l-4 border-amber-400 bg-amber-50 px-4 py-2 text-amber-900 dark:bg-amber-900/20 dark:text-amber-200">
      {children}
    </blockquote>
  ),
  table: ({ children }) => (
    <div className="my-4 overflow-hidden rounded-xl border border-slate-200 shadow-sm dark:border-slate-700">
      <table className="w-full text-left text-sm">{children}</table>
    </div>
  ),
  thead: ({ children }) => (
    <thead className="bg-gradient-to-r from-violet-600 to-purple-500">{children}</thead>
  ),
  th: ({ children }) => (
    <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-white">{children}</th>
  ),
  td: ({ children }) => (
    <td className="border-t border-slate-100 px-4 py-3 align-top text-slate-700 dark:border-slate-700 dark:text-slate-300">
      {children}
    </td>
  ),
  a: ({ children, href }) => (
    <a href={href} className="text-violet-600 underline dark:text-violet-400" target="_blank" rel="noreferrer">
      {children}
    </a>
  ),
};

function reportErrorMessage(error: unknown): string {
  if (error instanceof ApiClientError) {
    switch (error.status) {
      case 404:
        return "The research session or report could not be found.";
      case 503:
        return "Authentication/setup is not currently configured.";
      case 500:
        return "Research processing failed. Please try again.";
      default:
        return "The research report could not be loaded. Please try again.";
    }
  }
  if (error instanceof ApiConfigurationError) {
    return "The frontend backend connection is not configured.";
  }
  if (error instanceof ApiNetworkError) {
    return "Unable to connect to the research service. Please try again.";
  }
  return "The research report could not be loaded. Please try again.";
}

export default function ReportPage() {
  const { runId } = useParams<{ runId: string }>();
  const [status, setStatus] = useState<ResearchStatus | undefined>();
  const [report, setReport] = useState<string | undefined>();
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [retryKey, setRetryKey] = useState(0);

  useEffect(() => {
    let isCurrent = true;
    let timeoutId: number | undefined;

    async function fetchReport(): Promise<void> {
      try {
        const response = await getResearchReport(runId as string);
        if (isCurrent) {
          setReport(response.report);
        }
      } catch (fetchError) {
        if (isCurrent) {
          setError(reportErrorMessage(fetchError));
        }
      }
    }

    async function checkStatus(): Promise<void> {
      try {
        const response: ResearchStatusResponse = await getResearchStatus(runId as string);
        if (!isCurrent) return;

        setStatus(response.status);
        if (response.status === "done") {
          await fetchReport();
          return;
        }
        if (response.status === "running_synthesis") {
          timeoutId = window.setTimeout(() => {
            void checkStatus();
          }, POLL_INTERVAL_MS);
        }
      } catch (statusError) {
        if (isCurrent) {
          setError(reportErrorMessage(statusError));
        }
      } finally {
        if (isCurrent) {
          setIsLoading(false);
        }
      }
    }

    if (!runId) {
      setError("The research session ID is missing.");
      setIsLoading(false);
    } else {
      setStatus(undefined);
      setReport(undefined);
      setError("");
      setIsLoading(true);
      void checkStatus();
    }

    return () => {
      isCurrent = false;
      if (timeoutId !== undefined) {
        window.clearTimeout(timeoutId);
      }
    };
  }, [runId, retryKey]);

  if (isLoading) {
    return (
      <PageLayout>
        <div className="flex items-center gap-3">
          <div className="step-spinner" />
          <p className="text-slate-700 dark:text-slate-300">Checking research progress…</p>
        </div>
      </PageLayout>
    );
  }

  if (error) {
    return (
      <PageLayout>
        <p role="alert" className="rounded-xl bg-red-50 p-4 text-red-800 dark:bg-red-900/20 dark:text-red-400">{error}</p>
        {runId ? (
          <button
            type="button"
            onClick={() => setRetryKey((current) => current + 1)}
            className="rounded-lg bg-violet-600 px-4 py-2 font-medium text-white transition hover:bg-violet-500"
          >
            Retry
          </button>
        ) : null}
      </PageLayout>
    );
  }

  if (status === "running_synthesis") {
    return (
      <PageLayout>
        <h1 className="text-3xl font-bold text-slate-900 dark:text-white">Research Report</h1>
        <div className="mt-4 flex items-center gap-3">
          <div className="thought-line flex-1" />
        </div>
        <p className="mt-3 text-slate-600 dark:text-slate-400">Your selected papers are being synthesized. This may take a little while.</p>
      </PageLayout>
    );
  }

  if (status === "paused_for_selection") {
    return (
      <PageLayout>
        <h1 className="text-3xl font-bold text-slate-900 dark:text-white">Research Report</h1>
        <p className="mt-3 text-slate-600 dark:text-slate-400">Paper selection is still required before synthesis can begin.</p>
        {runId ? (
          <Link
            className="inline-block rounded-lg bg-violet-600 px-4 py-2 font-medium text-white transition hover:bg-violet-500"
            to={`/select/${encodeURIComponent(runId)}`}
          >
            Select papers
          </Link>
        ) : null}
      </PageLayout>
    );
  }

  if (status === "running_agent2") {
    return (
      <PageLayout>
        <h1 className="text-3xl font-bold text-slate-900 dark:text-white">Research Report</h1>
        <div className="mt-4 flex items-center gap-3">
          <div className="thought-line flex-1" />
        </div>
        <p className="mt-3 text-slate-600 dark:text-slate-400">Research is still retrieving and screening papers.</p>
      </PageLayout>
    );
  }

  if (status === "error") {
    return (
      <PageLayout>
        <h1 className="text-3xl font-bold text-slate-900 dark:text-white">Research Report</h1>
        <p role="alert" className="mt-3 rounded-xl bg-red-50 p-4 text-red-800 dark:bg-red-900/20 dark:text-red-400">
          Research processing failed. Please try again.
        </p>
        <button
          type="button"
          onClick={() => setRetryKey((current) => current + 1)}
          className="rounded-lg bg-violet-600 px-4 py-2 font-medium text-white transition hover:bg-violet-500"
        >
          Check status again
        </button>
      </PageLayout>
    );
  }

  return (
    <PageLayout>
      <h1 className="text-3xl font-bold text-slate-900 dark:text-white">Research Report</h1>
      <p className="mt-3 font-medium text-emerald-600 dark:text-emerald-400">Research complete.</p>
      <article className="mt-6 break-words rounded-xl border border-slate-200 bg-white p-6 text-sm leading-relaxed text-slate-800 shadow-sm dark:border-slate-700 dark:bg-slate-800/50 dark:text-slate-200">
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={REPORT_MARKDOWN_COMPONENTS}>
          {report}
        </ReactMarkdown>
      </article>
    </PageLayout>
  );
}

function PageLayout({ children }: { children: React.ReactNode }) {
  return (
    <main className="mx-auto max-w-4xl space-y-4 p-6">
      <div className="flex items-center gap-2">
        <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-violet-500 to-purple-600">
          <span className="text-[11px] font-bold text-white">N</span>
        </div>
        <p className="text-sm font-semibold tracking-wide text-violet-600 dark:text-violet-400">Nexora</p>
      </div>
      {children}
      <Link className="block text-violet-600 underline transition hover:text-violet-500 dark:text-violet-400 dark:hover:text-violet-300" to="/">
        Start new research
      </Link>
    </main>
  );
}
