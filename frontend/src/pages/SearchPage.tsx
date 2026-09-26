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
  deleteDocument,
  getChatHistory,
  listDocuments,
  sendChat,
  indexCopilot,
} from "../api/client";
import { NEW_SESSION_EVENT, createSessionId, getOrCreateSessionId, storeSessionId } from "../chatSession";
import { useAuth } from "../auth/AuthContext";
import GoogleSignInButton from "../auth/GoogleSignInButton";
import { addHistory, getHistory } from "../components/Sidebar";
import CardShell from "../components/CardShell";
import CandidateSelectionModal from "../components/CandidateSelectionModal";
import ReportView from "../components/ReportView";
import ChatSourceChips from "../components/ChatSourceChips";
import SessionDocumentsMenu from "../components/SessionDocumentsMenu";
import type { CandidatePaper, ChatHistoryMessage, ChatSource, DocumentUploadResponse, ResearchStatus } from "../types";

// Three modes: Chat (general, or grounded automatically on this thread's
// finished report and/or attached documents), Web Search (always live web,
// never overridden by thread context), and Deep Search (the paper pipeline).
type Mode = "chat" | "web" | "deep-search";

// Item 4/5/7: the whole Deep Search lifecycle now lives in this one page,
// as one continuous chat thread -- no navigation to a separate selection
// or report page. "idle" = no active Deep Search thread in this session.
type DeepSearchStage = "idle" | "running_agent2" | "paused_for_selection" | "running_synthesis" | "done" | "error";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  /** Where an assistant answer came from (report / documents / web pages). */
  sources?: ChatSource[];
  /** Documents that were attached when this user message was sent. */
  documents?: DocumentUploadResponse[];
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

// After a refresh the page has no memory of what was sent. A document counts as
// already sent if any stored user message is newer than its upload -- every
// Chat-mode message goes out with all of the session's documents attached.
function sentDocumentIdsFromHistory(documents: DocumentUploadResponse[], history: ChatHistoryMessage[]): Set<string> {
  const userMessageTimes = history.filter((entry) => entry.role === "user").map((entry) => Date.parse(entry.created_at));
  const sent = new Set<string>();
  for (const document of documents) {
    const uploadedAt = document.created_at ? Date.parse(document.created_at) : NaN;
    if (!Number.isNaN(uploadedAt) && userMessageTimes.some((sentAt) => sentAt > uploadedAt)) {
      sent.add(document.document_id);
    }
  }
  return sent;
}

