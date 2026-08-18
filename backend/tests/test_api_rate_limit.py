"""Tests for request rate limiting."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from shadow_cpi.api.rate_limit import WINDOW_SECONDS, RateLimitMiddleware


class FakeClock:
    """A clock the test moves by hand, so no test ever sleeps."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _app(
    default_per_minute: int = 2,
    path_limits: dict[str, int] | None = None,
    clock: FakeClock | None = None,
) -> TestClient:
    app = FastAPI()

    @app.get("/cheap")
    async def cheap() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/api/copilot/ask")
    async def expensive() -> dict[str, bool]:
        return {"ok": True}

    app.add_middleware(
        RateLimitMiddleware,
        default_per_minute=default_per_minute,
        path_limits=path_limits,
        clock=clock or FakeClock(),
    )
    return TestClient(app)


def test_requests_within_the_allowance_are_served() -> None:
    client = _app(default_per_minute=2)

    assert [client.get("/cheap").status_code for _ in range(2)] == [200, 200]


def test_the_request_that_exceeds_the_allowance_is_refused() -> None:
    client = _app(default_per_minute=2)

    for _ in range(2):
        client.get("/cheap")

    assert client.get("/cheap").status_code == 429


def test_a_refusal_says_when_to_come_back() -> None:
    """A client that is told when to retry does not need to poll blindly."""
    client = _app(default_per_minute=1)
    client.get("/cheap")

    response = client.get("/cheap")

    assert 0 < int(response.headers["Retry-After"]) <= WINDOW_SECONDS


def test_a_refusal_explains_the_limit_without_leaking_anything_else() -> None:
    client = _app(default_per_minute=1)
    client.get("/cheap")

    body = client.get("/cheap").json()

    assert body == {"detail": "Rate limit exceeded: 1 requests per minute"}


def test_the_allowance_resets_when_the_window_rolls_over() -> None:
    clock = FakeClock()
    client = _app(default_per_minute=1, clock=clock)
    client.get("/cheap")
    assert client.get("/cheap").status_code == 429

    clock.advance(WINDOW_SECONDS + 1)

    assert client.get("/cheap").status_code == 200


def test_an_expensive_path_has_its_own_stricter_allowance() -> None:
    client = _app(default_per_minute=5, path_limits={"/api/copilot": 1})

    first = client.get("/api/copilot/ask").status_code
    second = client.get("/api/copilot/ask").status_code

    assert (first, second) == (200, 429)


def test_exhausting_the_expensive_path_does_not_block_the_cheap_one() -> None:
    """Buckets are separate, so one endpoint cannot lock a client out of the rest."""
    client = _app(default_per_minute=5, path_limits={"/api/copilot": 1})
    client.get("/api/copilot/ask")
    assert client.get("/api/copilot/ask").status_code == 429

    assert client.get("/cheap").status_code == 200


def test_old_windows_are_discarded_so_memory_does_not_grow_forever() -> None:
    clock = FakeClock()
    client = _app(default_per_minute=1, clock=clock)
    client.get("/cheap")
    middleware = next(
        item
        for item in client.app.user_middleware  # type: ignore[attr-defined]
        if item.cls is RateLimitMiddleware
    )
    assert middleware is not None

    clock.advance(WINDOW_SECONDS * 10)
    client.get("/cheap")

    assert client.get("/cheap").status_code == 429
