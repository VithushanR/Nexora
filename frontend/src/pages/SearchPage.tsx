import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

import {
  ApiClientError,
  ApiConfigurationError,
  ApiError,
  ApiNetworkError,
  getCandidates,
  getResearchReport,
  getResearchStatus,
  startResearch,
  submitSelection,
  uploadDocument,
  sendDocumentChat,
  sendGeneralChat,
  sendCopilotMessage,
  indexCopilot,
} from "../api/client";
import { useAuth } from "../auth/AuthContext";
import GoogleSignInButton from "../auth/GoogleSignInButton";
import { addHistory, getHistory } from "../components/Sidebar";
import CardShell from "../components/CardShell";
import CandidateSelectionModal from "../components/CandidateSelectionModal";
import ReportView from "../components/ReportView";
import type { CandidatePaper, DocumentUploadResponse, ResearchStatus } from "../types";

type Mode = "chat" | "deep-search";

// Item 4/5/7: the whole Deep Search lifecycle now lives in this one page,
// as one continuous chat thread -- no navigation to a separate selection
// or report page. "idle" = no active Deep Search thread in this session.
type DeepSearchStage = "idle" | "running_agent2" | "paused_for_selection" | "running_synthesis" | "done" | "error";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  pages?: number[];
  /** When set, this message renders as a ReportView card instead of plain/markdown text (item 7). */
  reportThreadId?: string;
  reportText?: string;
  /** A small inline control to reopen the selection popup after it's been closed without submitting. */
  showReviewPapersButton?: boolean;
}

// Issue 4: every real backend status (research.py's ResearchStatusResponse
// Literal), mapped to a friendly label -- no raw internal identifier
// (e.g. "running_agent2") should ever reach rendered UI text.
const STATUS_LABELS: Record<ResearchStatus, string> = {
  running_agent2: "Searching and screening papers…",
  paused_for_selection: "Ready for your selection",
  running_synthesis: "Analyzing selected papers…",
  done: "Research complete",
  error: "Something went wrong",
};

function statusLabel(status: ResearchStatus): string {
  return STATUS_LABELS[status];
}

// Issue 10 hardening: Date.now() can collide when two messages are added
// in the same millisecond (fast typing/sending, or two setMessages calls
// back to back); a colliding React `key` can cause one message to be
// silently dropped from the rendered list. A monotonic counter can't
// collide.
let messageIdCounter = 0;
function nextMessageId(prefix: string): string {
  messageIdCounter += 1;
  return `${prefix}-${Date.now()}-${messageIdCounter}`;
}

// Issue 3: sessionStorage-backed draft so a composer-in-progress survives
// a remount -- e.g. AppShell swapping the whole tree to <LoginPage/> when
// an automatic signOut() fires (a 401 on any authenticated call, not just
// the one the user is actively looking at) and back again. Session-scoped
// (not persisted across browser restarts) since it's a draft, not saved work.
const DRAFT_STORAGE_KEY = "nexora_chat_draft";

function loadDraft(): string {
  try {
    return sessionStorage.getItem(DRAFT_STORAGE_KEY) ?? "";
  } catch {
    return "";
  }
}

function saveDraft(value: string): void {
  try {
    if (value) sessionStorage.setItem(DRAFT_STORAGE_KEY, value);
    else sessionStorage.removeItem(DRAFT_STORAGE_KEY);
  } catch {
    // ignore -- same non-fatal storage failure as api/client.ts's token helpers
  }
}

const CHAT_MD: Components = {
  p: ({ children }) => <p className="mb-3 last:mb-0">{children}</p>,
  strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
  a: ({ children, href }) => (
    <a href={href} target="_blank" rel="noreferrer" className="text-violet-600 underline dark:text-violet-400">
      {children}
    </a>
  ),
  ul: ({ children }) => <ul className="mb-3 list-disc space-y-1 pl-5">{children}</ul>,
  ol: ({ children }) => <ol className="mb-3 list-decimal space-y-1 pl-5">{children}</ol>,
  pre: ({ children }) => (
    <pre className="mb-3 overflow-x-auto rounded-lg bg-slate-50 p-3 text-[13px] dark:bg-slate-800">{children}</pre>
  ),
  code: ({ children }) => (
    <code className="rounded bg-slate-100 px-1.5 py-0.5 text-[13px] dark:bg-slate-800">{children}</code>
  ),
};

