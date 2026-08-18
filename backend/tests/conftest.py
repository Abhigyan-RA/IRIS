"""Shared pytest configuration for the backend test suite."""

from __future__ import annotations

import pytest
from _pytest.config import Config
from _pytest.reports import TestReport
from _pytest.terminal import TerminalReporter


def pytest_terminal_summary(
    terminalreporter: TerminalReporter,
    exitstatus: int,
    config: Config,
) -> None:
    """Fail the whole run if any test was skipped.

    A skipped test is easy to add "temporarily" and easy to forget, and it hides
    a gap in coverage behind a green build. Turning skips into failures forces
    the decision to be explicit: either fix the test or delete it.

    Args:
        terminalreporter: Reporter holding all test results.
        exitstatus: Exit status pytest computed before this hook ran.
        config: Active pytest configuration.
    """
    skipped: list[TestReport] = terminalreporter.stats.get("skipped", [])
    if skipped:
        names = ", ".join(report.nodeid for report in skipped)
        pytest.exit(f"Skipped tests are not allowed: {names}", returncode=1)
