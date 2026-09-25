"""No-I/O tests for the research HTTP API."""

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.auth.jwt import create_access_token, get_current_user
from backend.research_threads import MonthlyResearchQuotaExceeded
from backend.routers import research
from backend.safety.nvidia_client import (
    NvidiaSafetyClassification,
    NvidiaSafetyConfigurationError,
    NvidiaSafetyProviderError,
    NvidiaSafetyResponseError,
)
from backend.safety.policy import SafetyDecision, SafetyPolicyResult
from backend.tiers import TierName, get_tier_config


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
        self.start_inputs: list[dict[str, Any]] = []
        self.start_entered = asyncio.Event()
        self.start_release: asyncio.Event | None = None

    async def ainvoke(self, input_value, config=None):
        if hasattr(input_value, "resume"):
            self.resume_payloads.append(input_value.resume)
            if self.fail_resume:
                raise RuntimeError("controlled resume failure")
            self.interrupted = False
            return {"report": self.report}
        self.start_inputs.append(input_value)
        self.start_entered.set()
        if self.start_release is not None:
            await self.start_release.wait()
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
    create_calls: list[tuple[str, str, int | None]] = []
    quota_failure: dict[str, Exception | None] = {"exception": None}
    safe_classification = NvidiaSafetyClassification(
        user_safety="safe",
        raw_user_safety="safe",
        categories=(),
        raw_model_output='{"User Safety": "safe"}',
    )
    safety_client = AsyncMock(return_value=safe_classification)
    safety_policy = Mock(
        return_value=SafetyPolicyResult(decision=SafetyDecision.SAFE)
    )
    tier_lookup = AsyncMock(return_value=TierName.FREE)

    async def fake_create_thread(user_id, domain, monthly_limit):
        nonlocal next_thread
        if quota_failure["exception"] is not None:
            raise quota_failure["exception"]
        create_calls.append((str(user_id), domain, monthly_limit))
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

    quota_creator = AsyncMock(side_effect=fake_create_thread)
    monkeypatch.setattr(research, "create_thread_with_monthly_quota", quota_creator)
    monkeypatch.setattr(research, "get_thread", fake_get_thread)
    monkeypatch.setattr(research, "update_thread_status", fake_update_status)
    monkeypatch.setattr(research, "verify_thread_owner", fake_verify_owner)
    monkeypatch.setattr(research, "graph_context", fake_graph_context)
    monkeypatch.setattr(research, "classify_research_topic", safety_client)
    monkeypatch.setattr(research, "apply_safety_policy", safety_policy)
    monkeypatch.setattr(research, "get_user_tier", tier_lookup)
    monkeypatch.setattr(research, "_start_rate_limiter", research.ResearchStartRateLimiter())

    app = FastAPI()
    app.include_router(research.router)
    app.dependency_overrides[get_current_user] = lambda: "owner-1"
    return SimpleNamespace(
        app=app,
        threads=threads,
        updates=updates,
        graph=graph,
        create_calls=create_calls,
        quota_creator=quota_creator,
        quota_failure=quota_failure,
        safety_client=safety_client,
        safety_policy=safety_policy,
        tier_lookup=tier_lookup,
        safe_classification=safe_classification,
    )


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
    router_environment.safety_client.assert_awaited_once_with("Climate adaptation")
    router_environment.safety_policy.assert_called_once_with(
        "Climate adaptation", router_environment.safe_classification
    )
    router_environment.tier_lookup.assert_awaited_once_with("owner-1")
    assert router_environment.create_calls == [
        (
            "owner-1",
            "Climate adaptation",
            get_tier_config(TierName.FREE).monthly_research_runs,
        )
    ]
    assert router_environment.graph.start_inputs == [
        {
            "user_id": "owner-1",
            "tier": TierName.FREE,
            "domain": "Climate adaptation",
        }
    ]


@pytest.mark.parametrize("tier", [TierName.FREE, TierName.PRO, TierName.TEAM])
def test_start_passes_centralized_monthly_limit_for_tier(router_environment, tier):
    router_environment.tier_lookup.return_value = tier

    with _client(router_environment) as client:
        response = client.post("/research", json={"domain": "Tier quota test"})

    assert response.status_code == 201
    router_environment.quota_creator.assert_awaited_once_with(
        "owner-1",
        "Tier quota test",
        get_tier_config(tier).monthly_research_runs,
    )


