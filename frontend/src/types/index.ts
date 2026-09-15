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
  prerank_score: number | null;
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
