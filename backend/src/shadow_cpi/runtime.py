"""Process-level setup that must happen before anything else runs.

Two things belong here, and both have to happen before the first database call.

**Loading the environment file.** Configuration is read from the environment, and a
developer's values live in a ``.env`` file at the repository root. Something has to put
them into the environment, and it has to be an entry point rather than a library:
importing a module should never silently rewrite the environment of whatever imported
it. Real environment variables always win, so a deployment that sets them properly is
never overridden by a file left behind on disk.

**Choosing an event loop.** Python on Windows defaults to a loop the PostgreSQL driver
cannot use in async mode. Connections in a pool then never open, and the failure
presents as a timeout that says nothing about the cause. Selecting a compatible loop
first avoids an hour of confused debugging.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

# runtime.py sits at backend/src/shadow_cpi/, so the repository root is four levels up.
_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def load_environment(dotenv_path: Path | None = None) -> bool:
    """Load variables from a ``.env`` file into the environment.

    Args:
        dotenv_path: File to read. Defaults to ``.env`` at the repository root.

    Returns:
        True when a file was found and read, False when there was none. A missing file
        is normal: in a deployment the variables come from the environment itself.
    """
    path = dotenv_path or (_REPOSITORY_ROOT / ".env")
    if not path.is_file():
        return False
    # override=False: a value already set in the environment is authoritative.
    load_dotenv(path, override=False)
    return True


def configure_event_loop() -> None:
    """Select an event loop the database driver can use.

    On Windows this switches to the selector-based loop. Everywhere else the default
    loop is already suitable and nothing changes.
    """
    if sys.platform != "win32":
        return

    policy = getattr(asyncio, "WindowsSelectorEventLoopPolicy", None)
    if policy is not None:
        asyncio.set_event_loop_policy(policy())


def bootstrap(dotenv_path: Path | None = None) -> None:
    """Prepare the process: load the environment file, then choose an event loop.

    Every entry point calls this as its first action.

    Args:
        dotenv_path: File to read configuration from. Defaults to ``.env`` at the
            repository root. Tests pass a path of their own so that a developer's real
            configuration never leaks into a test run.
    """
    load_environment(dotenv_path)
    configure_event_loop()
