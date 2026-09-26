// Typed fetch wrapper for the FastAPI backend. Part D can later inject
// authentication headers through setAuthHeadersProvider without changing page code.

import type {
  CandidatesResponse,
  ChatHistoryMessage,
  ChatRequestMode,
  ChatResponse,
  CopilotIndexResponse,
  DocumentUploadResponse,
  ResearchStartRequest,
  ResearchStartResponse,
  ResearchStatusResponse,
  ReportResponse,
  SelectionRequest,
  SelectionResponse,
} from "../types";

export type AuthHeadersProvider = () => Promise<Record<string, string>>;

let authHeadersProvider: AuthHeadersProvider | undefined;

// Common base so callers that don't care about the specific failure mode
// (upload widgets, chat panels) can do a single `e instanceof ApiError`
// check, while call sites that DO care about status-code specifics
// (SelectionPage, ReportPage) keep narrowing to ApiClientError etc.
export class ApiError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ApiError";
  }
}

export class ApiClientError extends ApiError {
  constructor(
    public readonly status: number,
    message: string,
    public readonly code?: string,
  ) {
    super(message);
    this.name = "ApiClientError";
  }
}

export class ApiConfigurationError extends ApiError {
  constructor(message: string) {
    super(message);
    this.name = "ApiConfigurationError";
  }
}

export class ApiNetworkError extends ApiError {
  constructor(message: string) {
    super(message);
    this.name = "ApiNetworkError";
  }
}

export function setAuthHeadersProvider(provider?: AuthHeadersProvider): void {
  authHeadersProvider = provider;
}

// ---------------------------------------------------------------------------
// Auth token storage. Google Sign-In (src/auth/AuthContext.tsx) posts the
// Google ID token to POST /auth/google and stores the app JWT it returns
// using these functions.
// ---------------------------------------------------------------------------

const AUTH_TOKEN_STORAGE_KEY = "nexora_auth_token";

export function getAuthToken(): string | null {
  try {
    return localStorage.getItem(AUTH_TOKEN_STORAGE_KEY);
  } catch {
    return null;
  }
}

export function setAuthToken(token: string): void {
  try {
    localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, token);
  } catch {
    // localStorage unavailable (private browsing, disabled storage, etc.)
    // -- the token just won't persist across reloads.
  }
}

export function clearAuthToken(): void {
  try {
    localStorage.removeItem(AUTH_TOKEN_STORAGE_KEY);
  } catch {
    // ignore
  }
}

// ---------------------------------------------------------------------------
// Signed-in user display info. POST /auth/google only returns the app JWT
// (no name/email/picture -- see backend/routers/auth.py's GoogleLoginResponse),
// so AuthContext decodes those fields from the Google ID token payload at
// sign-in time and stores them here for display (avatar initial, name, etc.).
// ---------------------------------------------------------------------------

export interface AuthUser {
  name: string | null;
  email: string | null;
  picture: string | null;
}

const AUTH_USER_STORAGE_KEY = "nexora_auth_user";

export function getAuthUser(): AuthUser | null {
  try {
    const raw = localStorage.getItem(AUTH_USER_STORAGE_KEY);
    return raw ? (JSON.parse(raw) as AuthUser) : null;
  } catch {
    return null;
  }
}

export function setAuthUser(user: AuthUser): void {
  try {
    localStorage.setItem(AUTH_USER_STORAGE_KEY, JSON.stringify(user));
  } catch {
    // ignore -- same non-fatal storage failure as setAuthToken()
  }
}

export function clearAuthUser(): void {
  try {
    localStorage.removeItem(AUTH_USER_STORAGE_KEY);
  } catch {
    // ignore
  }
}

// Attach the stored token to every outgoing request as a Bearer token.
// setAuthHeadersProvider() only ever registers a hook -- without actually
// calling it here, a token saved via setAuthToken() would never reach the
// backend on any request.
setAuthHeadersProvider(async () => {
  const token = getAuthToken();
  const headers: Record<string, string> = {};
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  return headers;
});

function getBaseUrl(): string {
  const configuredUrl = import.meta.env.VITE_API_BASE_URL?.trim();
  if (!configuredUrl) {
    throw new ApiConfigurationError(
      "The frontend is missing its backend API URL configuration.",
    );
  }
  return configuredUrl.replace(/\/$/, "");
}

async function parseJson(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return undefined;
  }
}

interface ResponseErrorDetail {
  message: string;
  code?: string;
}

