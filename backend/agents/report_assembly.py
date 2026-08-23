"""
Report assembly (fan-in node).

Merges Agent 3 (evidence_table, contradictions) + Agent 4 (gaps) into one
markdown report, then chunks and indexes it for the Copilot chat.
Makes no LLM calls -- pure data merging and embedding.
"""

from backend.graph.state import ResearchState
from backend.agents.gap_discovery import embed

# ============================================================
# MERGE
# ============================================================


def merge_report(state: dict) -> str:
    """Combine Agent 3 and Agent 4 output into one markdown report.

    None means the agent crashed. An empty list means it ran and found
    nothing. These are different, and the report says which.
    """
    evidence_table = state.get("evidence_table")
    contradictions = state.get("contradictions")
    gaps = state.get("gaps")

    missing = []
    if evidence_table is None:
        missing.append("Evidence Table")
    if contradictions is None:
        missing.append("Conflicts")
    if gaps is None:
        missing.append("Research Gaps")

    domain = state.get("domain", "Untitled search")
    selected = state.get("selected_papers") or []

    parts = [
        f"# {domain} — Report\n",
        f"{len(selected)} papers analysed.\n",
    ]

    if missing:
        parts.append(
            "> **Warning:** these sections could not be generated: "
            + ", ".join(missing)
            + ".\n"
        )

    parts.append(render_evidence_table(evidence_table or []))
    parts.append(render_contradictions(contradictions or []))
    parts.append(render_gaps(gaps or []))

    return "\n".join(parts)


def render_evidence_table(rows):
    """Render Agent 3's evidence table as markdown."""
    if not rows:
        return "## Evidence Table\n\nNo evidence rows available.\n"

    lines = ["## Evidence Table\n"]
    lines.append("| Paper | Method | Key finding |")
    lines.append("| --- | --- | --- |")

    for row in rows:
        title = row.get("title", "—")
        method = row.get("method", "—")
        finding = row.get("finding", "—")
        lines.append(f"| {title} | {method} | {finding} |")

    lines.append("")
    return "\n".join(lines)


def render_contradictions(items):
    """Render Agent 3's contradiction report as markdown."""
    if not items:
        return "## Conflicts\n\nNo contradictions detected.\n"

    lines = ["## Conflicts\n"]
    for item in items:
        lines.append(f"- {item.get('summary', '—')}")
    lines.append("")
    return "\n".join(lines)


def render_gaps(gaps):
    """Render the Research Gaps section as markdown."""
    if not gaps:
        return "## Research Gaps\n\nNo recurring gaps met the support threshold.\n"

    lines = ["## Research Gaps\n"]
    for gap in gaps:
        lines.append(f"### {gap['statement']}\n")
        lines.append(
            f"Supported by {gap['support_count']} of "
            f"{gap['total_papers']} papers.\n"
        )
        for quote in gap["quotes"]:
            lines.append(f"- *{quote['paper_id']}*: \"{quote['text']}\"")
        lines.append("")

    return "\n".join(lines)


# ============================================================
# CHUNKING & INDEXING (for Copilot "Report mode" retrieval)
# ============================================================


def chunk_report(state: dict) -> list[dict]:
    """One chunk per evidence row, per contradiction, per gap."""
    chunks = []

    for i, row in enumerate(state.get("evidence_table") or []):
        text = " ".join(
            str(row.get(k, "")) for k in ("title", "method", "finding")
        ).strip()
        if text:
            chunks.append({"id": f"evidence:{i}", "section": "evidence", "text": text})

    for i, item in enumerate(state.get("contradictions") or []):
        text = str(item.get("summary", "")).strip()
        if text:
            chunks.append(
                {"id": f"conflict:{i}", "section": "conflicts", "text": text}
            )

    for gap in state.get("gaps") or []:
        quotes = " ".join(q["text"] for q in gap.get("quotes", []))
        text = f"{gap['statement']} {quotes}".strip()
        if text:
            chunks.append(
                {"id": gap["gap_id"], "section": "gaps", "text": text}
            )

    return chunks


def build_index(chunks):
    """Embed each chunk once and build a FAISS index. Reuses embed(), no LLM."""
    import numpy as np
    import faiss

    if not chunks:
        return None

    vectors = np.asarray(embed([c["text"] for c in chunks]), dtype="float32")
    index = faiss.IndexFlatIP(vectors.shape[1])
    index.add(vectors)
    return index


# ============================================================
# NODE (the entry point)
# ============================================================

_index = None
_chunks: list[dict] = []


def get_index():
    """Handed to the Copilot chat route for Report-mode lookups."""
    return _index, _chunks


async def report_assembly_node(state: ResearchState) -> dict:
    """LangGraph fan-in node. Reads Agent 3 + Agent 4 output, writes report.

    Runs after both synthesis_integrity and gap_discovery finish. No LLM.
    """
    global _index, _chunks

    report_md = merge_report(state)

    _chunks = chunk_report(state)
    _index = build_index(_chunks)

    return {"report": report_md}


# ============================================================
# OPTIONAL: PDF EXPORT (bonus, not wired into build_graph.py)
# ============================================================
# A router could call this to let the user download a PDF:
#     GET /report/pdf  ->  render_pdf(state["report"])
# Needs: pip install reportlab   (and add reportlab to requirements.txt)


def render_pdf(report_markdown: str, filename: str = "nexora_report.pdf") -> str:
    """Render the markdown report as a simple PDF. Returns the file path."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    import html

    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontSize=16, spaceAfter=10)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=13, spaceAfter=6)
    body = ParagraphStyle("body", parent=styles["Normal"], fontSize=10, leading=14)

    doc = SimpleDocTemplate(
        filename,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
    )

    story = []
    for line in report_markdown.split("\n"):
        text = html.escape(line.strip())
        if not text:
            story.append(Spacer(1, 6))
        elif line.startswith("# "):
            story.append(Paragraph(text[2:], h1))
        elif line.startswith("## "):
            story.append(Paragraph(text[3:], h2))
        elif line.startswith("### "):
            story.append(Paragraph(f"<b>{text[4:]}</b>", body))
        else:
            story.append(Paragraph(text, body))

    doc.build(story)
    return filename
