"""PDF rendering checks for the downloadable Nexora research report."""

from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pypdf import PdfReader

from backend.agents.report_assembly import render_pdf
from backend.auth.jwt import get_current_user
from backend.routers import research


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
    assert float(reader.pages[0].mediabox.width) < float(reader.pages[0].mediabox.height)

    page_text = [page.extract_text() or "" for page in reader.pages]
    combined_text = "\n".join(page_text)
    assert all("Nexora Research" in text for text in page_text)
    evidence_pages = [text for text in page_text if "Evidence paper" in text]
    assert len(evidence_pages) >= 2
    assert all("Paper" in text and "Key finding" in text for text in evidence_pages)
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


# ---------------------------------------------------------------------------
# Tier gate on GET /research/{thread_id}/report/pdf
# ---------------------------------------------------------------------------

# Fake tier limits, so these tests don't depend on the final values in
# backend/tiers.py.
PDF_DISABLED = SimpleNamespace(pdf_export_enabled=False)
PDF_ENABLED = SimpleNamespace(pdf_export_enabled=True)
# A tier object with no pdf_export_enabled at all -- the real TierLimits
# always has this field now, and the endpoint reads it directly (no getattr
# fallback), so this simulates a malformed/incomplete tier object rather
# than "today's behaviour."
NO_PDF_FIELD = SimpleNamespace()


@pytest.fixture
def pdf_endpoint(monkeypatch):
    """The research router with auth, tier lookup and report loading faked,
    so no JWT, users table or LangGraph checkpoint is needed."""
    env = SimpleNamespace(
        tier_lookup=AsyncMock(return_value="free"),
        load_report=AsyncMock(return_value=research.ReportResponse(report="# Report\n\nSome findings.")),
    )
    monkeypatch.setattr(research, "get_user_tier", env.tier_lookup)
    monkeypatch.setattr(research, "research_report", env.load_report)

    def use_limits(limits):
        monkeypatch.setattr(research, "get_tier_config", lambda tier: limits)

    env.use_limits = use_limits

    app = FastAPI()
    app.include_router(research.router)
    app.dependency_overrides[get_current_user] = lambda: "user_alice"
    env.client = TestClient(app)
    return env


def test_pdf_export_disabled_tier_gets_upgrade_error(pdf_endpoint):
    pdf_endpoint.use_limits(PDF_DISABLED)

    response = pdf_endpoint.client.get("/research/thread-1/report/pdf")

    assert response.status_code == 403
    detail = response.json()["detail"]
    assert detail["code"] == "tier_limit"
    assert detail["limit"] == "pdf_export_enabled"
    assert "upgrade" in detail["message"].lower()
    assert "Markdown report is still available" in detail["message"]


def test_pdf_export_disabled_tier_never_loads_or_renders_the_report(pdf_endpoint, monkeypatch):
    pdf_endpoint.use_limits(PDF_DISABLED)
    renderer = Mock()
    monkeypatch.setattr("backend.agents.report_assembly.render_pdf", renderer)

    pdf_endpoint.client.get("/research/thread-1/report/pdf")

    pdf_endpoint.load_report.assert_not_awaited()
    renderer.assert_not_called()


def test_pdf_export_enabled_tier_gets_the_pdf(pdf_endpoint):
    pdf_endpoint.use_limits(PDF_ENABLED)

    response = pdf_endpoint.client.get("/research/thread-1/report/pdf")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "thread-1" in response.headers["content-disposition"]
    assert response.content.startswith(b"%PDF")
    pdf_endpoint.load_report.assert_awaited_once_with("thread-1", "user_alice")


def test_tier_missing_the_pdf_field_entirely_fails_loudly_not_silently_allowed(pdf_endpoint):
    """pdf_export_enabled is read via direct attribute access, not
    getattr(..., True) -- a tier object that doesn't define it (a bug
    elsewhere, not a real account tier) must surface as a clear error
    rather than silently granting PDF export to everyone, which is exactly
    what the old getattr default did before backend/tiers.py defined this
    field for real."""
    pdf_endpoint.use_limits(NO_PDF_FIELD)

    with pytest.raises(AttributeError, match="pdf_export_enabled"):
        pdf_endpoint.client.get("/research/thread-1/report/pdf")


def test_pdf_gate_uses_the_requesting_users_tier(pdf_endpoint):
    pdf_endpoint.use_limits(PDF_ENABLED)

    pdf_endpoint.client.get("/research/thread-1/report/pdf")

    pdf_endpoint.tier_lookup.assert_awaited_once_with("user_alice")
