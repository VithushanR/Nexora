"""
Report assembly (fan-in node).

Merges Agent 3 (evidence_table, contradictions) + Agent 4 (gaps) into one
markdown report (for GET /research/{thread_id}/report), and registers the
same data as a structured dict for the Report Copilot to index (for
POST /research/{thread_id}/copilot/index) via backend/report/store.py.
Makes no LLM calls -- pure data merging.
"""

from langgraph.config import get_config

from backend.graph.state import ResearchState
from backend.report.store import register_report

# ============================================================
# MERGE (-> Markdown, for GET /research/{thread_id}/report)
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
# STRUCTURED REPORT (-> dict, for POST /research/{thread_id}/copilot/index)
# ============================================================
#
# backend/routers/copilot.py's own chunk_report() reads evidence_table rows
# and contradictions by their real field names directly -- both already
# match what synthesis_integrity.py produces verbatim (title/doi/year/
# source/full_text_available/full_text_strategy/summary_source/
# methodology_summary/results_summary/retracted/retraction_note for rows;
# description/paper_a_title/paper_a_claim/paper_b_title/paper_b_claim for
# contradictions), so those pass straight through unchanged.
#
# gaps is the one place the shapes genuinely differ: gap_discovery.py's
# real output uses "statement" and "supporting_paper_ids" (which, per its
# own docstring, hold paper TITLES -- Candidate has no separate id field),
# where copilot.py's chunker expects "theme" and "supporting_paper_titles".
# Same data, different names -- rename here rather than in either agent.


def _map_gap_for_copilot(gap: dict) -> dict:
    return {
        "theme": gap.get("statement", ""),
        "support_count": gap.get("support_count", 0),
        "supporting_paper_titles": gap.get("supporting_paper_ids") or [],
    }


def build_structured_report(state: dict) -> dict:
    """Builds the dict backend/report/store.py registers for Copilot
    indexing, from the same state merge_report() renders to Markdown."""
    return {
        "domain": state.get("domain", ""),
        "evidence_table": state.get("evidence_table") or [],
        "contradictions": state.get("contradictions") or [],
        "contradictions_status": state.get("contradictions_status") or {},
        "gaps": [_map_gap_for_copilot(g) for g in (state.get("gaps") or [])],
        "gaps_status": state.get("gaps_status") or {},
    }


# ============================================================
# NODE (the entry point)
# ============================================================


async def report_assembly_node(state: ResearchState) -> dict:
    """LangGraph fan-in node. Reads Agent 3 + Agent 4 output, writes report.

    Runs after both synthesis_integrity and gap_discovery finish. No LLM.

    Also registers the same evidence_table/contradictions/gaps as a
    structured report (see build_structured_report()) so the Report
    Copilot's /index endpoint can index this thread's real output instead
    of falling back to the placeholder sample report. get_config() reads
    the thread_id LangGraph is running this node under -- ResearchState
    itself carries no thread_id field, this is the one place a running
    node can recover it.
    """
    thread_id = (get_config().get("configurable") or {}).get("thread_id")
    if not thread_id:
        raise RuntimeError(
            "report_assembly_node requires a thread_id in the run config "
            "(config={'configurable': {'thread_id': ...}}) to register the "
            "report for Copilot indexing -- see backend/routers/research.py's "
            "THREAD_CONFIG for how every real run supplies this."
        )
    register_report(thread_id, build_structured_report(state))

    return {"report": merge_report(state)}


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
