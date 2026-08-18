"""Entry point that starts the API server.

Two equivalent ways to run it:

    python -m shadow_cpi.api.main
    uvicorn shadow_cpi.api.main:app --reload

The server opens its database connections on startup and closes them on shutdown.
If the databases are unreachable, it still starts and serves the health endpoint,
reporting each data endpoint as unavailable rather than refusing to boot: a
diagnosable service is more useful than one that will not start.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from shadow_cpi.api.app import create_app
from shadow_cpi.api.dependencies import ApiDependencies
from shadow_cpi.config import get_settings
from shadow_cpi.runtime import bootstrap
from shadow_cpi.wiring import open_dependencies

# Done before the application is built, so configuration from the environment file is
# present and the event loop is one the database driver can use.
bootstrap()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:  # pragma: no cover - needs databases
    """Open database connections for the life of the application.

    Args:
        app: The running application.

    Yields:
        Nothing. The dependency container is attached to the application while the
        block is active.
    """
    settings = get_settings()
    try:
        async with open_dependencies(settings) as dependencies:
            app.state.dependencies = dependencies
            yield
    except Exception as error:
        sys.stderr.write(f"Starting without data stores: {type(error).__name__}\n")
        app.state.dependencies = ApiDependencies()
        yield


app = create_app()
app.router.lifespan_context = lifespan


def run() -> None:  # pragma: no cover - starts a server
    """Start the server on the configured port.

    The server runs on a loop this process creates, rather than one the server library
    creates for us. That matters on Windows: the loop chosen there by default cannot be
    used by the PostgreSQL driver, so every database call would fail with a connection
    error that says nothing about the real cause.

    Automatic reload is not wired in for the same reason, since it hands loop creation
    back to the library. During development, restart this command, or use
    ``uvicorn shadow_cpi.api.main:app --reload`` on a platform whose default loop is
    already compatible.
    """
    bootstrap()
    settings = get_settings()
    config = uvicorn.Config(
        app=app,
        host="127.0.0.1",
        port=settings.api_port,
        log_level=settings.log_level,
        loop="asyncio",
    )
    asyncio.run(uvicorn.Server(config).serve())


if __name__ == "__main__":
    run()
