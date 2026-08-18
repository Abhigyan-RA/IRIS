"""The health endpoint, used by container orchestrators and uptime monitors."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from shadow_cpi import __version__
from shadow_cpi.config import Settings


class HealthResponse(BaseModel):
    """Body returned by the health endpoint.

    Attributes:
        status: Always ``ok``. If the process cannot serve requests, the caller
            gets a connection error or a 5xx instead of this body.
        environment: Which environment this process believes it is running in,
            which makes it obvious when a deploy targeted the wrong place.
        version: Version of the running backend, useful for confirming that a
            deploy actually rolled out.
    """

    status: str = Field(description="Literal 'ok' when the service is live")
    environment: str = Field(description="local, staging, or production")
    version: str = Field(description="Backend package version")


def build_health_router(settings: Settings) -> APIRouter:
    """Create the health router.

    The response deliberately contains only harmless metadata. Health endpoints
    are usually reachable without authentication, so they must never expose
    configuration details, credentials, or internal hostnames.

    Args:
        settings: Active application settings.

    Returns:
        A router exposing ``GET /health``.
    """
    router = APIRouter(tags=["system"])

    @router.get("/health", response_model=HealthResponse, summary="Service liveness")
    async def read_health() -> HealthResponse:
        """Report that the service is alive.

        Returns:
            The health payload.
        """
        return HealthResponse(
            status="ok",
            environment=settings.app_env,
            version=__version__,
        )

    return router
