-- One finished research report per thread. `report` is the structured object
-- built by report_assembly.build_structured_report (evidence_table,
-- contradictions, gaps, introduction, ...), stored unchanged.
CREATE TABLE IF NOT EXISTS reports (
    thread_id TEXT PRIMARY KEY
        REFERENCES research_threads (thread_id) ON DELETE CASCADE,
    report JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);
