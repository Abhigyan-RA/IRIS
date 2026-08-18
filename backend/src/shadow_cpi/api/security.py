"""Security headers applied to every HTTP response.

Browsers only apply protections they are told about. These headers are the
standard set for a JSON API: they stop content-type guessing, block framing,
withhold the referrer, isolate the browsing context, and declare that the
response contains no scripts, styles, or embedded content of any kind.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# This API only ever returns JSON, so the strictest possible policy is also the
# correct one: nothing should ever be loaded or executed from a response here.
_CONTENT_SECURITY_POLICY = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"

_ONE_YEAR_IN_SECONDS = 31_536_000


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach a standard set of security headers to every response.

    HTTPS enforcement (``Strict-Transport-Security``) is only sent when the
    service runs outside local development. Sending it locally would make
    browsers refuse the plain-HTTP dev server, sometimes for months, because the
    instruction is cached per domain.
    """

    def __init__(self, app: Callable[..., Awaitable[None]], *, enforce_https: bool) -> None:
        """Initialise the middleware.

        Args:
            app: The application being wrapped.
            enforce_https: Whether to send the HTTPS-only instruction to browsers.
        """
        super().__init__(app)
        self._enforce_https = enforce_https

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Run the request, then add security headers to the response.

        Args:
            request: The incoming request.
            call_next: The next handler in the chain.

        Returns:
            The response, with security headers set.
        """
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
        response.headers["Content-Security-Policy"] = _CONTENT_SECURITY_POLICY
        response.headers["Cache-Control"] = "no-store"
        if self._enforce_https:
            response.headers["Strict-Transport-Security"] = (
                f"max-age={_ONE_YEAR_IN_SECONDS}; includeSubDomains"
            )
        # Do not advertise which server software is running: it hands attackers a
        # free hint about which vulnerabilities might apply.
        if "server" in response.headers:
            del response.headers["server"]
        return response
