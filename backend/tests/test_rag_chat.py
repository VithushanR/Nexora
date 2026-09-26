"""
backend/tests/test_rag_chat.py

Part D — tests for rag/chat.py

These tests use the REAL sentence-transformers embedding model and REAL
FAISS index (both are already in requirements.txt), but mock out the
Gemini call in rag_chat() so tests don't need a live GEMINI_API_KEY or
network access to run.

Covers the two non-negotiable rules from the handoff doc §D.2:
    1. Namespaces must never collide (a document namespace query must
       never return report namespace chunks, and vice versa).
    2. build_index() overwrites, it does not append -- rebuilding a
       namespace replaces its old content entirely.

NOTE: the first test run will download the embedding model
(all-MiniLM-L6-v2, ~90MB) if it isn't already cached locally. This is a
one-time cost per machine.
"""

import pytest

import rag.chat as rag_chat_module
from rag.chat import build_index, query, rag_chat


@pytest.fixture(autouse=True)
def clean_index_store(tmp_path, monkeypatch):
    """
    Each test gets its own empty index directory so tests can't leak state
    into each other -- and never touch the real backend/rag/index_store/
    (deleting that directory used to wipe every real index in it).
    """
    monkeypatch.setattr(rag_chat_module, "_INDEX_STORE_DIR", str(tmp_path))
    yield


class TestBuildAndQuery:
    def test_query_returns_relevant_chunk_first(self):
        chunks = [
            "The mitochondria is the powerhouse of the cell.",
            "Graph neural networks operate on non-Euclidean data structures.",
            "Photosynthesis converts sunlight into chemical energy in plants.",
        ]
        build_index(chunks, namespace="document:test-doc-1")

        results = query("document:test-doc-1", "How do plants get energy from the sun?", top_k=2)

        assert len(results) == 2
        assert "photosynthesis" in results[0]["text"].lower()
        assert "score" in results[0]
        assert isinstance(results[0]["score"], float)

    def test_query_on_empty_namespace_returns_empty_list(self):
        # Nothing was ever build_index()'d for this namespace.
        results = query("document:never-built", "anything")
        assert results == []

    def test_top_k_respected(self):
        chunks = [f"This is chunk number {i} about topic {i}." for i in range(10)]
        build_index(chunks, namespace="report:many-chunks")

        results = query("report:many-chunks", "topic 5", top_k=3)
        assert len(results) == 3


class TestNamespaceIsolation:
    """
    The non-negotiable rule from §D.2: a document chat must never
    retrieve report chunks or vice versa.
    """

    def test_document_and_report_namespaces_never_cross(self):
        report_chunks = [
            "Evidence table row: this paper found a 15% improvement in accuracy.",
            "Contradiction: Paper A claims X, Paper B claims not-X.",
        ]
        document_chunks = [
            "Uploaded PDF abstract: a study on reinforcement learning in robotics.",
            "The methodology section describes a novel reward shaping technique.",
        ]

        build_index(report_chunks, namespace="report:thread-abc")
        build_index(document_chunks, namespace="document:doc-xyz")

        # Querying the document namespace should NEVER surface report content.
        doc_results = query("document:doc-xyz", "accuracy improvement evidence")
        for r in doc_results:
            assert "evidence table" not in r["text"].lower()
            assert "contradiction" not in r["text"].lower()

        # Querying the report namespace should NEVER surface document content.
        report_results = query("report:thread-abc", "reinforcement learning robotics")
        for r in report_results:
            assert "reinforcement learning" not in r["text"].lower()
            assert "reward shaping" not in r["text"].lower()

    def test_similar_id_suffixes_do_not_collide(self):
        # "report:123" and "document:123" share the same trailing id --
        # confirm the prefix keeps them separate on disk.
        build_index(["Report content for thread 123."], namespace="report:123")
        build_index(["Document content for upload 123."], namespace="document:123")

        report_result = query("report:123", "content")
        doc_result = query("document:123", "content")

        assert "Report content" in report_result[0]["text"]
        assert "Document content" in doc_result[0]["text"]


class TestOverwriteBehavior:
    """
    §D.2: build_index() "Overwrites any existing index for that
    namespace" -- this is NOT additive.
    """

    def test_rebuilding_namespace_replaces_old_content(self):
        build_index(["Old content, version one."], namespace="document:versioned")
        build_index(["Brand new content, version two."], namespace="document:versioned")

        results = query("document:versioned", "content", top_k=5)

        # Only the second build's chunk should exist -- old content is gone,
        # not appended alongside the new.
        assert len(results) == 1
        assert "version two" in results[0]["text"]
        assert "version one" not in results[0]["text"]


class TestInputValidation:
    def test_build_index_rejects_empty_chunks(self):
        with pytest.raises(ValueError):
            build_index([], namespace="document:empty")

    def test_build_index_rejects_empty_namespace(self):
        with pytest.raises(ValueError):
            build_index(["some text"], namespace="")

    def test_query_rejects_empty_question(self):
        build_index(["some text"], namespace="document:valid")
        with pytest.raises(ValueError):
            query("document:valid", "")


class TestRagChat:
    """
    rag_chat() = query() + Gemini generation. We mock the Gemini call
    here so this test suite doesn't need GEMINI_API_KEY or network
    access to run in CI.
    """

    def test_rag_chat_grounds_answer_in_retrieved_context(self, monkeypatch):
        build_index(
            ["The experiment showed a 42% reduction in latency."],
            namespace="document:mocked",
        )

        captured_prompt = {}

        class FakeResponse:
            text = "Based on the context, latency was reduced by 42%."

        class FakeModels:
            def generate_content(self, model, contents):
                captured_prompt["prompt"] = contents
                return FakeResponse()

        class FakeClient:
            models = FakeModels()

        monkeypatch.setattr(rag_chat_module, "_get_genai_client", lambda: FakeClient())

        answer = rag_chat("document:mocked", "What happened to latency?")

        assert answer == "Based on the context, latency was reduced by 42%."
        # Confirm the retrieved chunk actually made it into the prompt sent to Gemini.
        assert "42% reduction in latency" in captured_prompt["prompt"]
        # Confirm the context is clearly delimited, per the module's own
        # injection-resistance design.
        assert "<context>" in captured_prompt["prompt"]
        assert "</context>" in captured_prompt["prompt"]

    def test_rag_chat_handles_empty_namespace_gracefully(self, monkeypatch):
        class FakeResponse:
            text = "I don't have any relevant information to answer that."

        class FakeModels:
            def generate_content(self, model, contents):
                return FakeResponse()

        class FakeClient:
            models = FakeModels()

        monkeypatch.setattr(rag_chat_module, "_get_genai_client", lambda: FakeClient())

        # Namespace was never built -- should not raise, should still
        # produce a user-facing answer via the LLM.
        answer = rag_chat("document:nonexistent", "What does this say?")
        assert isinstance(answer, str)
        assert len(answer) > 0
