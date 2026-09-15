// Shared TypeScript types mirroring backend Pydantic/state models
// (state.py ResearchState fields, router request/response models).

// TODO: define Paper (candidate/selected paper shape)
// TODO: define EvidenceRow (matches Agent 3 evidence_table entries)
// TODO: define Contradiction (matches Agent 3 contradictions entries)
// TODO: define Gap (matches Agent 4 gaps entries)
// TODO: define SearchResponse, SelectionResponse, ChatResponse (match routers/*.py)

// Shared TypeScript types mirroring the frozen API contract in
// nexora_final_split.md §A.1, §B.1, §B.3, §0.2.

export type SourceName = "openalex" | "semantic_scholar" | "arxiv" | "europepmc";
export type Verdict = "INCLUDE" | "EXCLUDE" | "UNCERTAIN";

export interface Candidate {
  title: string;
  doi: string | null;
  abstract: string;
  year: number | null;
  source: SourceName;
  verdict: Verdict;
  quote: string;
  reason: string;
  prerank_score: number;
  has_usable_abstract: boolean;
}

export type RunStatusCode =
  | "running_agent2"
  | "paused_for_selection"
  | "running_synthesis"
  | "done"
  | "error";

export interface RunStatus {
  status: RunStatusCode;
  detail: string;
}

export interface EvidenceRow {
  title: string;
  doi: string;
  year: number | null;
  source: string;
  full_text_available: boolean;
  full_text_strategy: string;
  summary_source: string;
  methodology_summary: string;
  results_summary: string;
  retracted: boolean | null;
  retraction_note: string;
  related_gap_indices: number[];
}

export interface Contradiction {
  description: string;
  paper_a_title: string;
  paper_a_claim: string;
  paper_b_title: string;
  paper_b_claim: string;
}

export interface StatusBlock {
  code: string;
  message: string;
  is_error: boolean;
}

export interface Gap {
  theme: string;
  support_count: number;
  supporting_paper_titles: string[];
}

export interface ReportMeta {
  n_papers: number;
  n_full_text: number;
  n_abstract_fallback: number;
  n_contradictions: number;
  n_gaps: number;
  strategy_counts: Record<string, number>;
  analysis_incomplete: boolean;
}

export interface ReportResponse {
  domain: string;
  evidence_table: EvidenceRow[];
  contradictions: Contradiction[];
  contradictions_status: StatusBlock;
  gaps: Gap[];
  gaps_status: StatusBlock & { n_statements?: number };
  meta: ReportMeta;
  // Echoed at the top level per §A.2.4 when meta.analysis_incomplete is true.
  analysis_incomplete?: boolean;
}

export interface CopilotSource {
  type: "evidence_row" | "web";
  paper_title?: string;
  url?: string;
  title?: string;
}

export interface CopilotChatResponse {
  message_id: string;
  answer: string;
  mode: "report" | "web";
  sources: CopilotSource[];
}

export interface CopilotHistoryItem {
  message_id: string;
  role: "user" | "assistant";
  content: string;
  mode?: "report" | "web";
  timestamp: string;
}

export interface DocumentUploadResponse {
  document_id: string;
  title: string;
  n_pages: number;
}

export interface DocumentChatSource {
  page: number;
}

export interface DocumentChatResponse {
  message_id: string;
  answer: string;
  sources: DocumentChatSource[];
}

export interface DocumentHistoryItem {
  message_id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
}
