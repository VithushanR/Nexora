"""A fixed, realistic report in the exact shape Report Copilot is contracted
to receive. Tests only -- production code never falls back to fake report
data: an unregistered thread simply has no report (see backend/report/store.py).
"""

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
