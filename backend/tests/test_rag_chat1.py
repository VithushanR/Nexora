"""
backend/tests/test_rag_chat1.py

Second, independent test suite for rag/chat.py.

This suite uses its own fake JSON file (fake_rag_data1.json) so it can
live alongside an existing test_rag_chat.py without any name or data
collisions. It uses the REAL SentenceTransformer model and REAL FAISS
index, exactly like the real module does. Only Gemini is mocked.

What this suite checks that a first pass often misses:
1. FAISS scores come back in ascending order (lower L2 distance = closer).
2. query() honors its own default top_k=5 when the caller doesn't pass one.
3. _sanitize_namespace() actually replaces ":" with "_".
4. build_index() writes real files on disk at the sanitized path.
5. rag_chat() lets a caller override the default system_prompt.
6. rag_chat() inserts the "(No relevant context was found...)" placeholder
   when the namespace has no index.
7. rag_chat() falls back to a friendly message when Gemini returns
   response.text = None (e.g. safety-filtered generations).
8. rag_chat() validates its own namespace/question arguments, not just
   query()'s.
"""

import json
import os
from pathlib import Path

import pytest

import rag.chat as rag_chat_module
from rag.chat import (
    build_index,
    query,
    rag_chat,
    _index_path,
    _chunks_path,
    _sanitize_namespace,
    _DEFAULT_SYSTEM_PROMPT,
)


# ---------------------------------------------------------------------------
# Fake JSON data
# ---------------------------------------------------------------------------

DATA_FILE = Path(__file__).parent / "data" / "fake_rag_data1.json"


def load_fake_data():
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Test isolation
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clean_index_store(tmp_path, monkeypatch):
    """
    Each test gets its own empty index directory so this suite never leaks
    state into itself or a separately-run suite -- and never touches the
    real backend/rag/index_store/.
    """
    monkeypatch.setattr(rag_chat_module, "_INDEX_STORE_DIR", str(tmp_path))
    yield


# ---------------------------------------------------------------------------
# Retrieval quality
# ---------------------------------------------------------------------------

class TestRetrievalQuality:

    def test_best_match_has_the_lowest_score(self):
        """
        query() returns raw L2 distance as "score" -- LOWER means more
        similar. The best match must be first AND must have the smallest
        score of the batch, not just be first by coincidence of order.
        """
        data = load_fake_data()
        document = data["documents"][0]

        build_index(
            document["content"],
            namespace=f"document:{document['id']}",
        )

        results = query(
            "document:doc-101",
            "What is the biggest planet?",
            top_k=3,
        )

        assert len(results) == 3
        assert "jupiter" in results[0]["text"].lower()

        scores = [r["score"] for r in results]
        assert scores == sorted(scores)  # ascending: best match first

    def test_default_top_k_is_five(self):
        """
        query()'s signature is query(namespace, question, top_k=5).
        Calling it with no top_k at all must return 5 results, not
        everything in the namespace.
        """
        data = load_fake_data()
        report = data["reports"][1]  # thread-102, 8 chunks

        build_index(
            report["content"],
            namespace=f"report:{report['id']}",
        )

        results = query("report:thread-102", "chunk from the report")

        assert len(results) == 5


# ---------------------------------------------------------------------------
# Namespace isolation
# ---------------------------------------------------------------------------

class TestNamespaceIsolation:

    def test_document_and_report_never_cross(self):
        data = load_fake_data()
        report = data["reports"][0]
        document = data["documents"][1]

        build_index(
            report["content"],
            namespace=f"report:{report['id']}",
        )
        build_index(
            document["content"],
            namespace=f"document:{document['id']}",
        )

        doc_results = query("document:doc-102", "server database migration")
        for result in doc_results:
            assert "caching layer" not in result["text"].lower()
            assert "zero downtime" not in result["text"].lower()

        report_results = query("report:thread-101", "sea levels temperature")
        for result in report_results:
            assert "sea level" not in result["text"].lower()
            assert "temperature" not in result["text"].lower()


# ---------------------------------------------------------------------------
# Overwrite behavior
# ---------------------------------------------------------------------------

class TestOverwriteBehavior:

    def test_rebuild_replaces_old_content(self):
        data = load_fake_data()
        old_content = data["overwrite_test"]["old"]
        new_content = data["overwrite_test"]["new"]

        build_index(old_content, namespace="document:draft")
        build_index(new_content, namespace="document:draft")

        results = query("document:draft", "summary", top_k=5)

        assert len(results) == 1
        assert "final, corrected" in results[0]["text"]
        assert "first draft" not in results[0]["text"]


# ---------------------------------------------------------------------------
# Filesystem / sanitization behavior
# ---------------------------------------------------------------------------

