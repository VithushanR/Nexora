// Folder icon (top-right, beside the theme toggle) + a small dropdown listing
// ONLY the documents uploaded in the current session. Not a page and not a
// cross-thread list: each chat session shows its own attachments.
//
// Clicking a document opens the PDF in a new tab via an authenticated blob
// fetch (the file is encrypted at rest and has no static URL). The trash
// button removes it from the server and from this session.
import { useEffect, useRef, useState } from "react";

import { ApiError, deleteDocument, fetchDocumentFile } from "../api/client";
import type { DocumentUploadResponse } from "../types";

interface SessionDocumentsMenuProps {
  documents: DocumentUploadResponse[];
  onRemoved: (documentId: string) => void;
}

const BLOB_URL_LIFETIME_MS = 60_000;

export default function SessionDocumentsMenu({ documents, onRemoved }: SessionDocumentsMenuProps) {
  const [open, setOpen] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) setOpen(false);
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  async function handleOpen(doc: DocumentUploadResponse) {
    if (busyId) return;
    setError("");
    setBusyId(doc.document_id);
    // Opened synchronously, inside the click, so the browser's popup blocker
    // treats it as user-initiated -- the blob URL is only known after the
    // fetch resolves, so it's pointed at the tab afterwards.
    const tab = window.open("about:blank", "_blank");
    try {
      const blob = await fetchDocumentFile(doc.document_id);
      const url = URL.createObjectURL(new Blob([blob], { type: "application/pdf" }));
      if (tab) tab.location.href = url;
      else window.open(url, "_blank");
      window.setTimeout(() => URL.revokeObjectURL(url), BLOB_URL_LIFETIME_MS);
    } catch (e) {
      tab?.close();
      setError(e instanceof ApiError ? e.message : "The document could not be opened.");
    } finally {
      setBusyId(null);
    }
  }

  async function handleRemove(doc: DocumentUploadResponse) {
    if (busyId) return;
    setError("");
    setBusyId(doc.document_id);
    try {
      await deleteDocument(doc.document_id);
      onRemoved(doc.document_id);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The document could not be removed.");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div ref={containerRef} className="fixed right-16 top-4 z-50">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        title="Documents in this session"
        aria-label="Documents in this session"
        aria-expanded={open}
        className="relative flex h-9 w-9 items-center justify-center rounded-xl border border-slate-200 bg-white text-slate-500 shadow-sm transition hover:bg-slate-50 hover:text-slate-700 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-400 dark:hover:bg-slate-700 dark:hover:text-slate-200"
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V7z" />
        </svg>
        {documents.length > 0 && (
          <span className="absolute -right-1 -top-1 flex h-4 min-w-[16px] items-center justify-center rounded-full bg-violet-600 px-1 text-[10px] font-semibold text-white">
            {documents.length}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-11 w-72 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-xl dark:border-slate-700 dark:bg-slate-800">
          <div className="flex items-center justify-between border-b border-slate-200 px-4 py-2.5 dark:border-slate-700">
            <span className="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-400 dark:text-slate-500">
              This session
            </span>
            <span className="text-[11px] text-slate-400 dark:text-slate-500">
              {documents.length} {documents.length === 1 ? "document" : "documents"}
            </span>
          </div>

          {documents.length === 0 ? (
            <div className="px-4 py-8 text-center">
              <svg className="mx-auto mb-2 text-slate-300 dark:text-slate-600" width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V7z" />
              </svg>
              <p className="text-sm font-medium text-slate-800 dark:text-slate-200">No documents in this session</p>
              <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">Use + in the message box to attach a PDF.</p>
            </div>
          ) : (
            <ul>
              {documents.map((doc) => (
                <li key={doc.document_id} className="flex items-center gap-1 pr-2 hover:bg-slate-50 dark:hover:bg-slate-700/50">
                  <button
                    type="button"
                    onClick={() => void handleOpen(doc)}
                    disabled={busyId !== null}
                    title="Open PDF in a new tab"
                    className="flex min-w-0 flex-1 items-center gap-2.5 px-4 py-3 text-left disabled:opacity-60"
                  >
                    <svg className="shrink-0 text-violet-500" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round">
                      <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8l-6-6z" />
                      <path d="M14 2v6h6" />
                    </svg>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium text-slate-900 dark:text-slate-100">{doc.title}</span>
                      <span className="block text-[11px] text-slate-400 dark:text-slate-500">{doc.n_pages} {doc.n_pages === 1 ? "page" : "pages"}</span>
                    </span>
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleRemove(doc)}
                    disabled={busyId !== null}
                    title="Remove from this session"
                    aria-label={`Remove ${doc.title}`}
                    className="shrink-0 rounded-md p-1.5 text-slate-300 transition hover:bg-red-50 hover:text-red-500 disabled:opacity-60 dark:text-slate-500 dark:hover:bg-red-900/20 dark:hover:text-red-400"
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M3 6h18M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2m3 0-1 14a2 2 0 01-2 2H7a2 2 0 01-2-2L4 6h16z" />
                    </svg>
                  </button>
                </li>
              ))}
            </ul>
          )}

          {error && (
            <p role="alert" className="border-t border-slate-200 px-4 py-2 text-xs text-red-600 dark:border-slate-700 dark:text-red-400">
              {error}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
