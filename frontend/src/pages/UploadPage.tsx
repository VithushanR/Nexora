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
      <div className="flex h-full flex-col items-center justify-center px-6">
        <h1 className="mb-2 text-2xl font-semibold text-slate-900">
          Upload a paper
        </h1>
        <p className="mb-8 text-center text-slate-500">
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
          className="flex w-full max-w-md cursor-pointer flex-col items-center rounded-2xl border-2 border-dashed border-slate-300 bg-white px-6 py-12 text-center transition hover:border-blue-400"
        >
          {uploading ? (
            <>
              <div className="mb-3 h-8 w-8 animate-spin rounded-full border-2 border-slate-200 border-t-blue-600" />
              <p className="text-sm text-slate-500">Uploading…</p>
            </>
          ) : (
            <>
              <svg
                width="40"
                height="40"
                viewBox="0 0 24 24"
                fill="none"
                className="mb-3 text-slate-400"
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
              <p className="text-sm font-medium text-slate-700">
                Drop a PDF here or click to browse
              </p>
              <p className="mt-1 text-xs text-slate-400">Max {MAX_SIZE_MB} MB</p>
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

        {error && <p className="mt-4 text-sm text-rose-600">{error}</p>}
      </div>
    );
  }

  return (
    <div className="mx-auto flex h-full max-w-3xl flex-col px-6 py-8">
      <div className="mb-4">
        <h1 className="text-xl font-semibold text-slate-900">{doc.title}</h1>
        <p className="text-sm text-slate-500">{doc.n_pages} pages</p>
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto rounded-xl border border-slate-200 bg-white p-4">
        {messages.length === 0 && (
          <p className="text-xs text-slate-400">
            Ask a question about this paper.
          </p>
        )}
        {messages.map((m) => (
          <div
            key={m.id}
            className={m.role === "user" ? "text-right" : "text-left"}
          >
            <div
              className={`inline-block max-w-[85%] rounded-2xl px-3 py-2 text-sm ${
                m.role === "user"
                  ? "bg-blue-600 text-white"
                  : "bg-slate-100 text-slate-800"
              }`}
            >
              {m.content}
            </div>
            {m.pages && m.pages.length > 0 && (
              <p className="mt-1 text-[10px] text-slate-400">
                Pages: {m.pages.join(", ")}
              </p>
            )}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      <div className="mt-3">
        <div className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 focus-within:border-blue-500">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") send();
            }}
            placeholder="Ask about the paper…"
            className="flex-1 bg-transparent text-sm outline-none"
          />
          <button
            onClick={send}
            disabled={sending || !input.trim()}
            className="text-sm font-medium text-blue-600 disabled:opacity-40"
          >
            Send
          </button>
        </div>
      </div>
    </div>
  );
}
