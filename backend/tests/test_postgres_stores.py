"""
Integration tests for the Postgres-backed stores -- reports, documents and
chat_messages -- run against a REAL PostgreSQL, with the schema built from
the actual backend/sql/*.sql migration files (so the SQL itself is tested,
not just the Python).

Point NEXORA_TEST_PG_URL at a throwaway database, e.g.
    postgresql+psycopg://postgres@127.0.0.1:55432/postgres
Each test gets a fresh, isolated schema (dropped afterwards); nothing else in
the database is touched. Skipped when the variable is not set, so the suite
stays runnable without a Postgres.

Run with: pytest backend/tests/test_postgres_stores.py -v
"""

import os
import sqlite3
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend import chat_store, documents_store, migrate_documents_to_postgres, research_threads
from backend.report import store as report_store

PG_URL = os.environ.get("NEXORA_TEST_PG_URL", "")
SQL_DIR = Path(__file__).resolve().parents[1] / "sql"

pytestmark = pytest.mark.skipif(not PG_URL, reason="NEXORA_TEST_PG_URL is not set")

USER = "user-a"
OTHER = "user-b"


def _schema_engine(schema: str):
    return create_async_engine(PG_URL, connect_args={"options": f"-csearch_path={schema}"})


def _patch_factory(monkeypatch, factory):
    for module in (report_store, documents_store, chat_store, research_threads, migrate_documents_to_postgres):
        monkeypatch.setattr(module, "async_session_factory", factory)


@pytest_asyncio.fixture
async def pg(monkeypatch):
    schema = f"nexora_it_{uuid.uuid4().hex[:12]}"
    admin = create_async_engine(PG_URL, isolation_level="AUTOCOMMIT")
    async with admin.connect() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))

    engine = _schema_engine(schema)
    async with engine.begin() as conn:
        for sql_file in sorted(SQL_DIR.glob("*.sql")):
            await conn.exec_driver_sql(sql_file.read_text(encoding="utf-8"))

    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    _patch_factory(monkeypatch, factory)
    yield SimpleFixture(schema, engine, factory)

    await engine.dispose()
    async with admin.connect() as conn:
        await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    await admin.dispose()


class SimpleFixture:
    def __init__(self, schema, engine, factory):
        self.schema, self.engine, self.factory = schema, engine, factory


async def _thread(user_id=USER) -> str:
    return await research_threads.create_thread(user_id, "test domain")


def _report(marker="A") -> dict:
    return {
        "domain": f"domain {marker}",
        "introduction": f"intro {marker}",
        "evidence_table": [{"title": f"Paper {marker}", "methodology_summary": "m", "results_summary": "r"}],
        "contradictions": [],
        "gaps": [{"theme": "t", "support_count": 2, "supporting_paper_titles": ["Paper A"]}],
        "analysis_incomplete": False,
    }


# ------------------------------------------------------------------
# Migration files
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_migrations_are_idempotent(pg):
    async with pg.engine.begin() as conn:
        for sql_file in sorted(SQL_DIR.glob("*.sql")):
            await conn.exec_driver_sql(sql_file.read_text(encoding="utf-8"))  # second run: IF NOT EXISTS


# ------------------------------------------------------------------
# reports
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_report_round_trips_through_postgres_unchanged(pg):
    thread_id = await _thread()
    report = _report()

    await report_store.register_report(thread_id, report)

    assert await report_store.get_report(thread_id) == report


@pytest.mark.asyncio
async def test_get_report_for_unregistered_thread_is_none_not_sample_data(pg):
    thread_id = await _thread()  # a real thread that simply has no report yet

    assert await report_store.get_report(thread_id) is None
    assert await report_store.get_report("no-such-thread") is None