@pytest.mark.asyncio
async def test_monthly_quota_rejection_returns_429_without_thread_or_background_task(
    router_environment,
):
    router_environment.quota_failure["exception"] = MonthlyResearchQuotaExceeded()
    background_tasks = BackgroundTasks()

    with pytest.raises(HTTPException) as exc_info:
        await research.start_research(
            research.ResearchStartRequest(domain="Quota exhausted"),
            background_tasks,
            "owner-1",
        )

    assert exc_info.value.status_code == 429
    assert exc_info.value.detail == {
        "code": "RESEARCH_MONTHLY_QUOTA_EXCEEDED",
        "message": "Your monthly research-run limit has been reached.",
    }
    assert router_environment.threads == {}
    assert router_environment.create_calls == []
    assert background_tasks.tasks == []
    assert router_environment.graph.start_inputs == []


@pytest.mark.asyncio
async def test_start_returns_before_initial_graph_and_exposes_real_status(
    router_environment,
):
    router_environment.graph.start_release = asyncio.Event()
    background_tasks = BackgroundTasks()

    started_at = time.perf_counter()
    response = await asyncio.wait_for(
        research.start_research(
            research.ResearchStartRequest(domain="Climate adaptation"),
            background_tasks,
            "owner-1",
        ),
        timeout=0.25,
    )
    elapsed = time.perf_counter() - started_at

    assert elapsed < 0.25
    assert router_environment.graph.start_entered.is_set() is False
    assert len(background_tasks.tasks) == 1
    thread = router_environment.threads[response.thread_id]
    assert thread.status == "running_agent2"

    running_status = await research.research_status(response.thread_id, "owner-1")
    assert running_status.model_dump() == {
        "status": "running_agent2",
        "detail": "Research is planning the protocol and screening papers.",
    }

    task_runner = asyncio.create_task(background_tasks())
    await asyncio.wait_for(router_environment.graph.start_entered.wait(), timeout=0.25)
    assert thread.status == "running_agent2"
    assert (response.thread_id, "paused_for_selection") not in router_environment.updates

    router_environment.graph.start_release.set()
    await asyncio.wait_for(task_runner, timeout=0.25)
    assert thread.status == "paused_for_selection"
    assert (response.thread_id, "paused_for_selection") in router_environment.updates


@pytest.mark.parametrize(
    ("decision", "code"),
    [
        (SafetyDecision.UNSAFE, "SAFETY_UNSAFE"),
        (SafetyDecision.UNCERTAIN, "SAFETY_NEEDS_CONTEXT"),
    ],
)
def test_safety_rejection_stops_before_thread_and_graph(
    router_environment, decision, code
):
    router_environment.safety_policy.return_value = SafetyPolicyResult(
        decision=decision,
        message="Safe user-facing safety message.",
    )

    with _client(router_environment) as client:
        response = client.post("/research", json={"domain": "Original topic"})

    assert response.status_code == 422
    assert response.json() == {
        "detail": {"code": code, "message": "Safe user-facing safety message."}
    }
    router_environment.safety_client.assert_awaited_once_with("Original topic")
    assert router_environment.create_calls == []
    assert router_environment.threads == {}
    assert router_environment.graph.start_inputs == []
    router_environment.tier_lookup.assert_not_awaited()
    router_environment.quota_creator.assert_not_awaited()


@pytest.mark.parametrize(
    "failure",
    [
        NvidiaSafetyProviderError("provider failed with secret test-api-key"),
        NvidiaSafetyConfigurationError("missing test-api-key"),
        NvidiaSafetyResponseError("malformed response containing test-api-key"),
    ],
)
def test_safety_service_failure_is_sanitized_and_fail_closed(
    router_environment, failure
):
    router_environment.safety_client.side_effect = failure

    with _client(router_environment) as client:
        response = client.post("/research", json={"domain": "Climate adaptation"})

    assert response.status_code == 503
    assert response.json() == {
        "detail": {
            "code": "SAFETY_UNAVAILABLE",
            "message": "The safety check is temporarily unavailable. Please try again later.",
        }
    }
    assert "test-api-key" not in response.text
    assert router_environment.create_calls == []
    assert router_environment.graph.start_inputs == []
    router_environment.tier_lookup.assert_not_awaited()
    router_environment.quota_creator.assert_not_awaited()
    router_environment.safety_policy.assert_not_called()


