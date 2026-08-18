"""Builds the HTTP application.

The app is created by a function rather than defined once at import time. That
means tests can create a fresh app with whatever configuration they need, and
two apps in the same process never share state such as rate-limit counters.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from shadow_cpi import __version__
from shadow_cpi.api.dependencies import ApiDependencies
from shadow_cpi.api.rate_limit import RateLimitMiddleware
from shadow_cpi.api.routes import copilot, graph, institutional, pipeline, prices
from shadow_cpi.api.routes.health import build_health_router
from shadow_cpi.api.security import SecurityHeadersMiddleware
from shadow_cpi.config import Settings, get_settings

# The copilot endpoint calls a paid model on every request, so it counts against
# its own, much smaller allowance.
COPILOT_PATH_PREFIX = "/api/copilot"


def create_app(
    settings: Settings | None = None,
    dependencies: ApiDependencies | None = None,
) -> FastAPI:
    """Create the API application with security, CORS, and rate limiting wired up.

    Args:
        settings: Configuration to use. Defaults to the shared process settings.
        dependencies: Data stores the routes read from. Defaults to none
            configured, in which case data endpoints report that they are
            unavailable instead of failing at startup.

    Returns:
        A ready-to-serve application instance.

    Example:
        >>> from shadow_cpi.api.app import create_app
        >>> app = create_app()  # doctest: +SKIP
    """
    resolved = settings or get_settings()

    app = FastAPI(
        title="Shadow CPI API",
        version=__version__,
        description="Daily commodity, freight, and institutional-holdings intelligence",
    )
    app.state.settings = resolved
    app.state.dependencies = dependencies or ApiDependencies()

    # Middleware runs in reverse order of registration, so CORS is added last and
    # therefore runs first: browser preflight requests are answered before any
    # other work happens. Rate limiting sits innermost so that a rejected request
    # still carries the security headers added by the layer above it.
    app.add_middleware(
        RateLimitMiddleware,
        default_per_minute=resolved.rate_limit_per_minute,
        path_limits={COPILOT_PATH_PREFIX: resolved.copilot_rate_limit_per_minute},
    )
    app.add_middleware(SecurityHeadersMiddleware, enforce_https=resolved.app_env != "local")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(resolved.cors_allowed_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    )

    app.include_router(build_health_router(resolved))
    app.include_router(prices.router)
    app.include_router(institutional.router)
    app.include_router(graph.router)
    app.include_router(pipeline.router)
    app.include_router(copilot.router)
    return app
