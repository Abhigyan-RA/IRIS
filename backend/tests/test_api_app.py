"""Contract tests for the FastAPI application factory and its security posture."""

from __future__ import annotations

from fastapi.testclient import TestClient

from shadow_cpi.api.app import create_app
from shadow_cpi.config import Settings, build_settings

MINIMUM_ENV: dict[str, str] = {
    "GEMINI_API_KEY": "test-gemini-key",
    "BRIGHTDATA_API_KEY": "test-brightdata-key",
    "NEO4J_PASSWORD": "test-neo4j-password",
    "CRON_SECRET": "test-cron-secret",
}


def _settings(**overrides: str) -> Settings:
    return build_settings({**MINIMUM_ENV, **overrides})


def _client(**overrides: str) -> TestClient:
    return TestClient(create_app(_settings(**overrides)))


def test_health_endpoint_reports_service_state() -> None:
    response = _client().get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "environment": "local", "version": "0.1.0"}


def test_health_response_never_leaks_secrets() -> None:
    response = _client().get("/health")

    assert "test-gemini-key" not in response.text
    assert "test-cron-secret" not in response.text


def test_security_headers_are_set_on_every_response() -> None:
    headers = _client().get("/health").headers

    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert headers["referrer-policy"] == "no-referrer"
    assert headers["cross-origin-opener-policy"] == "same-origin"
    assert "default-src 'none'" in headers["content-security-policy"]
    assert "server" not in {key.lower() for key in headers}


def test_hsts_is_absent_locally_and_present_outside_local() -> None:
    local_headers = _client().get("/health").headers
    production_headers = (
        _client(
            APP_ENV="production",
            NEXT_PUBLIC_APP_URL="https://shadowcpi.example",
            NEXT_PUBLIC_API_URL="https://api.shadowcpi.example",
            CORS_ALLOWED_ORIGINS="https://shadowcpi.example",
        )
        .get("/health")
        .headers
    )

    assert "strict-transport-security" not in local_headers
    assert "max-age=" in production_headers["strict-transport-security"]


def test_configured_origin_is_allowed_by_cors() -> None:
    response = _client().get("/health", headers={"Origin": "http://localhost:3000"})

    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_unknown_origin_is_not_allowed_by_cors() -> None:
    response = _client().get("/health", headers={"Origin": "https://evil.example"})

    assert "access-control-allow-origin" not in response.headers


def test_unknown_route_returns_not_found() -> None:
    assert _client().get("/api/does-not-exist").status_code == 404


def test_requests_beyond_the_rate_limit_are_rejected() -> None:
    client = _client(RATE_LIMIT_PER_MINUTE="2", COPILOT_RATE_LIMIT_PER_MINUTE="1")

    statuses = [client.get("/health").status_code for _ in range(3)]

    assert statuses[:2] == [200, 200]
    assert statuses[2] == 429


def test_openapi_schema_is_served_for_contract_tests() -> None:
    schema = _client().get("/openapi.json").json()

    assert schema["info"]["title"] == "Shadow CPI API"
    assert "/health" in schema["paths"]