def test_unexpected_policy_result_fails_closed(router_environment):
    router_environment.safety_policy.return_value = SimpleNamespace(decision="unexpected")

    with _client(router_environment) as client:
        response = client.post("/research", json={"domain": "Climate adaptation"})

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "SAFETY_UNAVAILABLE"
    assert router_environment.create_calls == []
    assert router_environment.graph.start_inputs == []
    router_environment.tier_lookup.assert_not_awaited()
    router_environment.quota_creator.assert_not_awaited()


@pytest.mark.parametrize("domain", ["", "   ", "x" * 501])
def test_invalid_research_topic_is_rejected_before_safety(router_environment, domain):
    with _client(router_environment) as client:
        response = client.post("/research", json={"domain": domain})

    assert response.status_code == 422
    router_environment.safety_client.assert_not_awaited()
    assert router_environment.create_calls == []
    assert router_environment.graph.start_inputs == []


def test_authentication_occurs_before_safety_service(router_environment):
    router_environment.app.dependency_overrides.clear()

    with _client(router_environment) as client:
        response = client.post("/research", json={"domain": "Climate adaptation"})

    assert response.status_code == 401
    router_environment.safety_client.assert_not_awaited()
    assert router_environment.create_calls == []
    assert router_environment.graph.start_inputs == []
    router_environment.tier_lookup.assert_not_awaited()
    router_environment.quota_creator.assert_not_awaited()


def test_rate_limit_occurs_before_safety_service(router_environment, monkeypatch):
    limiter = AsyncMock()
    limiter.allow.return_value = False
    monkeypatch.setattr(research, "_start_rate_limiter", limiter)

    with _client(router_environment) as client:
        response = client.post("/research", json={"domain": "Climate adaptation"})

    assert response.status_code == 429
    limiter.allow.assert_awaited_once_with("owner-1")
    router_environment.safety_client.assert_not_awaited()
    assert router_environment.create_calls == []
    assert router_environment.graph.start_inputs == []
    router_environment.tier_lookup.assert_not_awaited()
    router_environment.quota_creator.assert_not_awaited()


def test_start_research_security_boundary_call_order(router_environment, monkeypatch):
    calls: list[str] = []

    async def authenticated_user():
        calls.append("authentication")
        return "owner-1"

    class OrderedLimiter:
        async def allow(self, user_id):
            calls.append("rate_limit")
            return True

    async def classify(topic):
        calls.append("safety_client")
        return router_environment.safe_classification

    def apply_policy(topic, classification):
        calls.append("safety_policy")
        return SafetyPolicyResult(decision=SafetyDecision.SAFE)

    async def resolve_tier(user_id):
        calls.append("get_user_tier")
        return TierName.FREE

    original_create_thread = research.create_thread_with_monthly_quota
    original_ainvoke = router_environment.graph.ainvoke

    async def create(user_id, domain, monthly_limit):
        calls.append("create_thread")
        return await original_create_thread(user_id, domain, monthly_limit)

    async def invoke(input_value, config=None):
        calls.append("graph")
        return await original_ainvoke(input_value, config=config)

    router_environment.app.dependency_overrides[get_current_user] = authenticated_user
    monkeypatch.setattr(research, "_start_rate_limiter", OrderedLimiter())
    monkeypatch.setattr(research, "classify_research_topic", classify)
    monkeypatch.setattr(research, "apply_safety_policy", apply_policy)
    monkeypatch.setattr(research, "get_user_tier", resolve_tier)
    monkeypatch.setattr(research, "create_thread_with_monthly_quota", create)
    monkeypatch.setattr(router_environment.graph, "ainvoke", invoke)

    with _client(router_environment) as client:
        response = client.post("/research", json={"domain": "Original topic"})

    assert response.status_code == 201
    assert calls == [
        "authentication",
        "rate_limit",
        "safety_client",
        "safety_policy",
        "get_user_tier",
        "create_thread",
        "graph",
    ]