function userFacingError(error: unknown): string {
  if (error instanceof ApiClientError) {
    if (error.code === "SAFETY_UNSAFE") {
      return "This topic cannot be processed as a research request. Please choose a different academic topic.";
    }
    if (error.code === "SAFETY_NEEDS_CONTEXT") {
      return "Please provide more context about the academic, clinical, prevention, policy, or research purpose of this topic.";
    }
    if (error.code === "SAFETY_UNAVAILABLE") {
      return "The safety check is temporarily unavailable. Please try again later.";
    }
    if (error.status === 401) {
      return "Your session has expired. Please sign in again to start research.";
    }
    if (error.status === 503) {
      return "Research sign-in/setup is not configured yet. Please try again after authentication is enabled.";
    }
    if (error.status === 422) {
      return "This research topic was rejected. Please enter a clear academic research topic.";
    }
    if (error.status === 429) {
      return "Too many research requests were made. Please wait and try again later.";
    }
    if (error.status === 500) {
      return "Research could not be started. Please try again later.";
    }
    return "The research service could not complete the request. Please try again.";
  }
  if (error instanceof ApiConfigurationError) return "The frontend is not configured with a backend API URL.";
  if (error instanceof ApiNetworkError) return "Unable to reach the research service. Check the connection and try again.";
  return "Something went wrong while starting research. Please try again.";
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
      default:
        return "Paper selection could not be submitted.";
    }
  }
  if (error instanceof ApiConfigurationError) return "The frontend backend connection is not configured.";
  if (error instanceof ApiNetworkError) return "Unable to connect to the research service. Please try again.";
  return "Paper selection could not be submitted.";
}

function Sparkle({ className = "", size = 16 }: { className?: string; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" className={className}>
      <path d="M12 2l2.4 7.6L22 12l-7.6 2.4L12 22l-2.4-7.6L2 12l7.6-2.4z" />
    </svg>
  );
}