@pytest.mark.asyncio
async def test_register_report_twice_overwrites_the_previous_one(pg):
    thread_id = await _thread()

    await report_store.register_report(thread_id, _report("first"))
    await report_store.register_report(thread_id, _report("second"))

    stored = await report_store.get_report(thread_id)
    assert stored is not None and stored["introduction"] == "intro second"
    async with pg.factory() as session:
        count = await session.scalar(text("SELECT count(*) FROM reports"))
    assert count == 1


@pytest.mark.asyncio
async def test_report_requires_an_existing_thread(pg):
    with pytest.raises(IntegrityError):
        await report_store.register_report("no-such-thread", _report())


@pytest.mark.asyncio
async def test_report_survives_a_fresh_connection_pool(pg, monkeypatch):
    """The "backend restarted" case: a brand-new engine (new process, new
    pool) still reads the report the old one wrote."""
    thread_id = await _thread()
    await report_store.register_report(thread_id, _report())

    fresh_engine = _schema_engine(pg.schema)
    _patch_factory(monkeypatch, async_sessionmaker(bind=fresh_engine, expire_on_commit=False))
    try:
        assert await report_store.get_report(thread_id) == _report()
    finally:
        await fresh_engine.dispose()


# ------------------------------------------------------------------
# documents
# ------------------------------------------------------------------

async def _doc(*, user=USER, session_id=None, thread_id=None, title="p.pdf") -> str:
    document_id = str(uuid.uuid4())
    await documents_store.create_document(
        document_id=document_id, user_id=user, title=title, n_pages=3,
        file_path=f"/tmp/{document_id}.pdf", thread_id=thread_id, session_id=session_id,
    )
    return document_id


@pytest.mark.asyncio
async def test_document_round_trip(pg):
    document_id = await _doc(session_id="s1", title="paper.pdf")

    doc = await documents_store.get_document(document_id)

    assert doc is not None
    assert (doc.title, doc.n_pages, doc.user_id, doc.session_id, doc.thread_id) == ("paper.pdf", 3, USER, "s1", None)
    assert await documents_store.get_document("missing") is None


@pytest.mark.asyncio
async def test_list_documents_by_session_thread_and_both(pg):
    thread_id = await _thread()
    in_session = await _doc(session_id="s1")
    in_thread = await _doc(thread_id=thread_id)
    elsewhere = await _doc(session_id="s2")
    others = await _doc(user=OTHER, session_id="s1")

    ids = lambda docs: [d.document_id for d in docs]  # noqa: E731
    assert ids(await documents_store.list_documents(USER, session_id="s1")) == [in_session]
    assert ids(await documents_store.list_documents(USER, thread_id=thread_id)) == [in_thread]
    assert ids(await documents_store.list_documents(USER, session_id="s1", thread_id=thread_id)) == [in_session, in_thread]
    assert elsewhere not in ids(await documents_store.list_documents(USER, session_id="s1"))
    assert others not in ids(await documents_store.list_documents(USER, session_id="s1"))  # owner-scoped
    assert await documents_store.list_documents(USER) == []  # no scope -> nothing, never "everything"


@pytest.mark.asyncio
async def test_delete_document(pg):
    document_id = await _doc(session_id="s1")

    await documents_store.delete_document(document_id)

    assert await documents_store.get_document(document_id) is None
    assert await documents_store.list_documents(USER, session_id="s1") == []


@pytest.mark.asyncio
async def test_document_thread_must_exist(pg):
    with pytest.raises(IntegrityError):
        await _doc(thread_id="no-such-thread")


# ------------------------------------------------------------------
# chat_messages
# ------------------------------------------------------------------

async def _turn(*, session_id: str | None = "s1", thread_id: str | None = None, document_id: str | None = None, user: str = USER, q: str = "hello?", a: str = "hi!", mode: str = "general", sources: list | None = None):
    assistant_id = str(uuid.uuid4())
    await chat_store.save_chat_turn(
        user_id=user, session_id=session_id, thread_id=thread_id, document_id=document_id,
        user_content=q, assistant_message_id=assistant_id, assistant_content=a,
        mode=mode, sources=sources or [],
    )
    return assistant_id


