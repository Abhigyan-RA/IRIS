"""Contract tests for the copilot endpoint."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from shadow_cpi.ai.copilot import CopilotAnswer
from shadow_cpi.ai.gemini import GeminiQuotaExceededError
from shadow_cpi.api.app import create_app
from shadow_cpi.api.dependencies import ApiDependencies
from shadow_cpi.config import build_settings

BASE_ENV = {
    "GEMINI_API_KEY": "test-gemini-key",
    "BRIGHTDATA_API_KEY": "test-brightdata-key",
    "NEO4J_PASSWORD": "test-neo4j-password",
    "CRON_SECRET": "test-cron-secret",
}


class FakeCopilot:
    """Answers with whatever the test scripts."""

    def __init__(self, answer: CopilotAnswer | None = None, error: Exception | None = None) -> None:
        self.answer = answer or CopilotAnswer(
            answer="Copper is 4.52 USD per pound.",
            sources=["https://www.investing.com/commodities/copper"],
            data_as_of=datetime(2026, 8, 15, 12, 0, tzinfo=UTC),
        )
        self.error = error
        self.questions: list[str] = []

    async def ask(self, question: str) -> CopilotAnswer:
        self.questions.append(question)
        if self.error is not None:
            raise self.error
        return self.answer


def _client(copilot: FakeCopilot | None = None, **env: str) -> TestClient:
    app = create_app(
        build_settings({**BASE_ENV, **env}),
        dependencies=ApiDependencies(copilot=copilot),
    )
    return TestClient(app)


def test_a_question_gets_a_cited_answer() -> None:
    client = _client(FakeCopilot())

    body = client.post("/api/copilot/ask", json={"question": "what is copper doing"}).json()

    assert body["answer"] == "Copper is 4.52 USD per pound."
    assert body["sources"] == ["https://www.investing.com/commodities/copper"]
    assert body["data_as_of"].startswith("2026-08-15")


def test_the_question_reaches_the_copilot_unchanged() -> None:
    copilot = FakeCopilot()
    client = _client(copilot)

    client.post("/api/copilot/ask", json={"question": "  what is copper doing  "})

    assert copilot.questions == ["  what is copper doing  "]


def test_an_empty_question_is_refused() -> None:
    copilot = FakeCopilot()
    client = _client(copilot)

    response = client.post("/api/copilot/ask", json={"question": "   "})

    assert response.status_code == 422
    assert copilot.questions == []


def test_an_overlong_question_is_refused() -> None:
    copilot = FakeCopilot()
    client = _client(copilot)

    response = client.post("/api/copilot/ask", json={"question": "why " * 500})

    assert response.status_code == 422
    assert copilot.questions == []


def test_a_missing_question_field_is_refused() -> None:
    assert _client(FakeCopilot()).post("/api/copilot/ask", json={}).status_code == 422


def test_reaching_the_daily_model_cap_is_reported_as_unavailable() -> None:
    """A cost cap is a temporary condition, so it is reported as such."""
    client = _client(FakeCopilot(error=GeminiQuotaExceededError("cap reached")))

    response = client.post("/api/copilot/ask", json={"question": "what is copper doing"})

    assert response.status_code == 503
    assert "cap" in response.json()["detail"].lower()


def test_the_endpoint_reports_unavailability_when_no_copilot_is_configured() -> None:
    response = _client().post("/api/copilot/ask", json={"question": "what is copper doing"})

    assert response.status_code == 503


def test_the_copilot_has_its_own_stricter_rate_limit() -> None:
    """Each call costs money, so this endpoint is limited harder than the rest."""
    client = _client(FakeCopilot(), RATE_LIMIT_PER_MINUTE="60", COPILOT_RATE_LIMIT_PER_MINUTE="2")

    statuses = [
        client.post("/api/copilot/ask", json={"question": "what is copper doing"}).status_code
        for _ in range(3)
    ]

    assert statuses == [200, 200, 429]


def test_exhausting_the_copilot_limit_leaves_other_endpoints_usable() -> None:
    client = _client(FakeCopilot(), RATE_LIMIT_PER_MINUTE="60", COPILOT_RATE_LIMIT_PER_MINUTE="1")
    client.post("/api/copilot/ask", json={"question": "what is copper doing"})

    assert client.post("/api/copilot/ask", json={"question": "again"}).status_code == 429
    assert client.get("/health").status_code == 200


def test_an_answer_with_no_data_behind_it_is_still_a_successful_reply() -> None:
    client = _client(FakeCopilot(CopilotAnswer(answer="I do not have data for that.")))

    response = client.post("/api/copilot/ask", json={"question": "price of unobtainium"})

    assert response.status_code == 200
    assert response.json()["sources"] == []
    assert response.json()["data_as_of"] is None
