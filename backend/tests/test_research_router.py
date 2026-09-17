"""No-I/O tests for the research HTTP API."""

from contextlib import asynccontextmanager
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routers import research


@dataclass
class FakeUser:
    id: str


@dataclass
class FakeThread:
    thread_id: str
    user_id: str
    domain: str
    status: str
    created_at: str = "2026-01-01T00:00:00+00:00"


class FakeInterrupt:
    def __init__(self, value: dict[str, Any]) -> None:
        self.value = value


class FakeGraph:
    def __init__(self) -> None:
        self.candidates = [
            {
                "title": "Eligible paper",
                "doi": "10.1000/example",
                "abstract": "A usable abstract.",
                "year": 2024,
                "source": "openalex",
                "verdict": "INCLUDE",
                "quote": "usable abstract",
                "reason": "Matches the protocol.",
                "prerank_score": 8.5,
                "has_usable_abstract": True,
                "arxiv_id": "internal-id",
                "pmcid": "internal-pmcid",
            },
            {
                "title": "Second paper",
                "doi": None,
                "abstract": "Another usable abstract.",
                "year": 2023,
                "source": "arxiv",
                "verdict": "UNCERTAIN",
                "quote": "",
                "reason": "Needs review.",
                "prerank_score": 3.0,
                "has_usable_abstract": True,
            },
        ]
        self.interrupted = True
        self.fail_start = False
        self.fail_resume = False
        self.report: str | None = "# Completed report"
        self.resume_payloads: list[dict[str, Any]] = []

    async def ainvoke(self, input_value, config=None):
        if hasattr(input_value, "resume"):
            self.resume_payloads.append(input_value.resume)
            if self.fail_resume:
                raise RuntimeError("controlled resume failure")
            self.interrupted = False
            return {"report": self.report}
        if self.fail_start:
            raise RuntimeError("controlled start failure")
        return {"__interrupt__": [FakeInterrupt({"kind": "paper_selection"})]}

    async def aget_state(self, config):
        interrupts = (
            (FakeInterrupt({"kind": "paper_selection", "candidates": self.candidates}),)
            if self.interrupted
            else ()
        )
        values: dict[str, Any] = {"candidates": self.candidates}
        if not self.interrupted and self.report is not None:
            values["report"] = self.report
        return SimpleNamespace(values=values, interrupts=interrupts, next=())


@pytest.fixture
def router_environment(monkeypatch):
    threads: dict[str, FakeThread] = {}
    updates: list[tuple[str, str]] = []
    graph = FakeGraph()
    next_thread = 0

    async def fake_create_thread(user_id, domain):
        nonlocal next_thread
        next_thread += 1
        thread_id = f"thread-{next_thread}"
        threads[thread_id] = FakeThread(thread_id, str(user_id), domain, "running_agent2")
        return thread_id

    async def fake_get_thread(thread_id):
        return threads.get(thread_id)

    async def fake_update_status(thread_id, new_status):
        thread = threads.get(thread_id)
        if thread is None:
            return False
        thread.status = new_status
        updates.append((thread_id, new_status))
        return True

    async def fake_verify_owner(thread_id, user_id):
        thread = threads.get(thread_id)
        return thread is not None and thread.user_id == str(user_id)

    @asynccontextmanager
    async def fake_graph_context():
        yield graph

    monkeypatch.setattr(research, "create_thread", fake_create_thread)
    monkeypatch.setattr(research, "get_thread", fake_get_thread)
    monkeypatch.setattr(research, "update_thread_status", fake_update_status)
    monkeypatch.setattr(research, "verify_thread_owner", fake_verify_owner)
    monkeypatch.setattr(research, "graph_context", fake_graph_context)
    monkeypatch.setattr(research, "_start_rate_limiter", research.ResearchStartRateLimiter())

    app = FastAPI()
    app.include_router(research.router)
    app.dependency_overrides[research.get_current_user_dependency] = lambda: FakeUser("owner-1")
    return SimpleNamespace(app=app, threads=threads, updates=updates, graph=graph)


def _client(environment):
    return TestClient(environment.app)


def _paused_thread(environment, *, owner="owner-1"):
    thread = FakeThread("paused-thread", owner, "Test domain", "paused_for_selection")
    environment.threads[thread.thread_id] = thread
    return thread


def test_start_research_reaches_selection_and_returns_created_thread(router_environment):
    with _client(router_environment) as client:
        response = client.post("/research", json={"domain": "Climate adaptation"})

    assert response.status_code == 201
    thread_id = response.json()["thread_id"]
    assert router_environment.threads[thread_id].status == "paused_for_selection"
    assert (thread_id, "paused_for_selection") in router_environment.updates


def test_start_research_graph_failure_marks_error_without_leaking_exception(router_environment):
    router_environment.graph.fail_start = True

    with _client(router_environment) as client:
        response = client.post("/research", json={"domain": "Climate adaptation"})

    assert response.status_code == 500
    assert response.json()["detail"] == "Research processing failed."
    assert all("controlled start failure" not in str(value) for value in response.json().values())
    assert next(iter(router_environment.threads.values())).status == "error"