@pytest.mark.asyncio
async def test_chat_turn_is_stored_and_history_returns_it_in_order(pg):
    sources = [
        {"kind": "report", "label": "Deep Search report", "id": "t", "url": None},
        {"kind": "web", "label": "python.org", "id": None, "url": "https://python.org"},
    ]
    assistant_id = await _turn(q="what?", a="that [Report]", mode="grounded", sources=sources)

    history = await chat_store.list_chat_messages(USER, session_id="s1")

    assert [(m.role, m.content, m.mode) for m in history] == [
        ("user", "what?", None),
        ("assistant", "that [Report]", "grounded"),
    ]
    assert history[1].message_id == assistant_id
    assert history[1].sources == sources  # JSONB round-trip, unchanged
    assert history[0].sources == []


@pytest.mark.asyncio
async def test_history_keeps_turn_order_across_many_turns(pg):
    for i in range(5):
        await _turn(q=f"q{i}", a=f"a{i}")

    history = await chat_store.list_chat_messages(USER, session_id="s1")

    assert [m.content for m in history] == [x for i in range(5) for x in (f"q{i}", f"a{i}")]


@pytest.mark.asyncio
async def test_history_after_restart_is_read_from_postgres_not_memory(pg, monkeypatch):
    await _turn(q="before restart", a="answer")

    fresh_engine = _schema_engine(pg.schema)  # new pool == new process
    _patch_factory(monkeypatch, async_sessionmaker(bind=fresh_engine, expire_on_commit=False))
    try:
        history = await chat_store.list_chat_messages(USER, session_id="s1")
    finally:
        await fresh_engine.dispose()

    assert [m.content for m in history] == ["before restart", "answer"]


@pytest.mark.asyncio
async def test_history_is_owner_and_scope_specific(pg):
    thread_id = await _thread()
    await _turn(session_id="s1", q="mine")
    await _turn(session_id="s2", q="other session")
    await _turn(session_id="s1", user=OTHER, q="someone else")
    await _turn(session_id=None, thread_id=thread_id, q="thread message")

    contents = lambda msgs: [m.content for m in msgs if m.role == "user"]  # noqa: E731
    assert contents(await chat_store.list_chat_messages(USER, session_id="s1")) == ["mine"]
    assert contents(await chat_store.list_chat_messages(USER, thread_id=thread_id)) == ["thread message"]
    assert await chat_store.list_chat_messages(USER) == []  # no scope -> nothing


@pytest.mark.asyncio
async def test_message_must_belong_to_a_thread_a_document_or_a_session(pg):
    with pytest.raises(ValueError):
        await _turn(session_id=None, thread_id=None, document_id=None)

    # ...and the table itself enforces the same rule, not just the Python.
    async with pg.factory() as session:
        with pytest.raises(IntegrityError):
            async with session.begin():
                await session.execute(text(
                    "INSERT INTO chat_messages (message_id, user_id, role, content, created_at) "
                    "VALUES (gen_random_uuid(), 'u', 'user', 'x', now())"
                ))


@pytest.mark.asyncio
@pytest.mark.parametrize("column,value", [("role", "system"), ("mode", "deep")])
async def test_role_and_mode_are_constrained(pg, column, value):
    row = {"role": "user", "mode": "general"}
    row[column] = value
    async with pg.factory() as session:
        with pytest.raises(IntegrityError):
            async with session.begin():
                await session.execute(
                    text(
                        "INSERT INTO chat_messages (message_id, user_id, session_id, role, content, mode, created_at) "
                        "VALUES (gen_random_uuid(), 'u', 's', :role, 'x', :mode, now())"
                    ),
                    row,
                )