function messageFromHistory(entry: ChatHistoryMessage): Message {
  return {
    id: entry.message_id,
    role: entry.role,
    content: entry.content,
    sources: entry.role === "assistant" ? entry.sources : undefined,
  };
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

  // The chat session this page belongs to (see chatSession.ts). Messages and
  // uploads are stored under it, so a refresh reloads them from the server.
  const [sessionId, setSessionId] = useState(getOrCreateSessionId);

  // Documents uploaded in THIS session only -- shown in the folder panel and
  // used to ground Chat-mode answers. Restored from the server on load.
  const [documents, setDocuments] = useState<DocumentUploadResponse[]>([]);
  // Documents already sent with a chat message: those chips are done, only
  // documents attached since the last message show as "attached to this chat".
  const [sentDocumentIds, setSentDocumentIds] = useState<Set<string>>(new Set());
  const [uploading, setUploading] = useState(false);
  const [isDraggingFile, setIsDraggingFile] = useState(false);
  const dragDepthRef = useRef(0);

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

  // Restore this session's documents and conversation from the server. Inside
  // a resumed Deep Search thread the messages are appended after its report
  // is shown -- see the resume effect below -- but the history is still what
  // tells us which documents were already sent.
  useEffect(() => {
    if (status !== "signed-in") return;
    let cancelled = false;
    void (async () => {
      try {
        const restoredDocuments = await listDocuments({ sessionId, threadId: routeThreadId });
        const history = await getChatHistory({ sessionId, threadId: routeThreadId });
        if (cancelled) return;
        setDocuments(restoredDocuments);
        setSentDocumentIds(sentDocumentIdsFromHistory(restoredDocuments, history));
        if (!routeThreadId && history.length > 0) {
          setMessages((current) => (current.length === 0 ? history.map(messageFromHistory) : current));
        }
      } catch (error) {
        if (!cancelled && error instanceof ApiClientError && error.status === 401) handleUnauthorized();
        // Anything else: the page still works, it just starts empty.
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status, sessionId, routeThreadId]);

  // "New search": a brand-new session -- fresh id, empty thread, no documents.
  useEffect(() => {
    function startNewSession() {
      window.clearTimeout(pollTimeoutRef.current);
      const freshId = createSessionId();
      storeSessionId(freshId);
      setSessionId(freshId);
      setMessages([]);
      setDocuments([]);
      setSentDocumentIds(new Set());
      setThreadId(null);
      setDeepSearchStage("idle");
      setCandidates([]);
      setSelectedIndices([]);
      setIsSelectionModalOpen(false);
      setIsThinking(false);
      setProgressMessage("");
      setErrorMessage(null);
      setInput("");
    }
    window.addEventListener(NEW_SESSION_EVENT, startNewSession);
    return () => window.removeEventListener(NEW_SESSION_EVENT, startNewSession);
  }, []);

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
          // Index the finished report as soon as it's available, so Chat mode
          // can ground on it the moment the thread reaches "done". Best-
          // effort: chat degrades gracefully (no report hits, not an error)
          // if this hasn't finished yet, so a failure here is logged and
          // swallowed rather than surfaced as a research error.
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
    void (async () => {
      await pollThread(routeThreadId);
      try {
        const history = await getChatHistory({ sessionId, threadId: routeThreadId });
        if (history.length > 0 && pollActiveRef.current) {
          setMessages((current) => {
            const known = new Set(current.map((message) => message.id));
            return [...current, ...history.filter((entry) => !known.has(entry.message_id)).map(messageFromHistory)];
          });
        }
      } catch {
        // History is a nicety on resume; the report itself already rendered.
      }
    })();
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
      const result = await uploadDocument(file, { sessionId, threadId });
      setDocuments((current) => [...current, result]);
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

  async function handleFiles(files: FileList | File[]) {
    for (const file of Array.from(files)) {
      await handleFileUpload(file);
    }
  }

  async function removeDocument(document: DocumentUploadResponse) {
    try {
      await deleteDocument(document.document_id);
      setDocuments((current) => current.filter((d) => d.document_id !== document.document_id));
    } catch (e) {
      setErrorMessage(e instanceof ApiError ? e.message : "The document could not be removed.");
    }
  }

  function hasFiles(event: React.DragEvent): boolean {
    return Array.from(event.dataTransfer.types).includes("Files");
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
    // Documents attached since the last chat message -- shown once, on the
    // message that first sends them.
    const pendingDocuments = documents.filter((d) => !sentDocumentIds.has(d.document_id));

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
      // One endpoint for Chat and Web Search. The backend decides how to
      // answer: web mode always searches the web; chat mode grounds on this
      // thread's finished report and/or the attached documents when there
      // are any (both at once, cited separately), else replies
      // conversationally. The client just says which mode and what's attached.
      const reportThreadId = deepSearchStage === "done" ? threadId : null;
      const documentIds = documents.map((d) => d.document_id);
      const isGrounded = mode === "chat" && (reportThreadId !== null || documentIds.length > 0);

      setMessages((m) => [
        ...m,
        {
          id: nextMessageId("u"),
          role: "user",
          content: trimmed,
          documents: mode === "chat" && pendingDocuments.length > 0 ? pendingDocuments : undefined,
        },
      ]);
      setInput("");
      if (mode === "chat" && documentIds.length > 0) {
        setSentDocumentIds((current) => new Set([...current, ...documentIds]));
      }
      setIsThinking(true);
      setProgressMessage(mode === "web" ? "Searching the web…" : isGrounded ? "Searching your sources…" : "Thinking…");

      try {
        const res = await sendChat({
          message: trimmed,
          mode,
          sessionId,
          threadId: reportThreadId,
          documentIds,
        });
        setMessages((m) => [
          ...m,
          { id: res.message_id, role: "assistant", content: res.reply, sources: res.sources },
        ]);
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
      : mode === "web"
        ? "border-emerald-300 bg-emerald-50/40 focus-within:ring-1 focus-within:ring-emerald-200 dark:border-emerald-700 dark:bg-emerald-950/20 dark:focus-within:ring-emerald-800"
        : "border-slate-200 bg-white focus-within:border-violet-300 focus-within:ring-1 focus-within:ring-violet-100 dark:border-slate-700 dark:bg-slate-800 dark:focus-within:border-violet-700 dark:focus-within:ring-violet-900/30";

  const inputBar = (
    <div className="px-3 pb-2 pt-2">
      {/* No mx-auto/max-w-3xl here -- that inner width cap (while the box
          itself already spans the card's width) was what created the empty
          side gutters. Content now fills the box's actual width. */}
      <div>
        {/* Attached documents not yet sent with a message */}
        {documents
          .filter((d) => !sentDocumentIds.has(d.document_id))
          .map((d) => (
            <div key={d.document_id} className="mb-2 flex items-center gap-2 rounded-xl bg-violet-50 px-3 py-2 dark:bg-violet-950/30">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" className="shrink-0 text-violet-500">
                <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8l-6-6z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
                <path d="M14 2v6h6" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
              </svg>
              <span className="flex-1 truncate text-xs font-medium text-slate-700 dark:text-slate-300">{d.title}</span>
              <span className="shrink-0 text-[10px] text-slate-400">{d.n_pages} {d.n_pages === 1 ? "page" : "pages"} &middot; attached to this chat</span>
              <button
                onClick={() => void removeDocument(d)}
                title="Remove document"
                aria-label={`Remove ${d.title}`}
                className="ml-1 rounded p-0.5 text-slate-400 transition hover:bg-violet-100 hover:text-slate-600 dark:hover:bg-violet-900/40 dark:hover:text-slate-300"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                  <path d="M18 6L6 18M6 6l12 12" />
                </svg>
              </button>
            </div>
          ))}

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
            title="Attach a PDF"
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
            placeholder={
              deepSearchStage === "running_synthesis"
                ? "Analyzing selected papers…"
                : mode === "web"
                  ? "Search the web…"
                  : "Message Nexora…"
            }
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
              onClick={() => setMode("web")}
              disabled={inputDisabled}
              title="Web Search"
              className={`flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium transition ${
                mode === "web"
                  ? "bg-violet-100 text-violet-700 dark:bg-violet-900/50 dark:text-violet-300"
                  : "text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200"
              }`}
            >
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <circle cx="12" cy="12" r="9" />
                <path d="M3 12h18M12 3a14 14 0 010 18M12 3a14 14 0 000 18" />
              </svg>
              Web Search
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
            Drop a PDF here or click + to attach
          </button>
          <span className="text-[11px] text-slate-400 dark:text-slate-500">
            Enter to send · Shift + Enter for newline
          </span>
        </div>
      </div>
    </div>
  );

  return (
    <div
      className="relative h-full"
      onDragEnter={(event) => {
        if (!hasFiles(event)) return;
        event.preventDefault();
        dragDepthRef.current += 1;
        setIsDraggingFile(true);
      }}
      onDragOver={(event) => {
        if (hasFiles(event)) event.preventDefault();
      }}
      onDragLeave={(event) => {
        if (!hasFiles(event)) return;
        dragDepthRef.current = Math.max(0, dragDepthRef.current - 1);
        if (dragDepthRef.current === 0) setIsDraggingFile(false);
      }}
      onDrop={(event) => {
        if (!hasFiles(event)) return;
        event.preventDefault();
        dragDepthRef.current = 0;
        setIsDraggingFile(false);
        void handleFiles(event.dataTransfer.files);
      }}
    >
    <SessionDocumentsMenu
      documents={documents}
      onRemoved={(documentId) => setDocuments((current) => current.filter((d) => d.document_id !== documentId))}
    />
    {isDraggingFile && (
      <div className="pointer-events-none absolute inset-3 z-40 flex items-center justify-center rounded-3xl border-2 border-dashed border-violet-400 bg-violet-50/80 text-sm font-medium text-violet-700 backdrop-blur-sm dark:border-violet-500 dark:bg-violet-950/70 dark:text-violet-300 sm:inset-6 lg:inset-8">
        Drop a PDF to attach it to this chat
      </div>
    )}
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
                  <div className="flex flex-col items-end gap-2">
                    {m.documents?.map((d) => (
                      <div key={d.document_id} className="flex w-[365px] max-w-[80%] items-center gap-2 rounded-xl bg-violet-50 px-3 py-2 dark:bg-violet-950/30">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" className="shrink-0 text-violet-500">
                          <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8l-6-6z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
                          <path d="M14 2v6h6" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
                        </svg>
                        <span className="min-w-0 flex-1 truncate text-left text-xs font-medium text-slate-700 dark:text-slate-300">
                          {d.title}
                        </span>
                        <span className="shrink-0 text-[10px] text-slate-400">{d.n_pages} {d.n_pages === 1 ? "page" : "pages"}</span>
                      </div>
                    ))}
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
                      {m.sources && <ChatSourceChips sources={m.sources} />}
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
        multiple
        className="hidden"
        onChange={(e) => {
          if (e.target.files) void handleFiles(e.target.files);
          e.target.value = "";
        }}
      />
    </CardShell>
    </div>
  );
}