def test_default_authentication_seam_rejects_requests(router_environment):
    router_environment.app.dependency_overrides.clear()

    with _client(router_environment) as client:
        response = client.post("/research", json={"domain": "Climate adaptation"})

    assert response.status_code == 503
    assert response.json()["detail"] == "Authentication is not configured."


def test_status_returns_safe_metadata_detail(router_environment):
    thread = _paused_thread(router_environment)

    with _client(router_environment) as client:
        response = client.get(f"/research/{thread.thread_id}/status")

    assert response.status_code == 200
    assert response.json() == {
        "status": "paused_for_selection",
        "detail": "Research is waiting for paper selection.",
    }


def test_missing_and_unowned_threads_both_return_not_found(router_environment):
    _paused_thread(router_environment, owner="other-user")

    with _client(router_environment) as client:
        missing = client.get("/research/missing/status")
        unowned = client.get("/research/paused-thread/status")

    assert missing.status_code == 404
    assert unowned.status_code == 404
    assert missing.json() == unowned.json() == {"detail": "Research thread not found."}


def test_candidates_return_only_the_public_candidate_projection(router_environment):
    thread = _paused_thread(router_environment)

    with _client(router_environment) as client:
        response = client.get(f"/research/{thread.thread_id}/candidates")

    assert response.status_code == 200
    candidate = response.json()["eligible_candidates"][0]
    assert candidate["title"] == "Eligible paper"
    assert "arxiv_id" not in candidate
    assert "pmcid" not in candidate
    assert set(candidate) == {
        "title", "doi", "abstract", "year", "source", "verdict", "quote",
        "reason", "prerank_score", "has_usable_abstract",
    }


def test_candidates_require_paused_metadata_status(router_environment):
    thread = FakeThread("running-thread", "owner-1", "Test domain", "running_agent2")
    router_environment.threads[thread.thread_id] = thread

    with _client(router_environment) as client:
        response = client.get(f"/research/{thread.thread_id}/candidates")

    assert response.status_code == 409


def test_candidates_require_a_pending_selection_checkpoint(router_environment):
    thread = _paused_thread(router_environment)
    router_environment.graph.interrupted = False

    with _client(router_environment) as client:
        response = client.get(f"/research/{thread.thread_id}/candidates")

    assert response.status_code == 409


def test_select_resumes_checkpoint_in_background_and_marks_done(router_environment):
    thread = _paused_thread(router_environment)

    with _client(router_environment) as client:
        response = client.post(
            f"/research/{thread.thread_id}/select",
            json={"selected_indices": [0, 1]},
        )

    assert response.status_code == 200
    assert response.json() == {"status": "running_synthesis"}
    assert router_environment.graph.resume_payloads == [{"selected_indices": [0, 1]}]
    assert (thread.thread_id, "running_synthesis") in router_environment.updates
    assert router_environment.threads[thread.thread_id].status == "done"


@pytest.mark.parametrize(
    "selected_indices",
    [[], [0, 0], [-1], [2], [True], ["0"]],
)
def test_invalid_selection_is_rejected_without_resume_or_status_change(router_environment, selected_indices):
    thread = _paused_thread(router_environment)

    with _client(router_environment) as client:
        response = client.post(
            f"/research/{thread.thread_id}/select",
            json={"selected_indices": selected_indices},
        )

    assert response.status_code == 422
    assert router_environment.graph.resume_payloads == []
    assert router_environment.threads[thread.thread_id].status == "paused_for_selection"


def test_background_resume_failure_marks_metadata_error(router_environment):
    thread = _paused_thread(router_environment)
    router_environment.graph.fail_resume = True

    with _client(router_environment) as client:
        response = client.post(
            f"/research/{thread.thread_id}/select",
            json={"selected_indices": [0]},
        )

    assert response.status_code == 200
    assert response.json() == {"status": "running_synthesis"}
    assert router_environment.threads[thread.thread_id].status == "error"


def test_report_requires_done_status(router_environment):
    thread = _paused_thread(router_environment)

    with _client(router_environment) as client:
        response = client.get(f"/research/{thread.thread_id}/report")

    assert response.status_code == 404


def test_report_returns_runtime_markdown_when_done(router_environment):
    thread = FakeThread("done-thread", "owner-1", "Test domain", "done")
    router_environment.threads[thread.thread_id] = thread
    router_environment.graph.interrupted = False
    router_environment.graph.report = "# Completed report"

    with _client(router_environment) as client:
        response = client.get(f"/research/{thread.thread_id}/report")

    assert response.status_code == 200
    assert response.json() == {"report": "# Completed report"}


def test_done_thread_without_report_returns_safe_server_error(router_environment):
    thread = FakeThread("done-thread", "owner-1", "Test domain", "done")
    router_environment.threads[thread.thread_id] = thread
    router_environment.graph.interrupted = False
    router_environment.graph.report = None

    with _client(router_environment) as client:
        response = client.get(f"/research/{thread.thread_id}/report")

    assert response.status_code == 500
    assert response.json()["detail"] == "Research report is unavailable."


def test_start_rate_limit_rejects_the_eleventh_request(router_environment):
    with _client(router_environment) as client:
        responses = [
            client.post("/research", json={"domain": f"Topic {number}"})
            for number in range(11)
        ]

    assert [response.status_code for response in responses[:10]] == [201] * 10
    assert responses[10].status_code == 429