function responseDetail(payload: unknown, fallback: string): ResponseErrorDetail {
  if (typeof payload === "object" && payload !== null && "detail" in payload) {
    if (typeof payload.detail === "string") {
      return { message: payload.detail };
    }
    if (typeof payload.detail === "object" && payload.detail !== null) {
      const message =
        "message" in payload.detail && typeof payload.detail.message === "string"
          ? payload.detail.message
          : fallback;
      const code =
        "code" in payload.detail && typeof payload.detail.code === "string"
          ? payload.detail.code
          : undefined;
      return { message, code };
    }
  }
  return { message: fallback };
}

async function requestJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const authHeaders = authHeadersProvider ? await authHeadersProvider() : {};
  const url = `${getBaseUrl()}${path}`;
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  for (const [name, value] of Object.entries(authHeaders)) {
    headers.set(name, value);
  }

  let response: Response;

  try {
    response = await fetch(url, {
      ...init,
      headers,
    });
  } catch {
    throw new ApiNetworkError("Unable to connect to the research service.");
  }

  const payload = await parseJson(response);
  if (!response.ok) {
    const detail = responseDetail(
      payload,
      "The research service could not complete the request.",
    );
    throw new ApiClientError(
      response.status,
      detail.message,
      detail.code,
    );
  }
  return payload as T;
}

// ---------------------------------------------------------------------------
// Google Sign-In (backend/routers/auth.py). Request/response shape matches
// that router's GoogleLoginRequest/GoogleLoginResponse exactly.
// ---------------------------------------------------------------------------

export interface GoogleLoginResponse {
  access_token: string;
  token_type: string;
}

export async function loginWithGoogle(idToken: string): Promise<GoogleLoginResponse> {
  return requestJson<GoogleLoginResponse>("/auth/google", {
    method: "POST",
    body: JSON.stringify({ id_token: idToken }),
  });
}

export async function startResearch(
  request: ResearchStartRequest,
): Promise<ResearchStartResponse> {
  const response = await requestJson<ResearchStartResponse>("/research", {
    method: "POST",
    body: JSON.stringify({ domain: request.domain }),
  });

  if (typeof response?.thread_id !== "string" || !response.thread_id) {
    throw new ApiClientError(201, "The research service returned an invalid response.");
  }
  return response;
}

function researchPath(threadId: string, suffix = ""): string {
  return `/research/${encodeURIComponent(threadId)}${suffix}`;
}

export async function getResearchStatus(
  threadId: string,
): Promise<ResearchStatusResponse> {
  return requestJson<ResearchStatusResponse>(
    researchPath(threadId, "/status"),
  );
}

export async function getCandidates(threadId: string): Promise<CandidatesResponse> {
  return requestJson<CandidatesResponse>(
    researchPath(threadId, "/candidates"),
  );
}

export async function submitSelection(
  threadId: string,
  request: SelectionRequest,
): Promise<SelectionResponse> {
  return requestJson<SelectionResponse>(researchPath(threadId, "/select"), {
    method: "POST",
    body: JSON.stringify({ selected_indices: request.selected_indices }),
  });
}

export async function getResearchReport(threadId: string): Promise<ReportResponse> {
  const response = await requestJson<ReportResponse>(
    researchPath(threadId, "/report"),
  );

  if (typeof response?.report !== "string") {
    throw new ApiClientError(200, "The research service returned an invalid report.");
  }
  return response;
}

// GET /report/pdf returns a binary PDF, not JSON -- requestJson() always
// parses the body as JSON, so this needs its own fetch (same auth-header
// attachment as everywhere else, via authHeadersProvider).
export async function downloadResearchReportPdf(threadId: string): Promise<Blob> {
  const authHeaders = authHeadersProvider ? await authHeadersProvider() : {};
  const headers = new Headers();
  for (const [name, value] of Object.entries(authHeaders)) {
    headers.set(name, value);
  }

  let response: Response;
  try {
    response = await fetch(`${getBaseUrl()}${researchPath(threadId, "/report/pdf")}`, { headers });
  } catch {
    throw new ApiNetworkError("Unable to connect to the research service.");
  }

  if (!response.ok) {
    const payload = await parseJson(response);
    const detail = responseDetail(payload, "The report PDF could not be downloaded.");
    throw new ApiClientError(response.status, detail.message, detail.code);
  }
  return response.blob();
}

// ---------------------------------------------------------------------------
// Report indexing (backend/routers/copilot.py). Called once a Deep Search
// report is finished so chat can ground on it.
// ---------------------------------------------------------------------------

export async function indexCopilot(threadId: string): Promise<CopilotIndexResponse> {
  return requestJson<CopilotIndexResponse>(researchPath(threadId, "/copilot/index"), {
    method: "POST",
  });
}

