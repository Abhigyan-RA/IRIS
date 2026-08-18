"""Tests for driving a Scraper Studio collector."""

from __future__ import annotations

from collections.abc import Mapping

import pytest

from shadow_cpi.ingestion.brightdata.studio import (
    MAX_HEAL_PROMPT_LENGTH,
    HealStatus,
    ScraperStudioClient,
    ScraperStudioError,
    first_value,
)

COLLECTOR = "c_mswnopw72dyj64c7s3"
PAGE = "https://www.investing.com/commodities/copper"

# The shape the live collector returns, kept verbatim so the mapping is tested against
# reality rather than against an idealised row.
LIVE_ROW: dict[str, object] = {
    "price": {"value": 6.719, "currency": "USD", "symbol": "$"},
    "price_change_percent": "(+1.65%)",
    "input": {"url": PAGE},
}


class ScriptedHttpClient:
    """Replays scripted replies and records every request."""

    def __init__(
        self,
        post_replies: list[object] | None = None,
        get_replies: list[object] | None = None,
        post_error: Exception | None = None,
        get_error: Exception | None = None,
    ) -> None:
        self.post_replies = list(post_replies or [])
        self.get_replies = list(get_replies or [])
        self.post_error = post_error
        self.get_error = get_error
        self.posts: list[tuple[str, Mapping[str, object], Mapping[str, str]]] = []
        self.gets: list[str] = []

    async def get_json(
        self,
        url: str,
        params: Mapping[str, str | int] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> object:
        self.gets.append(url)
        if self.get_error is not None:
            raise self.get_error
        return self.get_replies.pop(0) if self.get_replies else {}

    async def get_text(
        self,
        url: str,
        params: Mapping[str, str | int] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> str:
        raise AssertionError("collectors return JSON")

    async def post_json(
        self,
        url: str,
        body: Mapping[str, object],
        headers: Mapping[str, str] | None = None,
    ) -> object:
        self.posts.append((url, dict(body), dict(headers or {})))
        if self.post_error is not None:
            raise self.post_error
        return self.post_replies.pop(0) if self.post_replies else {}


async def _no_wait(_seconds: float) -> None:
    """Skip the wait between polls, so tests take no time."""
    return None


def _client(http: ScriptedHttpClient, max_polls: int = 5) -> ScraperStudioClient:
    return ScraperStudioClient(
        http=http, api_key="test-token", sleep=_no_wait, poll_seconds=0.0, max_polls=max_polls
    )


class TestRunningACollector:
    @pytest.mark.asyncio
    async def test_returns_the_rows_the_collector_produced(self) -> None:
        http = ScriptedHttpClient(post_replies=[{"response_id": "d2t1"}], get_replies=[[LIVE_ROW]])

        rows = await _client(http).run(COLLECTOR, PAGE)

        assert rows == [LIVE_ROW]

    @pytest.mark.asyncio
    async def test_names_the_collector_and_sends_one_object_not_a_list(self) -> None:
        """The realtime endpoint rejects a list with 400; only the batch one takes an array."""
        http = ScriptedHttpClient(post_replies=[{"response_id": "d2t1"}], get_replies=[[LIVE_ROW]])

        await _client(http).run(COLLECTOR, PAGE)

        url, body, headers = http.posts[0]
        assert f"collector={COLLECTOR}" in url
        assert body == {"url": PAGE}
        assert headers["Authorization"] == "Bearer test-token"

    @pytest.mark.asyncio
    async def test_waits_while_the_run_is_still_working(self) -> None:
        """The endpoint signals progress by returning an object instead of an array."""
        http = ScriptedHttpClient(
            post_replies=[{"response_id": "d2t1"}],
            get_replies=[{"status": "running"}, {"status": "running"}, [LIVE_ROW]],
        )

        rows = await _client(http).run(COLLECTOR, PAGE)

        assert rows == [LIVE_ROW]
        assert len(http.gets) == 3

    @pytest.mark.asyncio
    async def test_a_finished_run_with_no_rows_returns_an_empty_list(self) -> None:
        """This is the signal that the page changed, so it must not be an error."""
        http = ScriptedHttpClient(post_replies=[{"response_id": "d2t1"}], get_replies=[[]])

        assert await _client(http).run(COLLECTOR, PAGE) == []

    @pytest.mark.asyncio
    async def test_a_run_that_never_finishes_is_reported(self) -> None:
        http = ScriptedHttpClient(
            post_replies=[{"response_id": "d2t1"}],
            get_replies=[{"status": "running"}] * 10,
        )

        with pytest.raises(ScraperStudioError, match="did not finish"):
            await _client(http, max_polls=3).run(COLLECTOR, PAGE)

    @pytest.mark.asyncio
    async def test_a_transient_polling_failure_is_retried_rather_than_fatal(self) -> None:
        http = ScriptedHttpClient(
            post_replies=[{"response_id": "d2t1"}], get_error=RuntimeError("502")
        )

        with pytest.raises(ScraperStudioError, match="did not finish"):
            await _client(http, max_polls=2).run(COLLECTOR, PAGE)

        assert len(http.gets) == 2

    @pytest.mark.asyncio
    async def test_a_run_that_cannot_start_is_reported(self) -> None:
        http = ScriptedHttpClient(post_error=RuntimeError("returned status 404"))

        with pytest.raises(ScraperStudioError, match=COLLECTOR):
            await _client(http).run(COLLECTOR, PAGE)

    @pytest.mark.asyncio
    async def test_a_reply_without_a_run_identifier_is_reported(self) -> None:
        http = ScriptedHttpClient(post_replies=[{"unexpected": True}])

        with pytest.raises(ScraperStudioError, match="no run identifier"):
            await _client(http).run(COLLECTOR, PAGE)

    @pytest.mark.asyncio
    async def test_the_token_never_appears_in_a_url(self) -> None:
        http = ScriptedHttpClient(post_replies=[{"response_id": "d2t1"}], get_replies=[[LIVE_ROW]])

        await _client(http).run(COLLECTOR, PAGE)

        assert all("test-token" not in url for url, _, _ in http.posts)
        assert all("test-token" not in url for url in http.gets)


class TestRepairingACollector:
    @pytest.mark.asyncio
    async def test_a_drafted_repair_is_reported_as_awaiting_approval(self) -> None:
        http = ScriptedHttpClient(post_replies=[{"status": "pending_answer"}])

        status = await _client(http).heal(COLLECTOR, "the price field returns null")

        assert status is HealStatus.AWAITING_APPROVAL

    @pytest.mark.asyncio
    async def test_the_description_of_what_broke_is_what_gets_sent(self) -> None:
        http = ScriptedHttpClient(post_replies=[{"status": "pending_answer"}])

        await _client(http).heal(COLLECTOR, "the price field returns null since the redesign")

        url, body, _ = http.posts[0]
        assert COLLECTOR in url
        assert url.endswith("/refactor_template")
        assert body["prompt"] == "the price field returns null since the redesign"

    @pytest.mark.asyncio
    async def test_an_overlong_description_is_trimmed_to_the_documented_limit(self) -> None:
        http = ScriptedHttpClient(post_replies=[{"status": "pending_answer"}])

        await _client(http).heal(COLLECTOR, "x" * 5_000)

        assert len(str(http.posts[0][1]["prompt"])) == MAX_HEAL_PROMPT_LENGTH

    @pytest.mark.asyncio
    async def test_a_repair_applied_immediately_is_reported_as_done(self) -> None:
        http = ScriptedHttpClient(post_replies=[{"status": "done"}])

        assert await _client(http).heal(COLLECTOR, "fix the price") is HealStatus.DONE

    @pytest.mark.asyncio
    async def test_an_unrecognised_status_counts_as_a_failure(self) -> None:
        """Acting on a status we do not understand is worse than stopping."""
        http = ScriptedHttpClient(post_replies=[{"status": "who knows"}])

        assert await _client(http).heal(COLLECTOR, "fix the price") is HealStatus.FAILED

    @pytest.mark.asyncio
    async def test_progress_can_be_checked_separately(self) -> None:
        http = ScriptedHttpClient(get_replies=[{"status": "pending_answer"}])

        status = await _client(http).heal_progress(COLLECTOR)

        assert status is HealStatus.AWAITING_APPROVAL
        assert http.gets[0].endswith("/refactor_template/progress")

    @pytest.mark.asyncio
    async def test_approving_keeps_the_same_collector_and_saves_the_change(self) -> None:
        """The handle must not change, or every schedule pointing at it would break."""
        http = ScriptedHttpClient(post_replies=[None])

        await _client(http).approve_heal(COLLECTOR)

        url, body, _ = http.posts[0]
        assert COLLECTOR in url
        assert url.endswith("/resume_automation_job")
        assert body == {"message": True, "auto_save": True}

    @pytest.mark.asyncio
    async def test_rejecting_leaves_the_collector_unchanged(self) -> None:
        http = ScriptedHttpClient(post_replies=[None])

        await _client(http).approve_heal(COLLECTOR, accept=False)

        assert http.posts[0][1] == {"message": False, "auto_save": False}

    @pytest.mark.asyncio
    async def test_a_failure_to_record_the_decision_is_reported(self) -> None:
        http = ScriptedHttpClient(post_error=RuntimeError("503"))

        with pytest.raises(ScraperStudioError, match="approve"):
            await _client(http).approve_heal(COLLECTOR)


class TestReadingValuesFromARow:
    def test_reads_a_nested_value_by_path(self) -> None:
        """A generated collector nests values, so the mapping has to describe where."""
        assert first_value(LIVE_ROW, ("price.value",)) == 6.719

    def test_tries_paths_in_order_until_one_exists(self) -> None:
        assert first_value(LIVE_ROW, ("last", "price.value")) == 6.719

    def test_reads_a_top_level_value(self) -> None:
        assert first_value(LIVE_ROW, ("price_change_percent",)) == "(+1.65%)"

    def test_returns_nothing_when_no_path_matches(self) -> None:
        assert first_value(LIVE_ROW, ("volume", "open_interest")) is None

    def test_a_path_through_a_non_mapping_does_not_fail(self) -> None:
        assert first_value(LIVE_ROW, ("price_change_percent.value",)) is None
