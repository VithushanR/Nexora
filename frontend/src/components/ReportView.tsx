// Item 7: the finished report rendered as a message/card in the SAME
// chat thread, not a separate page. Markdown styling ported unchanged
// from the old ReportPage.tsx (including the evidence table's violet
// header -- confirmed deliberate brand styling, not a bug; nothing else
// here applies any background color to prose text).
import { useState } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

import { ApiError, downloadResearchReportPdf } from "../api/client";

const REPORT_MARKDOWN_COMPONENTS: Components = {
  h1: ({ children }) => (
    <h2 className="mb-3 text-xl font-bold text-slate-900 dark:text-white">{children}</h2>
  ),
  h2: ({ children }) => (
    <h3 className="mb-2 mt-6 border-b border-slate-200 pb-1 text-base font-semibold text-slate-900 dark:border-slate-700 dark:text-white">
      {children}
    </h3>
  ),
  h3: ({ children }) => (
    <h4 className="mb-1 mt-4 text-sm font-semibold text-slate-900 dark:text-white">{children}</h4>
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
    <div className="my-3 overflow-x-auto rounded-xl border border-slate-200 shadow-sm dark:border-slate-700">
      <table className="w-full text-left text-xs">{children}</table>
    </div>
  ),
  thead: ({ children }) => (
    <thead className="bg-gradient-to-r from-violet-600 to-purple-500">{children}</thead>
  ),
  th: ({ children }) => (
    <th className="px-3 py-2 text-[10px] font-semibold uppercase tracking-wider text-white">{children}</th>
  ),
  td: ({ children }) => (
    <td className="border-t border-slate-100 px-3 py-2 align-top text-slate-700 dark:border-slate-700 dark:text-slate-300">
      {children}
    </td>
  ),
  a: ({ children, href }) => (
    <a href={href} className="text-violet-600 underline dark:text-violet-400" target="_blank" rel="noreferrer">
      {children}
    </a>
  ),
};

interface ReportViewProps {
  threadId: string;
  report: string;
}

export default function ReportView({ threadId, report }: ReportViewProps) {
  const [downloadingPdf, setDownloadingPdf] = useState(false);
  const [downloadError, setDownloadError] = useState("");

  async function handleDownloadPdf() {
    if (downloadingPdf) return;
    setDownloadingPdf(true);
    setDownloadError("");
    try {
      const blob = await downloadResearchReportPdf(threadId);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `nexora-report-${threadId}.pdf`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      setDownloadError(e instanceof ApiError ? e.message : "The report PDF could not be downloaded.");
    } finally {
      setDownloadingPdf(false);
    }
  }

  return (
    <div className="min-w-0 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-800/50">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-semibold text-emerald-600 dark:text-emerald-400">Research complete</p>
        <button
          type="button"
          onClick={() => void handleDownloadPdf()}
          disabled={downloadingPdf}
          className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 shadow-sm transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700"
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3" />
          </svg>
          {downloadingPdf ? "Preparing PDF…" : "Download PDF"}
        </button>
      </div>
      {downloadError && (
        <p role="alert" className="mb-2 rounded-lg bg-red-50 p-2 text-xs text-red-800 dark:bg-red-900/20 dark:text-red-400">
          {downloadError}
        </p>
      )}
      <div className="break-words text-xs leading-relaxed text-slate-700 dark:text-slate-300">
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={REPORT_MARKDOWN_COMPONENTS}>
          {report}
        </ReactMarkdown>
      </div>
    </div>
  );
}
