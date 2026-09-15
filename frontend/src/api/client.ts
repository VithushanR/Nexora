// Typed fetch wrapper for the FastAPI backend. Part D can later inject
// authentication headers through setAuthHeadersProvider without changing page code.

import type {
  CandidatesResponse,
  ResearchStartRequest,
  ResearchStartResponse,
  ResearchStatusResponse,
  SelectionRequest,
  SelectionResponse,
} from "../types";

export type AuthHeadersProvider = () => Promise<Record<string, string>>;

let authHeadersProvider: AuthHeadersProvider | undefined;

export class ApiClientError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiClientError";
  }
}

export class ApiConfigurationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ApiConfigurationError";
  }
}

export class ApiNetworkError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ApiNetworkError";
  }
}

export function setAuthHeadersProvider(provider?: AuthHeadersProvider): void {
  authHeadersProvider = provider;
}

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

function responseDetail(payload: unknown, fallback: string): string {
  if (
    typeof payload === "object" &&
    payload !== null &&
    "detail" in payload &&
    typeof payload.detail === "string"
  ) {
    return payload.detail;
  }
  return fallback;
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
    throw new ApiClientError(
      response.status,
      responseDetail(payload, "The research service could not complete the request."),
    );
  }
  return payload as T;
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
