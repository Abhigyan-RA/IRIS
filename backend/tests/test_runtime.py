"""Tests for process-level runtime setup."""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from shadow_cpi.runtime import bootstrap, configure_event_loop, load_environment


@pytest.fixture
def restore_policy() -> Iterator[None]:
    """Put the original event loop policy back after a test changes it.

    Yields:
        None. The policy is restored on teardown.
    """
    original = asyncio.get_event_loop_policy()
    yield
    asyncio.set_event_loop_policy(original)


@pytest.fixture
def clean_environment() -> Iterator[None]:
    """Remove the variables these tests set, however the test ends.

    Yields:
        None. The variables are removed on teardown.
    """
    names = ("SHADOW_CPI_TEST_VALUE", "SHADOW_CPI_TEST_EXISTING")
    yield
    for name in names:
        os.environ.pop(name, None)


class TestLoadEnvironment:
    def test_reads_values_from_the_file(self, tmp_path: Path, clean_environment: None) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("SHADOW_CPI_TEST_VALUE=from-file\n", encoding="utf-8")

        assert load_environment(env_file) is True
        assert os.environ["SHADOW_CPI_TEST_VALUE"] == "from-file"

    def test_a_real_environment_variable_wins_over_the_file(
        self, tmp_path: Path, clean_environment: None
    ) -> None:
        """A deployment sets real variables; a stray file must not override them."""
        os.environ["SHADOW_CPI_TEST_EXISTING"] = "from-environment"
        env_file = tmp_path / ".env"
        env_file.write_text("SHADOW_CPI_TEST_EXISTING=from-file\n", encoding="utf-8")

        load_environment(env_file)

        assert os.environ["SHADOW_CPI_TEST_EXISTING"] == "from-environment"

    def test_a_missing_file_is_not_an_error(self, tmp_path: Path) -> None:
        assert load_environment(tmp_path / "nothing-here") is False

    def test_comments_and_blank_lines_are_ignored(
        self, tmp_path: Path, clean_environment: None
    ) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("# a comment\n\nSHADOW_CPI_TEST_VALUE=kept\n", encoding="utf-8")

        load_environment(env_file)

        assert os.environ["SHADOW_CPI_TEST_VALUE"] == "kept"


class TestConfigureEventLoop:
    def test_selects_a_loop_the_database_driver_can_use(self, restore_policy: None) -> None:
        """Without this, opening a connection pool times out with no explanation.

        Written as one test rather than two platform-specific ones, because a skipped
        test is not allowed to merge and a test that only runs on the author's machine
        is not evidence of anything.
        """
        before = type(asyncio.get_event_loop_policy())

        configure_event_loop()

        after = type(asyncio.get_event_loop_policy())
        if sys.platform == "win32":
            assert after.__name__ == "WindowsSelectorEventLoopPolicy"
        else:
            assert after is before

    def test_is_safe_to_call_more_than_once(self, restore_policy: None) -> None:
        configure_event_loop()
        configure_event_loop()

        assert asyncio.get_event_loop_policy() is not None


class TestBootstrap:
    def test_prepares_the_process_from_a_given_file(
        self, tmp_path: Path, clean_environment: None, restore_policy: None
    ) -> None:
        """Given a file explicitly, so a real developer's configuration is never read."""
        env_file = tmp_path / ".env"
        env_file.write_text("SHADOW_CPI_TEST_VALUE=bootstrapped\n", encoding="utf-8")

        bootstrap(env_file)

        assert os.environ["SHADOW_CPI_TEST_VALUE"] == "bootstrapped"
        assert asyncio.get_event_loop_policy() is not None

    def test_does_not_fail_when_there_is_no_file(
        self, tmp_path: Path, restore_policy: None
    ) -> None:
        bootstrap(tmp_path / "absent")

        assert asyncio.get_event_loop_policy() is not None