@pytest.mark.asyncio
async def test_a_message_can_be_anchored_to_a_document_and_a_thread(pg):
    thread_id = await _thread()
    document_id = await _doc(session_id="s1")

    await _turn(session_id="s1", thread_id=thread_id, document_id=document_id, q="both")

    assert [m.content for m in await chat_store.list_chat_messages(USER, thread_id=thread_id)] == ["both", "hi!"]
    async with pg.factory() as session:
        stored_document = await session.scalar(text("SELECT DISTINCT document_id FROM chat_messages"))
    assert stored_document == document_id


@pytest.mark.asyncio
async def test_deleting_a_document_keeps_the_conversation(pg):
    document_id = await _doc(session_id="s1")
    await _turn(session_id="s1", document_id=document_id, q="about the doc")

    await documents_store.delete_document(document_id)

    history = await chat_store.list_chat_messages(USER, session_id="s1")
    assert [m.content for m in history] == ["about the doc", "hi!"]
    async with pg.factory() as session:
        assert await session.scalar(text("SELECT count(*) FROM chat_messages WHERE document_id IS NOT NULL")) == 0


# ------------------------------------------------------------------
# One-off SQLite -> Postgres documents migration
# ------------------------------------------------------------------

def _legacy_sqlite(tmp_path) -> Path:
    path = tmp_path / "documents.db"
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE documents (document_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, title TEXT NOT NULL,
            n_pages INTEGER NOT NULL, file_path TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE document_chat_history (message_id TEXT PRIMARY KEY, document_id TEXT NOT NULL,
            role TEXT NOT NULL, content TEXT NOT NULL, timestamp TEXT NOT NULL);
        INSERT INTO documents VALUES ('doc-1', 'user-a', 'old.pdf', 7, '/uploads/doc-1.pdf', '2026-01-02T03:04:05+00:00');
        INSERT INTO documents VALUES ('doc-2', 'user-b', 'other.pdf', 2, '/uploads/doc-2.pdf', '2026-01-03T00:00:00+00:00');
        """
    )
    connection.executemany(
        "INSERT INTO document_chat_history VALUES (?, ?, ?, ?, ?)",
        [
            (str(uuid.uuid4()), "doc-1", "user", "old question", "2026-01-02T03:10:00+00:00"),
            (str(uuid.uuid4()), "doc-1", "assistant", "old answer", "2026-01-02T03:10:00+00:00"),
        ],
    )
    connection.commit()
    connection.close()
    return path


@pytest.mark.asyncio
async def test_migration_moves_documents_and_their_chat_history(pg, tmp_path):
    source = _legacy_sqlite(tmp_path)

    counts = await migrate_documents_to_postgres.migrate_documents(source)

    assert counts == (2, 2)
    doc = await documents_store.get_document("doc-1")
    assert doc is not None
    assert (doc.user_id, doc.title, doc.n_pages, doc.file_path) == ("user-a", "old.pdf", 7, "/uploads/doc-1.pdf")
    assert (doc.session_id, doc.thread_id) == (None, None)  # no association existed before

    async with pg.factory() as session:
        rows = (await session.execute(text(
            "SELECT role, content, mode, document_id, user_id FROM chat_messages ORDER BY role"
        ))).all()
    assert rows == [
        ("assistant", "old answer", "grounded", "doc-1", "user-a"),
        ("user", "old question", None, "doc-1", "user-a"),
    ]


@pytest.mark.asyncio
async def test_migration_is_idempotent_and_leaves_the_source_untouched(pg, tmp_path):
    source = _legacy_sqlite(tmp_path)
    before = source.read_bytes()

    await migrate_documents_to_postgres.migrate_documents(source)
    await migrate_documents_to_postgres.migrate_documents(source)  # second run: no duplicates, no error

    async with pg.factory() as session:
        assert await session.scalar(text("SELECT count(*) FROM documents")) == 2
        assert await session.scalar(text("SELECT count(*) FROM chat_messages")) == 2
    assert source.read_bytes() == before
