"""
Per-thread report lookup for backend/routers/copilot.py.

register_report() is called for real by backend/agents/report_assembly.py's
report_assembly_node, right after it assembles evidence_table/contradictions/
gaps for a completed research thread -- see that module for the exact field
mapping (most fields pass through unchanged; gaps get a small rename since
gap_discovery.py's real shape uses statement/supporting_paper_ids where this
contract expects theme/supporting_paper_titles).

get_report() falls back to SAMPLE_REPORT only for a thread_id nothing has
registered yet -- in practice, a thread that hasn't reached report_assembly
(still running, or copilot/index called before completion), or local
testing without running the full pipeline.

This store is still in-memory only (module-level dict, not a DB table) --
lost on process restart, not shared across worker processes. That part
remains a real gap if this ever needs to survive across processes; the
get_report(thread_id) -> dict signature should stay stable regardless.
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
