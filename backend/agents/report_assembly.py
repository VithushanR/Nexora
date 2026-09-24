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


def merge_report(state: ResearchState) -> str:
    """Combine Agent 3 and Agent 4 output into one markdown report.

    None means the agent crashed. An empty list means it ran and found
    nothing. These are different, and the report says which.
    """
    evidence_table = state.get("evidence_table")
    contradictions = state.get("contradictions")
    gaps = state.get("gaps")
    paper_limitations = state.get("paper_limitations")

    missing = []
    if evidence_table is None:
        missing.append("Evidence Table")
    if contradictions is None:
        missing.append("Conflicts")
    if gaps is None:
        missing.append("Research Gaps")
    if paper_limitations is None:
        missing.append("Limitations by Individual Paper")

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
    parts.append(
        render_contradictions(contradictions or [], state.get("contradictions_status"))
    )
    parts.append(render_gaps(gaps or [], state.get("gaps_status")))
    parts.append(render_paper_limitations(paper_limitations or [], state.get("gaps_status")))

    return "\n".join(parts)


def _render_empty_section(heading, status, fallback):
    """Explain WHY a section is empty, using the status the agent recorded.

    An empty list can mean "ran and found nothing" or "could not run" (no
    full text, embedding/LLM failure). Only the agent's status knows which,
    so show its message rather than a fixed "nothing found" sentence.
    """
    if not status:
        return f"## {heading}\n\n{fallback}\n"

    message = status.get("message") or fallback
    if status.get("is_error"):
        return f"## {heading}\n\n> **Warning:** {message}\n"
    return f"## {heading}\n\n{message}\n"


def _table_cell(value):
    """Make free text safe inside a markdown table cell.

    Paper text can contain "|" (e.g. norms like \\|p\\|_1) or newlines, either
    of which would split the row and break the table.
    """
    text = " ".join(str(value).split())
    return text.replace("|", "\\|")


def _source_link_cell(paper_url) -> str:
    """A clickable markdown link when a real URL is available. Never
    fabricates one -- a paper with no known link (no OA PDF, arXiv ID, DOI,
    or PMCID) shows an honest "no link available" instead of a guessed URL."""
    if not paper_url:
        return "no link available"
    return f"[Source]({_table_cell(paper_url)})"


def render_evidence_table(rows):
    """Render Agent 3's evidence table as markdown."""
    if not rows:
        return "## Evidence Table\n\nNo evidence rows available.\n"

    lines = ["## Evidence Table\n"]
    lines.append("| Paper | Method | Key finding | Source |")
    lines.append("| --- | --- | --- | --- |")

    for row in rows:
        title = _table_cell(row.get("title", "—"))
        method = _table_cell(row.get("method", "—"))
        finding = _table_cell(row.get("finding", "—"))
        source = _source_link_cell(row.get("paper_url"))
        lines.append(f"| {title} | {method} | {finding} | {source} |")

    lines.append("")
    return "\n".join(lines)


def render_contradictions(items, status=None):
    """Render Agent 3's contradiction report as markdown."""
    if not items:
        return _render_empty_section(
            "Conflicts", status, "No contradictions detected."
        )

    lines = ["## Conflicts\n"]
    for item in items:
        lines.append(f"- {item.get('summary', '—')}")
    lines.append("")
    return "\n".join(lines)


def render_gaps(gaps, status=None):
    """Render the Research Gaps section as markdown."""
    if not gaps:
        return _render_empty_section(
            "Research Gaps", status, "No recurring gaps met the support threshold."
        )

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


def render_paper_limitations(paper_limitations, status=None):
    """Render single-paper limitations that never reached MIN_SUPPORT.

    Deliberately its own section, not folded into render_gaps(): a
    limitation one paper stated about itself is not a recurring research
    gap, and showing it under the same heading as gaps that ARE
    corroborated by multiple independent papers would blur exactly the
    distinction gap_discovery.py's MIN_SUPPORT threshold exists to draw.
    """
    if not paper_limitations:
        return _render_empty_section(
            "Limitations by Individual Paper", status,
            "No individual paper limitations could be extracted.",
        )

    lines = [
        "## Limitations by Individual Paper\n",
        "*(Not corroborated across papers)*\n",
    ]
    for item in paper_limitations:
        lines.append(f"**{item['paper_id']}**\n")
        lines.append(f"- {item['statement']}")
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


def build_structured_report(state: ResearchState) -> dict:
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
# PDF EXPORT -- wired into GET /research/{thread_id}/report/pdf
# (backend/routers/research.py). reportlab is a real dependency
# (backend/requirements.txt).
# ============================================================


def render_pdf(report_markdown: str) -> bytes:
    """Render the markdown report as a simple PDF, returned as bytes.

    Returns bytes (not a file path) deliberately: this runs inside an HTTP
    request handler, potentially concurrently for different threads/users --
    writing to a shared filename on disk would race between requests and
    leave files behind. reportlab's SimpleDocTemplate accepts a file-like
    object just as happily as a path, so an in-memory BytesIO avoids both
    problems.
    """
    import io
    import html

    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontSize=16, spaceAfter=10)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=13, spaceAfter=6)
    body = ParagraphStyle("body", parent=styles["Normal"], fontSize=10, leading=14)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
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
    return buffer.getvalue()