def test_start_research_background_failure_marks_error_and_exposes_safe_status(
    router_environment, caplog
):
    router_environment.graph.fail_start = True

    with caplog.at_level(logging.ERROR, logger="nexora.research_router"):
        client = _client(router_environment)
        response = client.post("/research", json={"domain": "Climate adaptation"})
        thread_id = response.json()["thread_id"]
        status_response = client.get(f"/research/{thread_id}/status")
        client.close()

    assert response.status_code == 201
    assert status_response.status_code == 200
    assert status_response.json() == {
        "status": "error",
        "detail": "Research processing failed.",
    }
    assert "controlled start failure" not in response.text
    assert router_environment.threads[thread_id].status == "error"
    assert "Initial research graph run failed" in caplog.text


def test_missing_bearer_token_is_rejected(router_environment):
    router_environment.app.dependency_overrides.clear()

    with _client(router_environment) as client:
        response = client.post("/research", json={"domain": "Climate adaptation"})

    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"
    assert response.headers["www-authenticate"] == "Bearer"


def test_real_jwt_supplies_string_user_id_to_research_router(router_environment):
    router_environment.app.dependency_overrides.clear()
    token = create_access_token("jwt-owner")

    with _client(router_environment) as client:
        response = client.post(
            "/research",
            json={"domain": "Climate adaptation"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 201
    thread_id = response.json()["thread_id"]
    assert router_environment.threads[thread_id].user_id == "jwt-owner"
    router_environment.tier_lookup.assert_awaited_once_with("jwt-owner")
    assert router_environment.graph.start_inputs == [
        {
            "user_id": "jwt-owner",
            "tier": TierName.FREE,
            "domain": "Climate adaptation",
        }
    ]


def test_status_returns_safe_metadata_detail(router_environment):
    thread = _paused_thread(router_environment)

    with _client(router_environment) as client:
        response = client.get(f"/research/{thread.thread_id}/status")

    assert response.status_code == 200
    assert response.json() == {
        "status": "paused_for_selection",
        "detail": "Research is waiting for paper selection.",
    }
    router_environment.quota_creator.assert_not_awaited()


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
        "reason", "paper_url", "prerank_score", "relevance_percent", "has_usable_abstract",
    }
    router_environment.quota_creator.assert_not_awaited()


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
    router_environment.quota_creator.assert_not_awaited()


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
    router_environment.quota_creator.assert_not_awaited()


def test_done_thread_without_report_returns_safe_server_error(router_environment):
    thread = FakeThread("done-thread", "owner-1", "Test domain", "done")
    router_environment.threads[thread.thread_id] = thread
    router_environment.graph.interrupted = False
    router_environment.graph.report = None

    with _client(router_environment) as client:
        response = client.get(f"/research/{thread.thread_id}/report")

    assert response.status_code == 500
    assert response.json()["detail"] == "Research report is unavailable."


def test_report_pdf_requires_done_status(router_environment):
    thread = _paused_thread(router_environment)

    with _client(router_environment) as client:
        response = client.get(f"/research/{thread.thread_id}/report/pdf")

    assert response.status_code == 404


def test_report_pdf_returns_downloadable_pdf_when_done(router_environment):
    thread = FakeThread("done-thread", "owner-1", "Test domain", "done")
    router_environment.threads[thread.thread_id] = thread
    router_environment.graph.interrupted = False
    router_environment.graph.report = "# Completed report\n\nSome findings."

    with _client(router_environment) as client:
        response = client.get(f"/research/{thread.thread_id}/report/pdf")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "attachment" in response.headers["content-disposition"]
    assert thread.thread_id in response.headers["content-disposition"]
    assert response.content.startswith(b"%PDF")
    router_environment.quota_creator.assert_not_awaited()


def test_start_rate_limit_rejects_the_eleventh_request(router_environment):
    with _client(router_environment) as client:
        responses = [
            client.post("/research", json={"domain": f"Topic {number}"})
            for number in range(11)
        ]

    assert [response.status_code for response in responses[:10]] == [201] * 10
    assert responses[10].status_code == 429
    assert router_environment.safety_client.await_count == 10
