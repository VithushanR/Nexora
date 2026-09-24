"""PDF rendering checks for the downloadable Nexora research report."""

from io import BytesIO

from pypdf import PdfReader

from backend.agents.report_assembly import render_pdf


def test_render_pdf_uses_branded_layout_and_real_evidence_table():
    long_method = " ".join(
        [
            "The study combines a calibrated ensemble with interpretable feature attribution",
            "and evaluates it with stratified cross-validation across several customer cohorts.",
        ]
        * 4
    )
    long_finding = " ".join(
        [
            "The ensemble improves churn detection while retaining explanations that analysts can use",
            "to plan targeted and cost-aware customer retention actions.",
        ]
        * 4
    )
    rows = "\n".join(
        f"| Evidence paper {index} | {long_method} | {long_finding} | [Source](https://example.org/{index}) |"
        for index in range(1, 9)
    )
    report = f"""# Explainable Customer Churn Prediction - Report

8 papers analysed.

## Introduction

The selected studies examine accurate, interpretable, and operationally useful churn prediction.

## Evidence Table

| Paper | Method | Key finding | Source |
| --- | --- | --- | --- |
{rows}

## Conflicts

No contradictions detected.
"""

    pdf_bytes = render_pdf(report)
    reader = PdfReader(BytesIO(pdf_bytes))

    assert pdf_bytes.startswith(b"%PDF")
    assert len(reader.pages) >= 2
    assert float(reader.pages[0].mediabox.width) > float(reader.pages[0].mediabox.height)

    page_text = [page.extract_text() or "" for page in reader.pages]
    combined_text = "\n".join(page_text)
    assert all("Nexora Research" in text for text in page_text)
    assert all("Paper" in text and "Key finding" in text for text in page_text)
    assert "Introduction" in combined_text
    assert "Evidence Table" in combined_text
    assert "| ---" not in combined_text
    assert "**" not in combined_text

    annotations = [
        annotation.get_object()
        for page in reader.pages
        for annotation in (page.get("/Annots") or [])
    ]
    assert any(annotation.get("/A", {}).get("/URI") for annotation in annotations)
