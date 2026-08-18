"""Request rate limiting.

Every public endpoint is limited per client address, and the endpoints that cost
money per call are limited harder. Without this, one client can exhaust the
database, the scraping quota, or the model budget for everyone else.

The counter is a fixed window: requests are counted per address per minute, and the
count resets when the minute rolls over. That is simple to reason about and cheap
to run. It is deliberately in-process, which is correct for a single instance; if
the service is ever run as several replicas, this is the piece to move to Redis so
the limit applies across all of them.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable, Mapping

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

WINDOW_SECONDS = 60.0

# Entries older than this are discarded, so an idle process does not accumulate one
# record per address that ever visited.
_PRUNE_AFTER_SECONDS = WINDOW_SECONDS * 5


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rejects a client that makes too many requests in a minute."""

    def __init__(
        self,
        app: Callable[..., Awaitable[None]],
        *,
        default_per_minute: int,
        path_limits: Mapping[str, int] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Create the middleware.

        Args:
            app: The application being wrapped.
            default_per_minute: Requests allowed per client per minute.
            path_limits: Stricter limits for particular path prefixes, such as the
                copilot endpoint, which spends money on every call.
            clock: Source of the current time. Injected so tests can control the
                window without sleeping.
        """
        super().__init__(app)
        self._default = default_per_minute
        self._path_limits = dict(path_limits or {})
        self._clock = clock
        # Key is (client address, limit bucket); value is (window start, count).
        self._counters: dict[tuple[str, str], tuple[float, int]] = {}

    def _limit_for(self, path: str) -> tuple[str, int]:
        """Return the bucket name and allowance that apply to a path.

        Args:
            path: Request path.

        Returns:
            The bucket the request counts against, and how many requests are
            allowed in it. Buckets are separate, so hammering the copilot endpoint
            cannot exhaust a client's allowance for reading prices.
        """
        for prefix, limit in self._path_limits.items():
            if path.startswith(prefix):
                return prefix, limit
        return "default", self._default

    def _register(self, key: tuple[str, str], now: float) -> int:
        """Count one request and return the running total for the window.

        Args:
            key: Client address and bucket.
            now: Current time.

        Returns:
            How many requests this client has made in the current window.
        """
        window_start, count = self._counters.get(key, (now, 0))
        if now - window_start >= WINDOW_SECONDS:
            window_start, count = now, 0
        count += 1
        self._counters[key] = (window_start, count)
        return count

    def _prune(self, now: float) -> None:
        """Discard windows that are long past.

        Args:
            now: Current time.
        """
        stale = [
            key
            for key, (window_start, _) in self._counters.items()
            if now - window_start > _PRUNE_AFTER_SECONDS
        ]
        for key in stale:
            del self._counters[key]

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Count the request, and reject it if the client is over its allowance.

        Args:
            request: The incoming request.
            call_next: The next handler in the chain.

        Returns:
            The downstream response, or a "too many requests" response carrying a
            ``Retry-After`` header so a well-behaved client knows when to return.
        """
        client = request.client.host if request.client else "unknown"
        bucket, limit = self._limit_for(request.url.path)
        now = self._clock()
        self._prune(now)

        count = self._register((client, bucket), now)
        if count > limit:
            window_start, _ = self._counters[(client, bucket)]
            retry_after = max(1, int(WINDOW_SECONDS - (now - window_start)))
            return JSONResponse(
                status_code=429,
                content={"detail": f"Rate limit exceeded: {limit} requests per minute"},
                headers={"Retry-After": str(retry_after)},
            )

        return await call_next(request)
