import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

import {
  ApiClientError,
  ApiConfigurationError,
  ApiError,
  ApiNetworkError,
  getResearchStatus,
  startResearch,
  uploadDocument,
  sendDocumentChat,
} from "../api/client";
import { useAuth } from "../auth/AuthContext";
import GoogleSignInButton from "../auth/GoogleSignInButton";
import type { DocumentUploadResponse } from "../types";

type Mode = "chat" | "deep-search";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  pages?: number[];
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

function Sparkle({ className = "", size = 16 }: { className?: string; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" className={className}>
      <path d="M12 2l2.4 7.6L22 12l-7.6 2.4L12 22l-2.4-7.6L2 12l7.6-2.4z" />
    </svg>
  );
}

export default function SearchPage() {
  const navigate = useNavigate();
  const { status, signOut } = useAuth();

  const [mode, setMode] = useState<Mode>("chat");
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [isThinking, setIsThinking] = useState(false);
  const [progressMessage, setProgressMessage] = useState("");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [needsSignIn, setNeedsSignIn] = useState(false);

  const [doc, setDoc] = useState<DocumentUploadResponse | null>(null);
  const [uploading, setUploading] = useState(false);

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
      setErrorMessage(e instanceof ApiError ? e.message : "Upload failed.");
    } finally {
      setUploading(false);
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

      setMessages((m) => [...m, { id: `u-${Date.now()}`, role: "user", content: trimmed }]);
      setInput("");
      setIsThinking(true);
      setProgressMessage("Starting research…");

      try {
        const { thread_id } = await startResearch({ domain: trimmed });
        // Match the report screen: poll once now, then schedule the next request
        // only after the current one has completed.
        async function checkStatus(): Promise<void> {
          try {
            const response = await getResearchStatus(thread_id);
            if (!pollActiveRef.current) return;
            if (response.status === "paused_for_selection") {
              setIsThinking(false);
              navigate(`/select/${thread_id}`);
              return;
            }
            if (response.status === "error") {
              const detail = response.detail?.trim();
              setErrorMessage(
                detail && detail !== "Research processing failed."
                  ? detail
                  : "Research stopped while finding or screening papers. Please try again; if it happens again, check the backend server log for the cause.",
              );
              setIsThinking(false);
              return;
            }
            if (response.status === "running_agent2") {
              setProgressMessage(`running_agent2 — ${response.detail || "Research is retrieving and screening papers."}`);
              pollTimeoutRef.current = window.setTimeout(() => void checkStatus(), 2_000);
              return;
            }
            setErrorMessage(`Research returned an unexpected status: ${response.status}.`);
            setIsThinking(false);
          } catch (error) {
            if (!pollActiveRef.current) return;
            if (error instanceof ApiClientError && error.status === 401) {
              signOut();
              setNeedsSignIn(true);
            }
            setErrorMessage(userFacingError(error));
            setIsThinking(false);
          }
        }
        await checkStatus();
      } catch (error) {
        if (error instanceof ApiClientError && error.status === 401) {
          signOut();
          setNeedsSignIn(true);
        }
        setErrorMessage(userFacingError(error));
        setIsThinking(false);
      }
    } else {
      setProgressMessage("");
      if (!doc) {
        setMessages((m) => [
          ...m,
          { id: `u-${Date.now()}`, role: "user", content: trimmed },
        ]);
        setInput("");
        setMessages((m) => [...m, {
          id: `a-${Date.now()}`,
          role: "assistant",
          content: "Upload a document using the **+** button to start chatting about it, or switch to **Deep Search** to explore academic research.",
        }]);
        return;
      }

      setMessages((m) => [...m, { id: `u-${Date.now()}`, role: "user", content: trimmed }]);
      setInput("");
      setIsThinking(true);

      try {
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
      } catch (e) {
        setMessages((m) => [
          ...m,
          {
            id: `err-${Date.now()}`,
            role: "assistant",
            content: e instanceof ApiError ? e.message : "Something went wrong.",
          },
        ]);
      } finally {
        setIsThinking(false);
      }
    }
  }

  const hasMessages = messages.length > 0;

  return (
    <div className="flex h-full flex-col">
      {/* Messages / empty state */}
      <div className="flex-1 overflow-y-auto">
        {!hasMessages ? (
          <div className="flex h-full flex-col items-center justify-center px-4 bg-gradient-to-b from-violet-50/80 via-slate-50 to-white dark:from-slate-900 dark:via-slate-900 dark:to-slate-900">
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
          <div className="mx-auto max-w-3xl space-y-1 px-4 py-8 bg-white dark:bg-slate-900">
            {messages.map((m) => (
              <div key={m.id} className="py-3">
                {m.role === "user" ? (
                  <div className="flex justify-end">
                    <div className="max-w-[80%] rounded-2xl bg-slate-100 px-4 py-3 text-[15px] leading-relaxed text-slate-800 dark:bg-slate-800 dark:text-slate-200">
                      {m.content}
                    </div>
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
                    {progressMessage || "Searching the document…"}
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
      </div>

      {/* Input area */}
      <div className="relative bg-white px-4 pb-4 pt-3 dark:bg-slate-900">
        {(isThinking || uploading) && (
          <div className="thought-line absolute inset-x-0 top-0 z-10" />
        )}

        <div className="mx-auto max-w-3xl">
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

          {/* Input box with floating mode toggle */}
          <div className="relative pt-5">
            {/* Floating mode toggle */}
            <div className="absolute -top-0 left-1/2 z-20 -translate-x-1/2">
              <div className="flex items-center gap-0.5 rounded-full border border-slate-200 bg-white p-0.5 shadow-sm dark:border-slate-700 dark:bg-slate-800">
                <button
                  onClick={() => setMode("chat")}
                  disabled={isThinking}
                  className={`flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-xs font-medium transition ${
                    mode === "chat"
                      ? "bg-violet-100 text-violet-700 dark:bg-violet-900/50 dark:text-violet-300"
                      : "text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200"
                  }`}
                >
                  <Sparkle size={12} />
                  Chat
                </button>
                <button
                  onClick={() => setMode("deep-search")}
                  disabled={isThinking}
                  className={`flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-xs font-medium transition ${
                    mode === "deep-search"
                      ? "bg-violet-100 text-violet-700 dark:bg-violet-900/50 dark:text-violet-300"
                      : "text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200"
                  }`}
                >
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                    <circle cx="11" cy="11" r="8" />
                    <path d="M21 21l-4.35-4.35" />
                  </svg>
                  Deep Search
                </button>
              </div>
            </div>

            {/* Input container */}
            <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm transition-shadow focus-within:border-violet-300 focus-within:shadow-md focus-within:ring-1 focus-within:ring-violet-100 dark:border-slate-700 dark:bg-slate-800 dark:shadow-none dark:focus-within:border-violet-700 dark:focus-within:ring-violet-900/30">
              <div className="flex items-center gap-3 px-4 py-3">
                <button
                  onClick={() => fileRef.current?.click()}
                  disabled={uploading}
                  title="Upload document"
                  className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-slate-400 transition hover:bg-violet-50 hover:text-violet-600 disabled:opacity-40 dark:hover:bg-violet-900/30 dark:hover:text-violet-400"
                >
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
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
                  placeholder="Message Nexora…"
                  rows={1}
                  disabled={isThinking}
                  className="block min-h-[28px] flex-1 resize-none bg-transparent text-[15px] leading-7 text-slate-800 outline-none placeholder:text-slate-400 disabled:cursor-not-allowed dark:text-slate-200 dark:placeholder:text-slate-500"
                />
                <button
                  onClick={handleSubmit}
                  disabled={isThinking || !input.trim()}
                  title="Send"
                  className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-violet-500 to-purple-600 text-white shadow-sm transition hover:shadow-md disabled:from-slate-200 disabled:to-slate-200 disabled:text-slate-400 disabled:shadow-none dark:disabled:from-slate-700 dark:disabled:to-slate-700 dark:disabled:text-slate-500"
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z" />
                  </svg>
                </button>
              </div>
            </div>
          </div>

          {/* Bottom hints */}
          <div className="mt-2 flex items-center justify-between px-1">
            <button
              onClick={() => fileRef.current?.click()}
              className="flex items-center gap-1 text-xs text-slate-400 transition hover:text-violet-500 dark:text-slate-500 dark:hover:text-violet-400"
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M17 8l-5-5-5 5M12 3v12" />
              </svg>
              Drop PDFs, docs, or links here
            </button>
            <span className="text-xs text-slate-400 dark:text-slate-500">
              Enter to send · Shift + Enter for newline
            </span>
          </div>
        </div>
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
    </div>
  );
}
