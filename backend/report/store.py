"""
Postgres-backed storage for finished research reports (the `reports` table,
backend/sql/003_create_reports.sql).

register_report() is called for real by backend/agents/report_assembly.py's
report_assembly_node, right after it assembles evidence_table/contradictions/
gaps for a completed research thread -- see that module for the exact field
mapping (most fields pass through unchanged; gaps get a small rename since
gap_discovery.py's real shape uses statement/supporting_paper_ids where the
Copilot contract expects theme/supporting_paper_titles).

get_report() returns None for a thread with no stored report (still
running, failed before report assembly, or never existed). It never
substitutes made-up data: callers must handle the "not found" case.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column, DateTime, MetaData, Table, Text, select
from sqlalchemy.dialects.postgresql import JSONB, insert

from backend.db import async_session_factory

reports_table = Table(
    "reports",
    MetaData(),
    Column("thread_id", Text, primary_key=True, nullable=False),
    Column("report", JSONB, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)


async def register_report(thread_id: str, report: dict) -> None:
    """Insert the report for `thread_id`, replacing any earlier one (a
    re-run of report assembly for the same thread overwrites it)."""
    statement = insert(reports_table).values(
        thread_id=thread_id,
        report=report,
        created_at=datetime.now(timezone.utc),
    )
    statement = statement.on_conflict_do_update(
        index_elements=[reports_table.c.thread_id],
        set_={"report": statement.excluded.report},
    )
    async with async_session_factory() as session:
        async with session.begin():
            await session.execute(statement)


async def get_report(thread_id: str) -> Optional[dict]:
    """The stored report for `thread_id`, or None if there isn't one."""
    async with async_session_factory() as session:
        return await session.scalar(
            select(reports_table.c.report).where(reports_table.c.thread_id == thread_id)
        )
