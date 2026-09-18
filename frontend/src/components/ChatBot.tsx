import { useEffect, useRef, useState } from "react";
import { uploadDocument, sendDocumentChat, ApiError } from "../api/client";
import type { DocumentUploadResponse } from "../types";

const MAX_SIZE_MB = 20;
const SUGGESTIONS = [
  "Create a summary of this document",
  "What are the key findings?",
  "Expand on the methodology",
];

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  pages?: number[];
}

export default function ChatBot() {
  const [open, setOpen] = useState(false);
  const [doc, setDoc] = useState<DocumentUploadResponse | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function handleFile(file: File) {
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      setError("Only PDF files are accepted.");
      return;
    }
    if (file.size > MAX_SIZE_MB * 1024 * 1024) {
      setError(`File exceeds the ${MAX_SIZE_MB} MB limit.`);
      return;
    }
    setUploading(true);
    setError(null);
    try {
      const result = await uploadDocument(file);
      setDoc(result);
      setMessages([]);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Upload failed.");
    } finally {
      setUploading(false);
    }
  }

  async function send(text?: string) {
    const msg = (text ?? input).trim();
    if (!msg || !doc || sending) return;
    if (!text) setInput("");

    setMessages((m) => [
      ...m,
      { id: `u-${Date.now()}`, role: "user", content: msg },
    ]);
    setSending(true);
    try {
      const res = await sendDocumentChat(doc.document_id, msg);
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
      setSending(false);
    }
  }

  function newChat() {
    setDoc(null);
    setMessages([]);
    setInput("");
    setError(null);
  }

  return (
    <>
      {/* -------- Floating button -------- */}
      {!open && (
        <button
          onClick={() => setOpen(true)}
          aria-label="Open chat"
          className="fixed bottom-6 right-6 z-50 flex h-14 w-14 items-center justify-center rounded-full bg-gradient-to-br from-blue-500 to-indigo-600 text-white shadow-lg transition-all hover:scale-105 hover:shadow-xl active:scale-95"
        >
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none">
            <path
              d="M12 2a1 1 0 011 1v1.07A8.001 8.001 0 0120 12a8 8 0 01-16 0 8.001 8.001 0 017-7.93V3a1 1 0 011-1z"
              fill="white"
              fillOpacity="0.15"
            />
            <rect x="4" y="5" width="16" height="12" rx="4" stroke="white" strokeWidth="1.5" />
            <circle cx="9.5" cy="11" r="1.5" fill="white" />
            <circle cx="14.5" cy="11" r="1.5" fill="white" />
            <path d="M12 2v3" stroke="white" strokeWidth="1.5" strokeLinecap="round" />
            <path d="M8 17l1.5 3h5l1.5-3" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      )}

      {/* -------- Chat panel -------- */}
      {open && (
        <div
          className="fixed bottom-6 right-6 z-50 flex flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl"
          style={{
            width: "min(400px, calc(100vw - 2rem))",
            height: "min(620px, calc(100vh - 3rem))",
            animation: "chatPanelIn .2s ease-out",
          }}
        >
          {/* Header */}
          <div className="flex items-center justify-between border-b border-slate-100 px-4 py-2.5">
            <div className="flex items-center gap-1">
              <button
                onClick={newChat}
                title="New chat"
                className="rounded-lg p-1.5 text-slate-400 transition hover:bg-slate-100 hover:text-slate-600"
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                  <path d="M15 3h6v6M9 21H3v-6" />
                  <path d="M21 3l-7 7M3 21l7-7" />
                </svg>
              </button>
            </div>
            <button
              onClick={() => setOpen(false)}
              title="Close"
              className="rounded-lg p-1.5 text-slate-400 transition hover:bg-slate-100 hover:text-slate-600"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <path d="M18 6L6 18M6 6l12 12" />
              </svg>
            </button>
          </div>

          {/* Body */}
          <div className="flex-1 overflow-y-auto px-5 py-4">
            {messages.length === 0 ? (
              <div className="flex h-full flex-col">
                <h2 className="text-[22px] font-semibold leading-snug text-slate-900">
                  Hey, what&apos;s on your mind today?
                </h2>

                <div className="flex-1" />

                {doc && (
                  <div className="space-y-2 pb-1">
                    {SUGGESTIONS.map((s) => (
                      <button
                        key={s}
                        onClick={() => send(s)}
                        className="block w-full rounded-xl border border-slate-200 px-4 py-2.5 text-left text-[13px] text-slate-600 transition hover:border-blue-300 hover:bg-blue-50/40 hover:text-blue-700"
                      >
                        {s}
                      </button>
                    ))}
                  </div>
                )}

                {!doc && !uploading && (
                  <p className="pb-1 text-xs text-slate-400">
                    Attach a PDF below to start chatting about it.
                  </p>
                )}
              </div>
            ) : (
              <div className="space-y-3">
                {messages.map((m) => (
                  <div key={m.id} className={m.role === "user" ? "text-right" : "text-left"}>
                    <div
                      className={`inline-block max-w-[85%] rounded-2xl px-3.5 py-2 text-[13px] leading-relaxed ${
                        m.role === "user"
                          ? "bg-blue-600 text-white"
                          : "bg-slate-100 text-slate-800"
                      }`}
                    >
                      {m.content}
                    </div>
                    {m.pages && m.pages.length > 0 && (
                      <p className="mt-0.5 text-[10px] text-slate-400">
                        Pages: {m.pages.join(", ")}
                      </p>
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
            )}
          </div>

          {/* Footer */}
          <div className="border-t border-slate-100 px-4 pb-4 pt-3">
            {error && (
              <p className="mb-2 rounded-lg bg-rose-50 px-3 py-1.5 text-xs text-rose-600">
                {error}
              </p>
            )}

            {uploading && (
              <div className="mb-2 flex items-center gap-2 rounded-xl bg-slate-50 px-3 py-2.5 text-xs text-slate-500">
                <div className="h-4 w-4 animate-spin rounded-full border-2 border-slate-200 border-t-blue-600" />
                Uploading document…
              </div>
            )}

            {doc && !uploading && (
              <div className="mb-2 flex items-center gap-2 rounded-xl bg-slate-50 px-3 py-2.5">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" className="shrink-0 text-rose-500">
                  <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8l-6-6z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
                  <path d="M14 2v6h6" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
                  <path d="M9 13h6M9 17h4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                </svg>
                <span className="flex-1 truncate text-xs font-medium text-slate-700">
                  {doc.title}
                </span>
                <span className="shrink-0 text-[10px] text-slate-400">{doc.n_pages} pages</span>
              </div>
            )}

            <div className="flex items-center gap-1 rounded-xl border border-slate-200 bg-white px-2 py-1.5 focus-within:border-blue-400 focus-within:ring-2 focus-within:ring-blue-100">
              <button
                onClick={() => fileRef.current?.click()}
                title="Upload PDF"
                className="shrink-0 rounded-lg p-1.5 text-slate-400 transition hover:bg-slate-100 hover:text-slate-600"
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                  <path d="M12 5v14M5 12h14" />
                </svg>
              </button>
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) send();
                }}
                placeholder={doc ? "Ask about your document…" : "Upload a PDF to start…"}
                disabled={!doc}
                className="min-w-0 flex-1 bg-transparent py-1 text-sm text-slate-800 outline-none placeholder:text-slate-400 disabled:cursor-not-allowed"
              />
              <button
                onClick={() => send()}
                disabled={sending || !input.trim() || !doc}
                title="Send"
                className="shrink-0 rounded-lg p-1.5 text-blue-600 transition hover:bg-blue-50 disabled:opacity-30"
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M3.478 2.405a.75.75 0 00-.926.94l2.432 7.905H13.5a.75.75 0 010 1.5H4.984l-2.432 7.905a.75.75 0 00.926.94l18.04-8.25a.75.75 0 000-1.39L3.478 2.405z" />
                </svg>
              </button>
            </div>
          </div>
        </div>
      )}

      <input
        ref={fileRef}
        type="file"
        accept=".pdf"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) handleFile(file);
          e.target.value = "";
        }}
      />

      <style>{`
        @keyframes chatPanelIn {
          from { opacity: 0; transform: translateY(12px) scale(0.96); }
          to   { opacity: 1; transform: translateY(0) scale(1); }
        }
      `}</style>
    </>
  );
}
