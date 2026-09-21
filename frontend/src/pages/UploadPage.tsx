import { useRef, useState } from "react";
import { uploadDocument, sendDocumentChat, ApiError } from "../api/client";
import type { DocumentUploadResponse } from "../types";

const MAX_SIZE_MB = 20;

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  pages?: number[];
}

export default function UploadPage() {
  const [doc, setDoc] = useState<DocumentUploadResponse | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

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
    } catch (e) {
      setError(
        e instanceof ApiError ? e.message : "Upload failed. Please try again."
      );
    } finally {
      setUploading(false);
    }
  }

  async function send() {
    if (!doc || !input.trim() || sending) return;
    const text = input.trim();
    setInput("");
    setMessages((m) => [
      ...m,
      { id: `u-${Date.now()}`, role: "user", content: text },
    ]);
    setSending(true);
    try {
      const res = await sendDocumentChat(doc.document_id, text);
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
          content:
            e instanceof ApiError ? e.message : "Something went wrong.",
        },
      ]);
    } finally {
      setSending(false);
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }

  if (!doc) {
    return (
      <div className="flex h-full flex-col items-center justify-center px-6 bg-gradient-to-b from-violet-50/80 via-slate-50 to-white dark:from-slate-900 dark:via-slate-900 dark:to-slate-900">
        <img
          src="/nexora-logo.png"
          alt="Nexora"
          className="mb-6 h-12 w-12 rounded-2xl object-cover shadow-lg shadow-violet-300/40 dark:shadow-violet-900/50"
        />
        <h1 className="mb-2 text-2xl font-bold text-slate-900 dark:text-white">
          Upload a paper
        </h1>
        <p className="mb-8 text-center text-slate-500 dark:text-slate-400">
          Upload a PDF and ask questions about it.
        </p>

        <div
          onClick={() => fileRef.current?.click()}
          onDragOver={(e) => {
            e.preventDefault();
            e.stopPropagation();
          }}
          onDrop={(e) => {
            e.preventDefault();
            e.stopPropagation();
            const file = e.dataTransfer.files?.[0];
            if (file) handleFile(file);
          }}
          className="flex w-full max-w-md cursor-pointer flex-col items-center rounded-2xl border-2 border-dashed border-slate-300 bg-white px-6 py-12 text-center shadow-sm transition hover:border-violet-400 hover:shadow-md dark:border-slate-600 dark:bg-slate-800 dark:hover:border-violet-500"
        >
          {uploading ? (
            <>
              <div className="mb-3 h-8 w-8 animate-spin rounded-full border-2 border-violet-200 border-t-violet-600 dark:border-slate-700 dark:border-t-violet-400" />
              <p className="text-sm text-slate-500 dark:text-slate-400">Uploading…</p>
            </>
          ) : (
            <>
              <svg
                width="40"
                height="40"
                viewBox="0 0 24 24"
                fill="none"
                className="mb-3 text-violet-400 dark:text-violet-500"
              >
                <path
                  d="M12 16V4m0 0L8 8m4-4l4 4"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
                <path
                  d="M20 16v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                />
              </svg>
              <p className="text-sm font-medium text-slate-700 dark:text-slate-300">
                Drop a PDF here or click to browse
              </p>
              <p className="mt-1 text-xs text-slate-400 dark:text-slate-500">Max {MAX_SIZE_MB} MB</p>
            </>
          )}
        </div>

        <input
          ref={fileRef}
          type="file"
          accept=".pdf"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) handleFile(file);
          }}
        />

        {error && (
          <p className="mt-4 rounded-xl bg-red-50 px-4 py-2 text-sm text-red-700 dark:bg-red-900/20 dark:text-red-400">{error}</p>
        )}
      </div>
    );
  }

  return (
    <div className="mx-auto flex h-full max-w-3xl flex-col px-6 py-8">
      <div className="mb-4">
        <div className="mb-3 flex items-center gap-2">
          <img src="/nexora-logo.png" alt="Nexora" className="h-7 w-7 rounded-lg object-cover" />
          <p className="text-sm font-semibold tracking-wide text-violet-600 dark:text-violet-400">Nexora</p>
        </div>
        <h1 className="text-xl font-bold text-slate-900 dark:text-white">{doc.title}</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400">{doc.n_pages} pages</p>
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-800/50">
        {messages.length === 0 && (
          <p className="text-xs text-slate-400 dark:text-slate-500">
            Ask a question about this paper.
          </p>
        )}
        {messages.map((m) => (
          <div
            key={m.id}
            className={m.role === "user" ? "flex justify-end" : "flex gap-3"}
          >
            {m.role === "assistant" && (
              <img
                src="/nexora-logo.png"
                alt="N"
                className="mt-0.5 h-6 w-6 shrink-0 rounded-lg object-cover"
              />
            )}
            <div
              className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-sm ${
                m.role === "user"
                  ? "bg-slate-100 text-slate-800 dark:bg-slate-700 dark:text-slate-200"
                  : "text-slate-700 dark:text-slate-300"
              }`}
            >
              {m.content}
              {m.pages && m.pages.length > 0 && (
                <p className="mt-1.5 text-[10px] text-slate-400 dark:text-slate-500">
                  Pages: {m.pages.join(", ")}
                </p>
              )}
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      <div className="mt-3">
        <div className="flex items-center gap-3 rounded-2xl border border-slate-200 bg-white px-4 py-3 shadow-sm transition focus-within:border-violet-300 focus-within:ring-1 focus-within:ring-violet-100 dark:border-slate-700 dark:bg-slate-800 dark:focus-within:border-violet-700 dark:focus-within:ring-violet-900/30">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") send();
            }}
            placeholder="Ask about the paper…"
            className="flex-1 bg-transparent text-sm text-slate-800 outline-none placeholder:text-slate-400 dark:text-slate-200 dark:placeholder:text-slate-500"
          />
          <button
            onClick={send}
            disabled={sending || !input.trim()}
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-violet-500 to-purple-600 text-white shadow-sm transition hover:shadow-md disabled:from-slate-200 disabled:to-slate-200 disabled:text-slate-400 disabled:shadow-none dark:disabled:from-slate-700 dark:disabled:to-slate-700 dark:disabled:text-slate-500"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
}
