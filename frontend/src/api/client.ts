// Typed fetch wrapper for the FastAPI backend.
// Responsibility: centralize base URL (from VITE_API_BASE_URL), request/response
// typing (using types/index.ts), and error handling for search/select/chat calls.

const BASE_URL = import.meta.env.VITE_API_BASE_URL;

// TODO: implement startSearch(domain: string): Promise<SearchResponse>
// TODO: implement submitSelection(runId: string, paperIds: string[]): Promise<SelectionResponse>
// TODO: implement sendChatMessage(runId: string, message: string, mode: "report" | "web"): Promise<ChatResponse>

export {};