export default function SearchPage() {
  const { threadId: routeThreadId } = useParams<{ threadId?: string }>();
  const { status, signOut } = useAuth();

  const [mode, setMode] = useState<Mode>("chat");
  const [input, setInput] = useState(loadDraft);
  const [messages, setMessages] = useState<Message[]>([]);
  const [isThinking, setIsThinking] = useState(false);
  const [progressMessage, setProgressMessage] = useState("");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [needsSignIn, setNeedsSignIn] = useState(false);

  const [doc, setDoc] = useState<DocumentUploadResponse | null>(null);
  const [uploading, setUploading] = useState(false);

  // Deep Search thread state -- item 4/5/7: all one persistent thread.
  const [threadId, setThreadId] = useState<string | null>(null);
  const [deepSearchStage, setDeepSearchStage] = useState<DeepSearchStage>("idle");
  const [candidates, setCandidates] = useState<CandidatePaper[]>([]);
  const [selectedIndices, setSelectedIndices] = useState<number[]>([]);
  const [isSelectionModalOpen, setIsSelectionModalOpen] = useState(false);
  const [isSubmittingSelection, setIsSubmittingSelection] = useState(false);
  const [selectionError, setSelectionError] = useState("");

  const fileRef = useRef<HTMLInputElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const pollTimeoutRef = useRef<number | undefined>(undefined);
  const pollActiveRef = useRef(true);

  useEffect(() => {
    pollActiveRef.current = true;
    return () => {
      pollActiveRef.current = false;
      window.clearTimeout(pollTimeoutRef.current);
    };
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isThinking]);

  useEffect(() => {
    const el = textareaRef.current;
    if (el) {
      el.style.height = "auto";
      el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
    }
    saveDraft(input);
  }, [input]);

  useEffect(() => {
    if (status === "signed-in") {
      setNeedsSignIn(false);
      setErrorMessage((c) =>
        c === "Please sign in with Google before starting research." ||
        c === "Your session has expired. Please sign in again to start research." ? null : c,
      );
    }
  }, [status]);

  function handleUnauthorized() {
    signOut();
    setNeedsSignIn(true);
    setErrorMessage("Your session has expired. Please sign in again to continue.");
  }

  // Polls a Deep Search thread's status through to a terminal state (done
  // or error), updating the SAME message thread as it goes -- this is the
  // one function driving items 4, 5, 6 and 7 together: it decides when the
  // selection popup opens, keeps the input bar disabled (via isThinking)
  // through synthesis, and appends the finished report as the last message
  // once done.
  async function pollThread(id: string): Promise<void> {
    try {
      const response = await getResearchStatus(id);
      if (!pollActiveRef.current) return;

      if (response.status === "running_agent2") {
        setDeepSearchStage("running_agent2");
        setIsThinking(true);
        setProgressMessage(statusLabel(response.status));
        pollTimeoutRef.current = window.setTimeout(() => void pollThread(id), 2_000);
        return;
      }

      if (response.status === "paused_for_selection") {
        setIsThinking(false);
        setDeepSearchStage("paused_for_selection");
        try {
          const candidateResponse = await getCandidates(id);
          if (!pollActiveRef.current) return;
          setCandidates(candidateResponse.eligible_candidates);
          setIsSelectionModalOpen(true);
          setMessages((m) => [
            ...m,
            {
              id: nextMessageId("a"),
              role: "assistant",
              content: `Found ${candidateResponse.eligible_candidates.length} candidate paper${candidateResponse.eligible_candidates.length === 1 ? "" : "s"}. Ready for your selection.`,
              showReviewPapersButton: true,
            },
          ]);
        } catch (error) {
          if (error instanceof ApiClientError && error.status === 401) {
            handleUnauthorized();
          } else {
            setErrorMessage(selectionErrorMessage(error));
          }
        }
        return;
      }

      if (response.status === "running_synthesis") {
        setDeepSearchStage("running_synthesis");
        setIsSelectionModalOpen(false);
        setIsThinking(true);
        setProgressMessage(statusLabel(response.status));
        pollTimeoutRef.current = window.setTimeout(() => void pollThread(id), 2_000);
        return;
      }

      if (response.status === "done") {
        setDeepSearchStage("done");
        setIsThinking(false);
        try {
          const reportResponse = await getResearchReport(id);
          if (!pollActiveRef.current) return;
          setMessages((m) => [
            ...m,
            { id: nextMessageId("a"), role: "assistant", content: "", reportThreadId: id, reportText: reportResponse.report },
          ]);
          // Issue 11c: index the finished report for Report Copilot chat as
          // soon as it's available, so Chat mode has something real to
          // ground answers in the moment the thread reaches "done" --
          // not only once the user happens to ask a question. Best-effort:
          // /copilot/chat degrades gracefully (empty retrieval, not an
          // error) if this hasn't finished yet, so a failure here is logged
          // and swallowed rather than surfaced as a research error.
          indexCopilot(id).catch((error) => {
            console.error("Report Copilot indexing failed for thread", id, error);
          });
        } catch (error) {
          if (error instanceof ApiClientError && error.status === 401) {
            handleUnauthorized();
          } else {
            setErrorMessage(userFacingError(error));
          }
        }
        return;
      }

      if (response.status === "error") {
        setDeepSearchStage("error");
        setIsThinking(false);
        const detail = response.detail?.trim();
        setErrorMessage(
          detail && detail !== "Research processing failed."
            ? detail
            : "Research stopped. Please try again; if it happens again, check the backend server log for the cause.",
        );
        return;
      }
    } catch (error) {
      if (!pollActiveRef.current) return;
      if (error instanceof ApiClientError && error.status === 401) {
        handleUnauthorized();
      } else {
        setErrorMessage(userFacingError(error));
      }
      setIsThinking(false);
      setDeepSearchStage("error");
    }
  }

  // Resume an existing thread when this page is opened via a "Saved
  // research" link (/t/:threadId) -- same in-thread rendering as an
  // active run, just entered from a fresh page load instead of continuing
  // in memory.
  useEffect(() => {
    if (!routeThreadId || threadId === routeThreadId) return;
    setThreadId(routeThreadId);
    setMode("deep-search");
    const domain = getHistory().find((h) => h.threadId === routeThreadId)?.domain;
    setMessages([
      {
        id: nextMessageId("u"),
        role: "user",
        content: domain ?? "Continuing this research thread…",
      },
    ]);
    void pollThread(routeThreadId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [routeThreadId]);

  async function handleFileUpload(file: File) {
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      setErrorMessage("Only PDF files are accepted.");
      return;
    }
    if (file.size > 20 * 1024 * 1024) {
      setErrorMessage("File exceeds the 20 MB limit.");
      return;
    }
    setUploading(true);
    setErrorMessage(null);
    try {
      const result = await uploadDocument(file);
      setDoc(result);
    } catch (e) {
      if (e instanceof ApiClientError && e.status === 401) {
        handleUnauthorized();
      } else {
        setErrorMessage(e instanceof ApiError ? e.message : "Upload failed.");
      }
    } finally {
      setUploading(false);
    }
  }

  function updateCandidateSelection(index: number, selected: boolean): void {
    setSelectedIndices((current) => {
      if (selected) {
        return current.includes(index) ? current : [...current, index];
      }
      return current.filter((selectedIndex) => selectedIndex !== index);
    });
  }

  async function handleSubmitSelection(): Promise<void> {
    if (!threadId || selectedIndices.length === 0 || isSubmittingSelection) return;

    const orderedIndices = [...selectedIndices].sort((a, b) => a - b);
    setSelectionError("");
    setIsSubmittingSelection(true);
    try {
      const response = await submitSelection(threadId, { selected_indices: orderedIndices });
      if (response.status === "running_synthesis") {
        setIsSelectionModalOpen(false);
        setDeepSearchStage("running_synthesis");
        setMessages((m) => [
          ...m,
          { id: nextMessageId("a"), role: "assistant", content: "Paper selection submitted." },
        ]);
        setIsThinking(true);
        setProgressMessage(statusLabel("running_synthesis"));
        pollTimeoutRef.current = window.setTimeout(() => void pollThread(threadId), 2_000);
      }
    } catch (error) {
      if (error instanceof ApiClientError && error.status === 401) {
        handleUnauthorized();
      }
      setSelectionError(selectionErrorMessage(error));
    } finally {
      setIsSubmittingSelection(false);
    }
  }

  async function handleSubmit() {
    const trimmed = input.trim();
    if (!trimmed || isThinking) return;

    setErrorMessage(null);

    if (mode === "deep-search") {
      if (status !== "signed-in") {
        setErrorMessage("Please sign in with Google before starting research.");
        setNeedsSignIn(true);
        return;
      }
      setNeedsSignIn(false);

      setMessages((m) => [...m, { id: nextMessageId("u"), role: "user", content: trimmed }]);
      setInput("");
      setIsThinking(true);
      setProgressMessage("Starting research…");
      setDeepSearchStage("running_agent2");

      try {
        const { thread_id } = await startResearch({ domain: trimmed });
        setThreadId(thread_id);
        addHistory(thread_id, trimmed);
        // Deliberately NOT navigate()-ing to /t/<thread_id> here: switching
        // between the "/" and "/t/:threadId" route patterns mid-session
        // risks React Router remounting SearchPage (uncertain across route
        // *pattern* boundaries, even for the same component), which would
        // wipe this live in-memory thread and replace it with the resume
        // effect's generic placeholder. A page refresh already destroys
        // React state regardless of the URL, so /t/:threadId's real job is
        // just being the entry point from "Saved research" -- not tracking
        // the active session's URL in real time.
        await pollThread(thread_id);
      } catch (error) {
        if (error instanceof ApiClientError && error.status === 401) {
          handleUnauthorized();
        } else {
          setErrorMessage(userFacingError(error));
        }
        setIsThinking(false);
        setDeepSearchStage("error");
      }
    } else {
      // Issue 11c: a completed Deep Search report in THIS thread takes
      // priority over an uploaded document, which takes priority over
      // plain conversational chat -- checked in that order every send, not
      // just decided once, so it stays correct if e.g. a report finishes
      // mid-conversation.
      const hasReport = deepSearchStage === "done" && threadId !== null;

      setMessages((m) => [...m, { id: nextMessageId("u"), role: "user", content: trimmed }]);
      setInput("");
      setIsThinking(true);
      // Mode-specific progress text, set BEFORE isThinking is read by the
      // render -- item 1's bug was this being left blank here (for every
      // chat sub-mode) and the thinking indicator falling back to a
      // hardcoded "Searching the document…" regardless of whether a
      // document, a report, or neither was actually in play.
      setProgressMessage(hasReport ? "Searching the report…" : doc ? "Searching the document…" : "Thinking…");

      try {
        if (hasReport) {
          const res = await sendCopilotMessage(threadId as string, trimmed, "report");
          setMessages((m) => [...m, { id: res.message_id, role: "assistant", content: res.answer }]);
        } else if (doc) {
          const res = await sendDocumentChat(doc.document_id, trimmed);
          setMessages((m) => [
            ...m,
            {
              id: res.message_id,
              role: "assistant",
              content: res.answer,
              pages: res.sources?.map((s) => s.page),
            },
          ]);
        } else {
          const res = await sendGeneralChat(trimmed);
          setMessages((m) => [...m, { id: nextMessageId("a"), role: "assistant", content: res.reply }]);
        }
      } catch (e) {
        if (e instanceof ApiClientError && e.status === 401) {
          handleUnauthorized();
        }
        const content =
          e instanceof ApiClientError && e.status === 429
            ? "You're sending messages a bit fast -- please wait a moment and try again."
            : e instanceof ApiError
              ? e.message
              : "Something went wrong.";
        setMessages((m) => [...m, { id: nextMessageId("err"), role: "assistant", content }]);
      } finally {
        setIsThinking(false);
      }
    }
  }

  const hasMessages = messages.length > 0;
  // Item 6: input disabled through synthesis (isThinking already covers
  // running_agent2/running_synthesis/general-chat/doc-chat in flight).
  const inputDisabled = isThinking;

  const footerClassName =
    mode === "deep-search"
      ? "border-violet-300 bg-violet-50/40 focus-within:ring-1 focus-within:ring-violet-200 dark:border-violet-700 dark:bg-violet-950/20 dark:focus-within:ring-violet-800"
      : "border-slate-200 bg-white focus-within:border-violet-300 focus-within:ring-1 focus-within:ring-violet-100 dark:border-slate-700 dark:bg-slate-800 dark:focus-within:border-violet-700 dark:focus-within:ring-violet-900/30";

  const inputBar = (
    <div className="px-3 pb-2 pt-2">
      {/* No mx-auto/max-w-3xl here -- that inner width cap (while the box
          itself already spans the card's width) was what created the empty
          side gutters. Content now fills the box's actual width. */}
      <div>
        {/* Uploaded doc chip */}
        {doc && (
          <div className="mb-2 flex items-center gap-2 rounded-xl bg-violet-50 px-3 py-2 dark:bg-violet-950/30">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" className="shrink-0 text-violet-500">
              <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8l-6-6z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
              <path d="M14 2v6h6" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
            </svg>
            <span className="flex-1 truncate text-xs font-medium text-slate-700 dark:text-slate-300">{doc.title}</span>
            <span className="shrink-0 text-[10px] text-slate-400">{doc.n_pages} pages</span>
            <button
              onClick={() => setDoc(null)}
              className="ml-1 rounded p-0.5 text-slate-400 transition hover:bg-violet-100 hover:text-slate-600 dark:hover:bg-violet-900/40 dark:hover:text-slate-300"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <path d="M18 6L6 18M6 6l12 12" />
              </svg>
            </button>
          </div>
        )}

        {/* Uploading indicator */}
        {uploading && (
          <div className="mb-2 flex items-center gap-2 rounded-xl bg-violet-50 px-3 py-2 text-xs text-slate-500 dark:bg-violet-950/30 dark:text-slate-400">
            <div className="h-4 w-4 animate-spin rounded-full border-2 border-violet-200 border-t-violet-600 dark:border-slate-700 dark:border-t-violet-400" />
            Uploading document…
          </div>
        )}

        {/* Error */}
        {errorMessage && (
          <div role="alert" className="mb-2 rounded-xl bg-red-50 px-3 py-2 text-xs text-red-700 dark:bg-red-900/20 dark:text-red-400">
            <p>{errorMessage}</p>
            {needsSignIn && <GoogleSignInButton width={210} />}
          </div>
        )}

        {/* Input row -- no border/shadow of its own, and no loading
            animation of its own (item 1) -- CardShell's footer box (whose
            accent already reflects the active mode, Issue 9) is the ONLY
            visible boundary here, and it stays visually static regardless
            of processing state. The message thread's own "..." indicator
            (below) is what shows progress now. */}
        <div className="flex items-center gap-2">
          <button
            onClick={() => fileRef.current?.click()}
            disabled={uploading}
            title="Upload document"
            className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-slate-400 transition hover:bg-violet-50 hover:text-violet-600 disabled:opacity-40 dark:hover:bg-violet-900/30 dark:hover:text-violet-400"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <path d="M12 5v14M5 12h14" />
            </svg>
          </button>
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSubmit();
              }
            }}
            placeholder={deepSearchStage === "running_synthesis" ? "Analyzing selected papers…" : "Message Nexora…"}
            rows={1}
            disabled={inputDisabled}
            className="block min-h-[24px] flex-1 resize-none bg-transparent text-[14px] leading-6 text-slate-800 outline-none placeholder:text-slate-400 disabled:cursor-not-allowed dark:text-slate-200 dark:placeholder:text-slate-500"
          />

          {/* Mode toggle -- inline, adjacent to send (Issue 8) */}
          <div className="flex shrink-0 items-center gap-0.5 rounded-full border border-slate-200 bg-white p-0.5 shadow-sm dark:border-slate-700 dark:bg-slate-900">
            <button
              onClick={() => setMode("chat")}
              disabled={inputDisabled}
              title="Chat"
              className={`flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium transition ${
                mode === "chat"
                  ? "bg-violet-100 text-violet-700 dark:bg-violet-900/50 dark:text-violet-300"
                  : "text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200"
              }`}
            >
              <Sparkle size={11} />
              Chat
            </button>
            <button
              onClick={() => setMode("deep-search")}
              disabled={inputDisabled}
              title="Deep Search"
              className={`flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium transition ${
                mode === "deep-search"
                  ? "bg-violet-100 text-violet-700 dark:bg-violet-900/50 dark:text-violet-300"
                  : "text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200"
              }`}
            >
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <circle cx="11" cy="11" r="8" />
                <path d="M21 21l-4.35-4.35" />
              </svg>
              Deep Search
            </button>
          </div>

          <button
            onClick={handleSubmit}
            disabled={inputDisabled || !input.trim()}
            title="Send"
            className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-violet-500 to-purple-600 text-white shadow-sm transition hover:shadow-md disabled:from-slate-200 disabled:to-slate-200 disabled:text-slate-400 disabled:shadow-none dark:disabled:from-slate-700 dark:disabled:to-slate-700 dark:disabled:text-slate-500"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z" />
            </svg>
          </button>
        </div>

        {/* Bottom hints */}
        <div className="mt-1 flex items-center justify-between px-0.5">
          <button
            onClick={() => fileRef.current?.click()}
            className="flex items-center gap-1 text-[11px] text-slate-400 transition hover:text-violet-500 dark:text-slate-500 dark:hover:text-violet-400"
          >
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M17 8l-5-5-5 5M12 3v12" />
            </svg>
            Drop PDFs, docs, or links here
          </button>
          <span className="text-[11px] text-slate-400 dark:text-slate-500">
            Enter to send · Shift + Enter for newline
          </span>
        </div>
      </div>
    </div>
  );

  return (
    <CardShell footer={inputBar} footerClassName={footerClassName}>
      {/* Messages / empty state */}
      <div className="relative flex-1 overflow-y-auto">
        {!hasMessages ? (
          <div className="flex h-full flex-col items-center justify-center px-4">
            {/* Logo */}
            <img
              src="/nexora-logo.png"
              alt="Nexora"
              className="mb-5 h-14 w-14 rounded-2xl object-cover shadow-lg shadow-violet-300/40 dark:shadow-violet-900/50"
            />

            {/* Label */}
            <p className="mb-4 text-xs font-semibold uppercase tracking-[0.2em] text-slate-500 dark:text-slate-400">
              Nexora Research
            </p>

            {/* Hero heading */}
            <h1 className="max-w-2xl text-center text-[42px] font-bold leading-[1.15] tracking-tight text-slate-900 dark:text-white">
              What would you like
              <br />
              <span className="bg-gradient-to-r from-violet-500 to-purple-500 bg-clip-text text-transparent">
                to discover?
              </span>
            </h1>

            {/* Subtitle */}
            <p className="mt-5 max-w-lg text-center text-[15px] leading-relaxed text-slate-500 dark:text-slate-400">
              Ask a question or upload research documents. Nexora will find the signal across your sources.
            </p>

          </div>
        ) : (
          // Item 2: no more mx-auto max-w-3xl cap here -- that's what left
          // most of the card's width empty. Content now uses the available
          // width with a modest, consistent side padding instead.
          <div className="space-y-1 px-5 py-8 sm:px-8">
            {messages.map((m) => (
              <div key={m.id} className="py-3">
                {m.role === "user" ? (
                  <div className="flex justify-end">
                    <div className="max-w-[80%] rounded-2xl bg-slate-100 px-4 py-3 text-[15px] leading-relaxed text-slate-800 dark:bg-slate-800 dark:text-slate-200">
                      {m.content}
                    </div>
                  </div>
                ) : m.reportThreadId && m.reportText ? (
                  <div className="flex gap-3">
                    <img
                      src="/nexora-logo.png"
                      alt="N"
                      className="mt-0.5 h-7 w-7 shrink-0 rounded-lg object-cover"
                    />
                    <ReportView threadId={m.reportThreadId} report={m.reportText} />
                  </div>
                ) : (
                  <div className="flex gap-3">
                    <img
                      src="/nexora-logo.png"
                      alt="N"
                      className="mt-0.5 h-7 w-7 shrink-0 rounded-lg object-cover"
                    />
                    <div className="min-w-0 flex-1 text-[15px] leading-relaxed text-slate-700 dark:text-slate-300">
                      <ReactMarkdown remarkPlugins={[remarkGfm]} components={CHAT_MD}>
                        {m.content}
                      </ReactMarkdown>
                      {m.pages && m.pages.length > 0 && (
                        <p className="mt-2 text-xs text-slate-400">
                          Pages: {m.pages.join(", ")}
                        </p>
                      )}
                      {m.showReviewPapersButton && deepSearchStage === "paused_for_selection" && !isSelectionModalOpen && (
                        <button
                          onClick={() => setIsSelectionModalOpen(true)}
                          className="mt-2 rounded-lg border border-violet-200 bg-violet-50 px-3 py-1.5 text-xs font-medium text-violet-700 transition hover:bg-violet-100 dark:border-violet-800 dark:bg-violet-950/30 dark:text-violet-300 dark:hover:bg-violet-900/40"
                        >
                          Review papers
                        </button>
                      )}
                    </div>
                  </div>
                )}
              </div>
            ))}

            {/* Backend status during research; a simple activity indicator for document chat. */}
            {isThinking && (
              <div className="py-4">
                <div className="mb-3 flex items-center gap-2">
                  <Sparkle className="text-violet-500" />
                  <span className="text-sm font-semibold text-slate-900 dark:text-white">Nexora</span>
                  <span className="text-xs text-slate-400 dark:text-slate-500">just now</span>
                </div>

                <div className="mb-4 flex items-center gap-2">
                  <Sparkle className="text-violet-400 dark:text-violet-300" />
                  <span className="text-sm font-medium text-slate-700 dark:text-slate-300">
                    {progressMessage || "Thinking…"}
                  </span>
                  <span className="thinking-dots text-violet-400">
                    <span>•</span><span>•</span><span>•</span>
                  </span>
                </div>

              </div>
            )}

            <div ref={messagesEndRef} />
          </div>
        )}

        {/* Item 4: selection as a popup over the thread, which stays
            visible (dimmed) behind it -- not a page navigation. */}
        {isSelectionModalOpen && deepSearchStage === "paused_for_selection" && (
          <CandidateSelectionModal
            candidates={candidates}
            selectedIndices={selectedIndices}
            onSelectionChange={updateCandidateSelection}
            onSubmit={() => void handleSubmitSelection()}
            onClose={() => setIsSelectionModalOpen(false)}
            isSubmitting={isSubmittingSelection}
            submissionError={selectionError}
          />
        )}
      </div>

      <input
        ref={fileRef}
        type="file"
        accept=".pdf"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) handleFileUpload(file);
          e.target.value = "";
        }}
      />
    </CardShell>
  );
}
