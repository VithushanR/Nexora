import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { getReport, indexCopilot, sendCopilotMessage, getCopilotHistory, addToEvidence, ApiError } from "../api/client";
import type { ReportResponse, CopilotChatResponse } from "../types";
import EvidenceTable from "../components/EvidenceTable";
import ContradictionCard from "../components/ContradictionCard";
import GapCard from "../components/GapCard";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  mode?: "report" | "web";
  sources?: CopilotChatResponse["sources"];
  added?: boolean;
}

export default function ReportPage() {
  const { runId } = useParams<{ runId: string }>();
  const [report, setReport] = useState<ReportResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [mode, setMode] = useState<"report" | "auto">("report");
  const [sending, setSending] = useState(false);
  const [indexed, setIndexed] = useState(false);
  const [chatExpanded, setChatExpanded] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!runId) return;
    let cancelled = false;

    async function load() {
      try {
        const r = await getReport(runId!);
        if (!cancelled) setReport(r);
      } catch (e) {
        if (cancelled) return;
        if (e instanceof ApiError && e.status === 404) {
          setTimeout(load, 3000);
        } else {
          setError(e instanceof ApiError ? e.message : "Could not load the report.");
        }
      }
    }
    load();
    return () => { cancelled = true; };
  }, [runId]);

  useEffect(() => {
    if (!runId || !report) return;
    let cancelled = false;

    async function init() {
      try {
        await indexCopilot(runId!);
        if (!cancelled) setIndexed(true);
      } catch {
        if (!cancelled) setIndexed(false);
      }
      try {
        const history = await getCopilotHistory(runId!);
        if (!cancelled && history.length > 0) {
          setMessages(history.map((h) => ({
            id: h.message_id,
            role: h.role,
            content: h.content,
            mode: h.mode,
          })));
          setChatExpanded(true);
        }
      } catch { /* start fresh */ }
    }
    init();
    return () => { cancelled = true; };
  }, [runId, report]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function send() {
    if (!runId) return;
    const text = input.trim();
    if (!text || sending) return;
    setInput("");
    setChatExpanded(true);
    setMessages((m) => [...m, { id: `u-${Date.now()}`, role: "user", content: text }]);
    setSending(true);
    try {
      const res = await sendCopilotMessage(runId, text, mode);
      setMessages((m) => [
        ...m,
        { id: res.message_id, role: "assistant", content: res.answer, mode: res.mode, sources: res.sources },
      ]);
    } catch (e) {
      setMessages((m) => [
        ...m,
        { id: `err-${Date.now()}`, role: "assistant", content: e instanceof ApiError ? e.message : "Something went wrong." },
      ]);
    } finally {
      setSending(false);
    }
  }

  async function handleAddToEvidence(messageId: string) {
    if (!runId) return;
    try {
      await addToEvidence(runId, messageId);
      setMessages((m) => m.map((msg) => (msg.id === messageId ? { ...msg, added: true } : msg)));
    } catch { /* non-critical */ }
  }

  if (error) {
    return <div className="flex h-full items-center justify-center px-6 text-rose-600">{error}</div>;
  }

  if (!report) {
    return (
      <div className="flex h-full flex-col items-center justify-center">
        <div className="mb-4 h-8 w-8 animate-spin rounded-full border-2 border-slate-200 border-t-blue-600" />
        <p className="text-slate-500">Assembling the report...</p>
      </div>
    );
  }

  const incomplete = report.analysis_incomplete || report.meta?.analysis_incomplete;

  return (
    <div className="flex h-full flex-col">
      {/* Scrollable report content */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-4xl px-6 py-8">
          <div className="mb-6">
            <h1 className="text-2xl font-semibold text-slate-900">{report.domain}</h1>
            <p className="mt-1 text-sm text-slate-500">
              {report.meta.n_papers} papers · {report.meta.n_full_text} with full text · {report.meta.n_contradictions} conflicts · {report.meta.n_gaps} gaps
            </p>
          </div>

          {incomplete && (
            <div className="mb-6 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
              <strong>Analysis incomplete.</strong> Some sections below could not be fully generated. Treat this report as partial.
            </div>
          )}

          <section className="mb-8">
            <h2 className="mb-3 text-lg font-semibold text-slate-900">Evidence table</h2>
            <EvidenceTable rows={report.evidence_table} />
          </section>

          <section className="mb-8">
            <h2 className="mb-3 text-lg font-semibold text-slate-900">Contradictions</h2>
            {report.contradictions_status.is_error ? (
              <p className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
                {report.contradictions_status.message}
              </p>
            ) : report.contradictions.length === 0 ? (
              <p className="rounded-xl border border-slate-200 bg-slate-50 p-3 text-sm text-slate-500">
                {report.contradictions_status.message || "No contradictions were found among these papers."}
              </p>
            ) : (
              <div className="space-y-3">
                {report.contradictions.map((c, i) => (
                  <ContradictionCard key={i} item={c} />
                ))}
              </div>
            )}
          </section>

          <section className="mb-8">
            <h2 className="mb-3 text-lg font-semibold text-slate-900">Research gaps</h2>
            {report.gaps_status.is_error ? (
              <p className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
                {report.gaps_status.message}
              </p>
            ) : report.gaps.length === 0 ? (
              <p className="rounded-xl border border-slate-200 bg-slate-50 p-3 text-sm text-slate-500">
                {report.gaps_status.message || "No recurring gaps met the support threshold."}
              </p>
            ) : (
              <div className="grid gap-3 sm:grid-cols-2">
                {report.gaps.map((g, i) => (
                  <GapCard key={i} gap={g} />
                ))}
              </div>
            )}
          </section>

          {/* Chat messages inline */}
          {chatExpanded && messages.length > 0 && (
            <section className="mb-4 rounded-xl border border-slate-200 bg-white p-4">
              <div className="mb-3 flex items-center justify-between">
                <h2 className="text-sm font-semibold text-slate-900">Copilot conversation</h2>
                <button
                  onClick={() => setChatExpanded(false)}
                  className="text-xs text-slate-400 hover:text-slate-600"
                >
                  Collapse
                </button>
              </div>
              <div className="space-y-3">
                {messages.map((m) => (
                  <div key={m.id} className={m.role === "user" ? "text-right" : "text-left"}>
                    <div
                      className={`inline-block max-w-[80%] rounded-2xl px-3.5 py-2 text-sm ${
                        m.role === "user"
                          ? "bg-blue-600 text-white"
                          : "bg-slate-100 text-slate-800"
                      }`}
                    >
                      {m.content}
                    </div>
                    {m.role === "assistant" && m.mode && (
                      <div className="mt-1 flex flex-wrap items-center gap-1">
                        <span
                          className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${
                            m.mode === "web"
                              ? "bg-purple-50 text-purple-700 ring-1 ring-purple-200"
                              : "bg-blue-50 text-blue-700 ring-1 ring-blue-200"
                          }`}
                        >
                          {m.mode === "web" ? "Web" : "Report"}
                        </span>
                        {m.mode === "web" && !m.added && (
                          <button
                            onClick={() => handleAddToEvidence(m.id)}
                            className="text-[10px] font-medium text-blue-600 hover:underline"
                          >
                            Add to evidence
                          </button>
                        )}
                        {m.added && <span className="text-[10px] text-emerald-600">Added</span>}
                      </div>
                    )}
                  </div>
                ))}
                {sending && (
                  <div className="text-left">
                    <div className="inline-flex items-center gap-1.5 rounded-2xl bg-slate-100 px-4 py-2.5">
                      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400" style={{ animationDelay: "0ms" }} />
                      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400" style={{ animationDelay: "150ms" }} />
                      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400" style={{ animationDelay: "300ms" }} />
                    </div>
                  </div>
                )}
                <div ref={bottomRef} />
              </div>
            </section>
          )}
        </div>
      </div>

      {/* Fixed chat input bar at bottom */}
      <div className="shrink-0 border-t border-slate-200 bg-white px-6 py-3">
        <div className="mx-auto max-w-4xl">
          <div className="flex items-center gap-3">
            {/* Mode toggle */}
            <div className="hidden shrink-0 rounded-full bg-slate-100 p-0.5 text-xs sm:flex">
              <button
                onClick={() => setMode("report")}
                className={`rounded-full px-3 py-1 transition ${
                  mode === "report" ? "bg-white text-slate-900 shadow-sm" : "text-slate-500"
                }`}
              >
                Report
              </button>
              <button
                onClick={() => setMode("auto")}
                className={`rounded-full px-3 py-1 transition ${
                  mode === "auto" ? "bg-white text-slate-900 shadow-sm" : "text-slate-500"
                }`}
              >
                Report + Web
              </button>
            </div>

            {/* Input */}
            <div className="flex flex-1 items-center gap-2 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-2.5 focus-within:border-blue-400 focus-within:bg-white focus-within:ring-2 focus-within:ring-blue-100">
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) send();
                }}
                placeholder={indexed ? "Ask about this report..." : "Indexing report..."}
                disabled={!indexed}
                className="flex-1 bg-transparent text-sm text-slate-900 outline-none placeholder:text-slate-400 disabled:cursor-not-allowed"
              />
              <button
                onClick={send}
                disabled={sending || !input.trim() || !indexed}
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-blue-600 text-white transition hover:bg-blue-700 disabled:opacity-40"
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                  <path d="M5 12h14M12 5l7 7-7 7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
