// Shared types for the current backend /research API contract.

export type ResearchStatus =
  | "running_agent2"
  | "paused_for_selection"
  | "running_synthesis"
  | "done"
  | "error";

export interface ResearchStartRequest {
  domain: string;
}

export interface ResearchStartResponse {
  thread_id: string;
}

export interface ResearchStatusResponse {
  status: ResearchStatus;
  detail: string;
}

export type ResearchSource =
  | "openalex"
  | "semantic_scholar"
  | "arxiv"
  | "europepmc";

export type ScreeningVerdict = "INCLUDE" | "EXCLUDE" | "UNCERTAIN";

export interface CandidatePaper {
  title: string | null;
  doi: string | null;
  abstract: string | null;
  year: number | null;
  source: ResearchSource | null;
  verdict: ScreeningVerdict | null;
  quote: string | null;
  reason: string | null;
  paper_url: string | null;
  prerank_score: number | null;
  // Relative to THIS search's own results only -- see backend's
  // apply_relevance_percent(). Never comparable across two different searches.
  relevance_percent: number | null;
  has_usable_abstract: boolean | null;
}

export interface CandidatesResponse {
  eligible_candidates: CandidatePaper[];
}

export interface SelectionRequest {
  selected_indices: number[];
}

export interface SelectionResponse {
  status: "running_synthesis";
}

export interface ReportResponse {
  report: string;
}

// ---------------------------------------------------------------------------
// Structured report pieces (Agent 3 / Agent 4 output).
//
// NOTE: no current backend endpoint actually returns these as JSON --
// GET /research/{thread_id}/report (ReportResponse above) returns the
// assembled report as a single Markdown string. These types exist so
// EvidenceTable.tsx / ContradictionCard.tsx / GapCard.tsx compile against
// the shape they were written for (and that backend/routers/copilot.py's
// chunk_report() reads from internally); wiring them to a real structured
// endpoint is a separate follow-up, not something this fix touches.
// ---------------------------------------------------------------------------

export interface EvidenceRow {
  title: string;
  source: ResearchSource | string;
  year: number | null;
  retracted: boolean | null;
  methodology_summary: string;
  results_summary: string;
  full_text_available: boolean;
  full_text_strategy: string;
}

export interface Contradiction {
  description: string;
  paper_a_title: string;
  paper_a_claim: string;
  paper_b_title: string;
  paper_b_claim: string;
}

export interface Gap {
  theme: string;
  support_count: number;
  supporting_paper_titles: string[];
}

// ---------------------------------------------------------------------------
// Report indexing (backend/routers/copilot.py) -- chatting over an indexed
// report goes through the merged chat router below, not a copilot endpoint.
// ---------------------------------------------------------------------------

export interface CopilotIndexResponse {
  indexed: boolean;
  n_chunks: number;
}

// ---------------------------------------------------------------------------
// Merged chat (backend/routers/chat.py) -- matches ChatRequest/ChatResponse/
// ChatSource exactly. "mode" here is only chat vs web; report/document
// grounding is automatic from what the request carries.
// ---------------------------------------------------------------------------

export type ChatRequestMode = "chat" | "web";
export type ChatAnswerMode = "general" | "grounded" | "web";

export interface ChatSource {
  kind: "report" | "document" | "web";
  label: string;
  id: string | null;
  url: string | null;
}

export interface ChatResponse {
  message_id: string;
  reply: string;
  mode: ChatAnswerMode;
  sources: ChatSource[];
}

export interface ChatHistoryMessage {
  message_id: string;
  role: "user" | "assistant";
  content: string;
  mode: ChatAnswerMode | null;
  sources: ChatSource[];
  created_at: string;
}

// ---------------------------------------------------------------------------
// Document upload (backend/routers/documents.py).
// ---------------------------------------------------------------------------

export interface DocumentUploadResponse {
  document_id: string;
  title: string;
  n_pages: number;
  /** Present on documents listed from the server (not on a fresh upload response). */
  created_at?: string;
}
