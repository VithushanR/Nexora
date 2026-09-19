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

// Tailwind's preflight strips default element styles, so style each markdown
// element explicitly (the report is Markdown from report_assembly.py).
const REPORT_MARKDOWN_COMPONENTS: Components = {
  h1: ({ children }) => <h2 className="mb-3 text-2xl font-bold text-slate-900">{children}</h2>,
  h2: ({ children }) => (
    <h3 className="mb-2 mt-8 border-b border-slate-200 pb-1 text-xl font-semibold text-slate-900">{children}</h3>
  ),
  h3: ({ children }) => <h4 className="mb-1 mt-5 text-base font-semibold text-slate-900">{children}</h4>,
  p: ({ children }) => <p className="my-2">{children}</p>,
  ul: ({ children }) => <ul className="my-2 list-disc space-y-1 pl-6">{children}</ul>,
  ol: ({ children }) => <ol className="my-2 list-decimal space-y-1 pl-6">{children}</ol>,
  blockquote: ({ children }) => (
    <blockquote className="my-3 rounded-md border-l-4 border-amber-400 bg-amber-50 px-4 py-2 text-amber-900">
      {children}
    </blockquote>
  ),
  table: ({ children }) => (
    <div className="my-3 overflow-x-auto">
      <table className="w-full border-collapse text-left text-sm">{children}</table>
    </div>
  ),
  th: ({ children }) => (
    <th className="border border-slate-200 bg-slate-50 px-3 py-2 font-semibold text-slate-900">{children}</th>
  ),
  td: ({ children }) => <td className="border border-slate-200 px-3 py-2 align-top">{children}</td>,
  a: ({ children, href }) => (
    <a href={href} className="text-indigo-700 underline" target="_blank" rel="noreferrer">
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
    return <PageLayout><p className="text-slate-700">Checking research progress…</p></PageLayout>;
  }

  if (error) {
    return (
      <PageLayout>
        <p role="alert" className="rounded-md bg-red-50 p-4 text-red-800">{error}</p>
        {runId ? (
          <button
            type="button"
            onClick={() => setRetryKey((current) => current + 1)}
            className="rounded-md bg-indigo-600 px-4 py-2 font-medium text-white"
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
        <h1 className="text-3xl font-bold text-slate-900">Research Report</h1>
        <p className="mt-3 text-slate-700">Your selected papers are being synthesized. This may take a little while.</p>
      </PageLayout>
    );
  }

  if (status === "paused_for_selection") {
    return (
      <PageLayout>
        <h1 className="text-3xl font-bold text-slate-900">Research Report</h1>
        <p className="mt-3 text-slate-700">Paper selection is still required before synthesis can begin.</p>
        {runId ? <Link className="text-indigo-700 underline" to={`/select/${encodeURIComponent(runId)}`}>Select papers</Link> : null}
      </PageLayout>
    );
  }

  if (status === "running_agent2") {
    return (
      <PageLayout>
        <h1 className="text-3xl font-bold text-slate-900">Research Report</h1>
        <p className="mt-3 text-slate-700">Research is still retrieving and screening papers.</p>
      </PageLayout>
    );
  }

  if (status === "error") {
    return (
      <PageLayout>
        <h1 className="text-3xl font-bold text-slate-900">Research Report</h1>
        <p role="alert" className="mt-3 rounded-md bg-red-50 p-4 text-red-800">Research processing failed. Please try again.</p>
        <button
          type="button"
          onClick={() => setRetryKey((current) => current + 1)}
          className="rounded-md bg-indigo-600 px-4 py-2 font-medium text-white"
        >
          Check status again
        </button>
      </PageLayout>
    );
  }

  return (
    <PageLayout>
      <h1 className="text-3xl font-bold text-slate-900">Research Report</h1>
      <p className="mt-3 font-medium text-emerald-700">Research complete.</p>
      <article className="mt-6 break-words rounded-lg border border-slate-200 bg-white p-5 text-sm leading-6 text-slate-800 shadow-sm">
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
      <p className="text-sm font-semibold tracking-wide text-indigo-700">Nexora</p>
      {children}
      <Link className="block text-indigo-700 underline" to="/">Start new research</Link>
    </main>
  );
}
