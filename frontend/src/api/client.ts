// Typed fetch wrapper for the FastAPI backend, per nexora_final_split.md
// §A.1 (research pipeline) and §B.1 (copilot).

import type {
  Candidate,
  CopilotChatResponse,
  CopilotHistoryItem,
  DocumentChatResponse,
  DocumentHistoryItem,
  DocumentUploadResponse,
  ReportResponse,
  RunStatus,
} from "../types";

const BASE_URL = import.meta.env.VITE_API_BASE_URL as string;
const TOKEN_KEY = "nexora_api_token";

export function getAuthToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setAuthToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearAuthToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getAuthToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string> | undefined),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${BASE_URL}${path}`, { ...options, headers });

  if (!res.ok) {
    let message = res.statusText || `Request failed (${res.status})`;
    try {
      const body = await res.json();
      message = body?.detail ?? message;
    } catch {
      // response wasn't JSON -- keep the default message
    }
    throw new ApiError(res.status, message);
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

// ---- Part A: research pipeline ----

export function startResearch(domain: string) {
  return request<{ thread_id: string }>("/research", {
    method: "POST",
    body: JSON.stringify({ domain }),
  });
}

export function getStatus(threadId: string) {
  return request<RunStatus>(`/research/${threadId}/status`);
}

export function getCandidates(threadId: string) {
  return request<{ eligible_candidates: Candidate[] }>(
    `/research/${threadId}/candidates`
  );
}

export function submitSelection(threadId: string, selectedIndices: number[]) {
  return request<{ status: string }>(`/research/${threadId}/select`, {
    method: "POST",
    body: JSON.stringify({ selected_indices: selectedIndices }),
  });
}

export function getReport(threadId: string) {
  return request<ReportResponse>(`/research/${threadId}/report`);
}

// ---- Part B: copilot ----

export function indexCopilot(threadId: string) {
  return request<{ indexed: boolean; n_chunks: number }>(
    `/research/${threadId}/copilot/index`,
    { method: "POST" }
  );
}

export function sendCopilotMessage(
  threadId: string,
  message: string,
  mode: "report" | "auto"
) {
  return request<CopilotChatResponse>(`/research/${threadId}/copilot/chat`, {
    method: "POST",
    body: JSON.stringify({ message, mode }),
  });
}

export function addToEvidence(threadId: string, messageId: string) {
  return request<{ added: boolean }>(
    `/research/${threadId}/copilot/add_to_evidence`,
    { method: "POST", body: JSON.stringify({ message_id: messageId }) }
  );
}

export function getCopilotHistory(threadId: string) {
  return request<CopilotHistoryItem[]>(`/research/${threadId}/copilot/history`);
}

// ---- Part D: document upload & chat ----

export async function uploadDocument(file: File): Promise<DocumentUploadResponse> {
  const token = getAuthToken();
  const formData = new FormData();
  formData.append("file", file);

  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${BASE_URL}/documents/upload`, {
    method: "POST",
    headers,
    body: formData,
  });

  if (!res.ok) {
    let message = res.statusText || `Upload failed (${res.status})`;
    try {
      const body = await res.json();
      message = body?.detail ?? message;
    } catch {
      // response wasn't JSON
    }
    throw new ApiError(res.status, message);
  }

  return (await res.json()) as DocumentUploadResponse;
}

export function sendDocumentChat(documentId: string, message: string) {
  return request<DocumentChatResponse>(`/documents/${documentId}/chat`, {
    method: "POST",
    body: JSON.stringify({ message }),
  });
}

export function getDocumentChatHistory(documentId: string) {
  return request<DocumentHistoryItem[]>(`/documents/${documentId}/chat/history`);
}