// ---------------------------------------------------------------------------
// The one chat endpoint (backend/routers/chat.py). The backend decides how
// to answer from the mode and what the request carries: web mode always
// searches the web; chat mode grounds on the thread's finished report and/or
// the attached documents when present, and otherwise replies conversationally.
// ---------------------------------------------------------------------------

export interface SendChatOptions {
  message: string;
  mode: ChatRequestMode;
  sessionId: string;
  threadId?: string | null;
  documentIds?: string[];
}

export async function sendChat({ message, mode, sessionId, threadId, documentIds }: SendChatOptions): Promise<ChatResponse> {
  return requestJson<ChatResponse>("/chat", {
    method: "POST",
    body: JSON.stringify({
      message,
      mode,
      session_id: sessionId,
      thread_id: threadId ?? null,
      document_ids: documentIds ?? [],
    }),
  });
}

// The stored conversation for a chat session and/or Deep Search thread, oldest
// first -- what restores the thread after a refresh or a backend restart.
export async function getChatHistory(scope: { sessionId?: string; threadId?: string | null }): Promise<ChatHistoryMessage[]> {
  const query = new URLSearchParams();
  if (scope.sessionId) query.set("session_id", scope.sessionId);
  if (scope.threadId) query.set("thread_id", scope.threadId);
  return requestJson<ChatHistoryMessage[]>(`/chat/history?${query.toString()}`);
}

// ---------------------------------------------------------------------------
// Document upload / open / delete (backend/routers/documents.py). Chatting
// about a document goes through sendChat above, not a document endpoint.
// ---------------------------------------------------------------------------

function documentPath(documentId: string, suffix = ""): string {
  return `/documents/${encodeURIComponent(documentId)}${suffix}`;
}

export interface DocumentScope {
  sessionId: string;
  threadId?: string | null;
}

export async function uploadDocument(file: File, scope: DocumentScope): Promise<DocumentUploadResponse> {
  const authHeaders = authHeadersProvider ? await authHeadersProvider() : {};
  const headers = new Headers();
  for (const [name, value] of Object.entries(authHeaders)) {
    headers.set(name, value);
  }
  // Deliberately not using requestJson(): it force-sets
  // Content-Type: application/json, which would break the multipart
  // boundary the browser needs to set itself for FormData uploads.
  const formData = new FormData();
  formData.append("file", file);
  formData.append("session_id", scope.sessionId);
  if (scope.threadId) formData.append("thread_id", scope.threadId);

  let response: Response;
  try {
    response = await fetch(`${getBaseUrl()}/documents/upload`, {
      method: "POST",
      headers,
      body: formData,
    });
  } catch {
    throw new ApiNetworkError("Unable to connect to the research service.");
  }

  const payload = await parseJson(response);
  if (!response.ok) {
    const detail = responseDetail(payload, "The document could not be uploaded.");
    throw new ApiClientError(
      response.status,
      detail.message,
      detail.code,
    );
  }
  return payload as DocumentUploadResponse;
}

// The documents uploaded in this chat session and/or Deep Search thread --
// what restores the folder panel after a refresh.
export async function listDocuments(scope: { sessionId?: string; threadId?: string | null }): Promise<DocumentUploadResponse[]> {
  const query = new URLSearchParams();
  if (scope.sessionId) query.set("session_id", scope.sessionId);
  if (scope.threadId) query.set("thread_id", scope.threadId);
  return requestJson<DocumentUploadResponse[]>(`/documents?${query.toString()}`);
}

// The PDF is encrypted at rest and has no static URL: this fetches the
// decrypted bytes with the auth header (owner-only on the server) so the
// caller can open them as a blob.
export async function fetchDocumentFile(documentId: string): Promise<Blob> {
  const authHeaders = authHeadersProvider ? await authHeadersProvider() : {};
  const headers = new Headers();
  for (const [name, value] of Object.entries(authHeaders)) {
    headers.set(name, value);
  }

  let response: Response;
  try {
    response = await fetch(`${getBaseUrl()}${documentPath(documentId, "/file")}`, { headers });
  } catch {
    throw new ApiNetworkError("Unable to connect to the research service.");
  }

  if (!response.ok) {
    const payload = await parseJson(response);
    const detail = responseDetail(payload, "The document could not be opened.");
    throw new ApiClientError(response.status, detail.message, detail.code);
  }
  return response.blob();
}

export async function deleteDocument(documentId: string): Promise<{ deleted: true }> {
  return requestJson<{ deleted: true }>(documentPath(documentId), { method: "DELETE" });
}
