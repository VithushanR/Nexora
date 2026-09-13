# STUB -- replace with Part D's real implementation. Interface must not change.
"""
Placeholder per-thread report lookup for backend/routers/copilot.py.

Nothing in this codebase yet persists a finished `report` object keyed by
thread_id (the pipeline in backend/graph/build_graph.py doesn't have a
human_selection/report_assembly path wired up end-to-end, and there's no
DB). This stub keeps Part B runnable and testable in isolation:
get_report() returns whatever was registered via register_report() for
that thread_id, falling back to a hardcoded sample report matching the
Part B contract shape so local testing works without the full pipeline.

Replace with a real lookup (DB row / checkpointer state keyed by
thread_id) once the pipeline persists reports -- keep the get_report(thread_id)
-> dict signature stable.
"""

# The exact report shape Part B (Report Copilot) is contracted to receive.
# See the Part B build prompt for the authoritative schema.
SAMPLE_REPORT: dict = {
    "domain": "sample domain",
    "evidence_table": [
        {
            "title": "Sample Paper One",
            "doi": "10.1000/sample1",
            "year": 2023,
            "source": "arxiv",
            "full_text_available": True,
            "full_text_strategy": "arxiv",
            "summary_source": "full_text",
            "methodology_summary": "A CNN trained on a public benchmark dataset.",
            "results_summary": "Reports 95% accuracy, outperforming the prior baseline.",
            "retracted": False,
            "retraction_note": "",
            "related_gap_indices": [0],
        },
        {
            "title": "Sample Paper Two",
            "doi": "10.1000/sample2",
            "year": 2022,
            "source": "europepmc",
            "full_text_available": False,
            "full_text_strategy": "none",
            "summary_source": "abstract_fallback",
            "methodology_summary": "A randomized controlled trial with 200 participants.",
            "results_summary": "Found no statistically significant effect.",
            "retracted": False,
            "retraction_note": "",
            "related_gap_indices": [],
        },
    ],
    "contradictions": [
        {
            "description": "Paper One reports a strong positive effect while Paper Two finds none.",
            "paper_a_title": "Sample Paper One",
            "paper_a_claim": "The method improves accuracy by 15 points.",
            "paper_b_title": "Sample Paper Two",
            "paper_b_claim": "No statistically significant improvement was observed.",
        }
    ],
    "contradictions_status": {"code": "ok", "message": "1 contradiction found.", "is_error": False},
    "gaps": [
        {
            "theme": "Long-term follow-up is rarely studied.",
            "support_count": 2,
            "supporting_paper_titles": ["Sample Paper One", "Sample Paper Two"],
        }
    ],
    "gaps_status": {"code": "ok", "message": "1 gap found.", "n_statements": 4, "is_error": False},
    "meta": {
        "n_papers": 2, "n_full_text": 1, "n_abstract_fallback": 1,
        "n_contradictions": 1, "n_gaps": 1,
        "strategy_counts": {"arxiv": 1, "none": 1},
        "analysis_incomplete": False,
    },
}

_REPORTS: dict[str, dict] = {}


def register_report(thread_id: str, report: dict) -> None:
    """Test/dev helper until the pipeline persists real per-thread reports."""
    _REPORTS[thread_id] = report


def get_report(thread_id: str) -> dict:
    """Returns the report for `thread_id`, or a hardcoded sample report if
    none was registered (local dev / no pipeline wiring yet)."""
    return _REPORTS.get(thread_id) or SAMPLE_REPORT