class TestFileSystemBehavior:

    def test_sanitize_namespace_replaces_colon(self):
        assert _sanitize_namespace("document:abc-123") == "document_abc-123"
        assert _sanitize_namespace("report:thread-1") == "report_thread-1"

    def test_build_index_writes_files_at_sanitized_path(self):
        build_index(["some content"], namespace="document:file-check")

        assert os.path.exists(_index_path("document:file-check"))
        assert os.path.exists(_chunks_path("document:file-check"))

        # The sanitized name should have no ":" in it anywhere on disk.
        assert ":" not in os.path.basename(_index_path("document:file-check"))


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

class TestInputValidation:

    def test_build_index_rejects_empty_chunks(self):
        with pytest.raises(ValueError):
            build_index([], namespace="document:empty")

    def test_build_index_rejects_empty_namespace(self):
        with pytest.raises(ValueError):
            build_index(["text"], namespace="")

    def test_query_rejects_empty_namespace(self):
        with pytest.raises(ValueError):
            query("", "some question")

    def test_query_rejects_empty_question(self):
        build_index(["text"], namespace="document:valid")
        with pytest.raises(ValueError):
            query("document:valid", "")

    def test_rag_chat_rejects_empty_namespace(self):
        with pytest.raises(ValueError):
            rag_chat("", "some question")

    def test_rag_chat_rejects_empty_question(self):
        with pytest.raises(ValueError):
            rag_chat("document:valid", "")


# ---------------------------------------------------------------------------
# RAG chat behavior (Gemini mocked)
# ---------------------------------------------------------------------------

def _make_fake_client(response_text, captured):
    """Small helper to build a fake genai client that records the prompt."""

    class FakeResponse:
        text = response_text

    class FakeModels:
        def generate_content(self, model, contents):
            captured["prompt"] = contents
            captured["model"] = model
            return FakeResponse()

    class FakeClient:
        models = FakeModels()

    return FakeClient()


class TestRagChat:

    def test_default_system_prompt_is_used_when_not_overridden(self, monkeypatch):
        captured = {}
        monkeypatch.setattr(
            rag_chat_module,
            "_get_genai_client",
            lambda: _make_fake_client("An answer.", captured),
        )

        build_index(["Some fact."], namespace="document:prompt-check")
        rag_chat("document:prompt-check", "What is the fact?")

        assert _DEFAULT_SYSTEM_PROMPT in captured["prompt"]

    def test_custom_system_prompt_overrides_default(self, monkeypatch):
        captured = {}
        monkeypatch.setattr(
            rag_chat_module,
            "_get_genai_client",
            lambda: _make_fake_client("An answer.", captured),
        )

        build_index(["Some fact."], namespace="document:prompt-override")
        custom_prompt = "You are a pirate. Answer only in pirate speak."

        rag_chat(
            "document:prompt-override",
            "What is the fact?",
            system_prompt=custom_prompt,
        )

        assert custom_prompt in captured["prompt"]
        assert _DEFAULT_SYSTEM_PROMPT not in captured["prompt"]

    def test_context_block_joins_multiple_chunks(self, monkeypatch):
        captured = {}
        monkeypatch.setattr(
            rag_chat_module,
            "_get_genai_client",
            lambda: _make_fake_client("An answer.", captured),
        )

        data = load_fake_data()
        chunks = data["context_join_test"]["chunks"]
        build_index(chunks, namespace="document:join-check")

        rag_chat("document:join-check", "Tell me the facts")

        assert "First retrieved fact about the topic." in captured["prompt"]
        assert "Second retrieved fact about the topic." in captured["prompt"]

    def test_empty_namespace_inserts_no_context_placeholder(self, monkeypatch):
        captured = {}
        monkeypatch.setattr(
            rag_chat_module,
            "_get_genai_client",
            lambda: _make_fake_client("An answer.", captured),
        )

        rag_chat("document:never-built", "Anything?")

        assert (
            "(No relevant context was found for this namespace.)"
            in captured["prompt"]
        )

    def test_question_is_included_in_the_prompt(self, monkeypatch):
        captured = {}
        monkeypatch.setattr(
            rag_chat_module,
            "_get_genai_client",
            lambda: _make_fake_client("An answer.", captured),
        )

        build_index(["Some fact."], namespace="document:question-check")
        rag_chat("document:question-check", "What is the meaning of life?")

        assert "Question: What is the meaning of life?" in captured["prompt"]

    def test_none_response_falls_back_to_friendly_message(self, monkeypatch):
        """
        Gemini's response.text can be None (e.g. safety filtering). The
        real rag_chat() must never let None reach the caller -- it should
        substitute the documented fallback string instead.
        """
        captured = {}
        monkeypatch.setattr(
            rag_chat_module,
            "_get_genai_client",
            lambda: _make_fake_client(None, captured),
        )

        build_index(["Some fact."], namespace="document:none-check")
        answer = rag_chat("document:none-check", "What is the fact?")

        assert answer == "Could not generate an answer for this question right now."
