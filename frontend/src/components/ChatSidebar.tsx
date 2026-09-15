// Copilot chat panel on ReportPage, with a Report/Web mode toggle that
// determines which backend retrieval path POST /chat uses.
// TODO: implement message list, input box, mode toggle, call api/client.ts.

import { useEffect, useRef, useState } from "react";
import { indexCopilot, sendCopilotMessage, addToEvidence, getCopilotHistory, ApiError } from "../api/client";
import type { CopilotChatResponse } from "../types";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  mode?: "report" | "web";
  sources?: CopilotChatResponse["sources"];
  added?: boolean;
}

export default function ChatSidebar({ threadId }: { threadId: string }) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [mode, setMode] = useState<"report" | "auto">("report");
  const [sending, setSending] = useState(false);
  const [indexed, setIndexed] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;

    async function init() {
      try {
        await indexCopilot(threadId);
        if (!cancelled) setIndexed(true);
      } catch {
        if (!cancelled) setIndexed(false);
      }

      try {
        const history = await getCopilotHistory(threadId);
        if (!cancelled && history.length > 0) {
          setMessages(
            history.map((h) => ({
              id: h.message_id,
              role: h.role,
              content: h.content,
              mode: h.mode,
            }))
          );
        }
      } catch {
        // history load failed — start fresh
      }
    }

    init();
    return () => {
      cancelled = true;
    };
  }, [threadId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function send() {
    const text = input.trim();
    if (!text || sending) return;
    setInput("");
    setMessages((m) => [...m, { id: `u-${Date.now()}`, role: "user", content: text }]);
    setSending(true);
    try {
      const res = await sendCopilotMessage(threadId, text, mode);
      setMessages((m) => [
        ...m,
        { id: res.message_id, role: "assistant", content: res.answer, mode: res.mode, sources: res.sources },
      ]);
    } catch (e) {
      setMessages((m) => [
        ...m,
        {
          id: `err-${Date.now()}`,
          role: "assistant",
          content: e instanceof ApiError ? e.message : "Something went wrong answering that.",
        },
      ]);
    } finally {
      setSending(false);
    }
  }

  async function handleAddToEvidence(messageId: string) {
    try {
      await addToEvidence(threadId, messageId);
      setMessages((m) => m.map((msg) => (msg.id === messageId ? { ...msg, added: true } : msg)));
    } catch {
      // non-critical action -- fail silently
    }
  }

  return (
    <aside className="flex h-full w-full flex-col border-l border-slate-200 bg-white">
      <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
        <h2 className="text-sm font-semibold text-slate-900">Copilot</h2>
        <div className="flex rounded-full bg-slate-100 p-0.5 text-xs">
          <button
            onClick={() => setMode("report")}
            className={`rounded-full px-3 py-1 ${mode === "report" ? "bg-white text-slate-900 shadow" : "text-slate-500"}`}
          >
            Report
          </button>
          <button
            onClick={() => setMode("auto")}
            className={`rounded-full px-3 py-1 ${mode === "auto" ? "bg-white text-slate-900 shadow" : "text-slate-500"}`}
          >
            Report + Web
          </button>
        </div>
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto px-4 py-4">
        {messages.length === 0 && (
          <p className="text-xs text-slate-400">
            {indexed ? "Ask about the evidence, contradictions, or gaps in this report." : "Indexing the report…"}
          </p>
        )}
        {messages.map((m) => (
          <div key={m.id} className={m.role === "user" ? "text-right" : "text-left"}>
            <div
              className={`inline-block max-w-[90%] rounded-2xl px-3 py-2 text-sm ${
                m.role === "user" ? "bg-blue-600 text-white" : "bg-slate-100 text-slate-800"
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
        <div ref={bottomRef} />
      </div>

      <div className="border-t border-slate-200 p-3">
        <div className="flex items-center gap-2 rounded-xl border border-slate-200 px-3 py-2 focus-within:border-blue-500">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") send();
            }}
            placeholder="Ask the Copilot…"
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
    </aside>
  );
}