"""Tests for the Gemini client wrapper."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from shadow_cpi.ai.gemini import (
    GeminiClient,
    GeminiError,
    GeminiQuotaExceededError,
    build_endpoint,
)


class FakeHttpClient:
    """Replays scripted replies and records every request."""

    def __init__(self, replies: list[object] | None = None, error: Exception | None = None) -> None:
        self.replies = list(replies or [])
        self.error = error
        self.posts: list[tuple[str, Mapping[str, object], Mapping[str, str]]] = []

    async def get_json(
        self,
        url: str,
        params: Mapping[str, str | int] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> object:
        raise AssertionError("the model is called with POST only")

    async def get_text(
        self,
        url: str,
        params: Mapping[str, str | int] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> str:
        raise AssertionError("the model is called with POST only")

    async def post_json(
        self,
        url: str,
        body: Mapping[str, object],
        headers: Mapping[str, str] | None = None,
    ) -> object:
        self.posts.append((url, dict(body), dict(headers or {})))
        if self.error is not None:
            raise self.error
        return self.replies.pop(0) if self.replies else None


def _reply(text: str) -> dict[str, Any]:
    return {"candidates": [{"content": {"parts": [{"text": text}]}}]}


def _client(
    http: FakeHttpClient,
    daily_call_cap: int = 100,
) -> GeminiClient:
    return GeminiClient(
        http=http,
        api_key="test-gemini-key",
        model="gemini-flash-latest",
        daily_call_cap=daily_call_cap,
    )


class Extracted(BaseModel):
    """Schema used to check structured replies."""

    entity_name: str
    price: float


class TestRequestShape:
    @pytest.mark.asyncio
    async def test_calls_the_configured_model(self) -> None:
        http = FakeHttpClient([_reply("hello")])

        await _client(http).generate_text("be brief", "say hello")

        assert http.posts[0][0] == build_endpoint("gemini-flash-latest")

    @pytest.mark.asyncio
    async def test_the_key_travels_in_a_header_not_the_url(self) -> None:
        """A key in a URL ends up in access logs and error reports."""
        http = FakeHttpClient([_reply("hello")])

        await _client(http).generate_text("be brief", "say hello")

        url, _, headers = http.posts[0]
        assert headers["x-goog-api-key"] == "test-gemini-key"
        assert "test-gemini-key" not in url

    @pytest.mark.asyncio
    async def test_instructions_and_question_are_sent_separately(self) -> None:
        http = FakeHttpClient([_reply("hello")])

        await _client(http).generate_text("you normalize data", "here is the payload")

        body = http.posts[0][1]
        assert "you normalize data" in str(body["system_instruction"])
        assert "here is the payload" in str(body["contents"])

    @pytest.mark.asyncio
    async def test_replies_are_deterministic_by_default(self) -> None:
        """Data work needs the same answer twice, not a creative one."""
        http = FakeHttpClient([_reply("hello")])

        await _client(http).generate_text("be brief", "say hello")

        config: Any = http.posts[0][1]["generationConfig"]
        assert config["temperature"] == 0.0


class TestTextReplies:
    @pytest.mark.asyncio
    async def test_returns_the_reply_text(self) -> None:
        http = FakeHttpClient([_reply("  copper is up  ")])

        answer = await _client(http).generate_text("be brief", "what happened")

        assert answer == "copper is up"

    @pytest.mark.asyncio
    async def test_a_reply_split_across_parts_is_joined(self) -> None:
        http = FakeHttpClient(
            [{"candidates": [{"content": {"parts": [{"text": "copper "}, {"text": "is up"}]}}]}]
        )

        answer = await _client(http).generate_text("be brief", "what happened")

        assert answer == "copper is up"

    @pytest.mark.asyncio
    async def test_an_empty_candidate_list_is_reported(self) -> None:
        http = FakeHttpClient([{"candidates": []}])

        with pytest.raises(GeminiError, match="no reply"):
            await _client(http).generate_text("be brief", "what happened")

    @pytest.mark.asyncio
    async def test_a_blocked_reply_is_reported_with_its_reason(self) -> None:
        http = FakeHttpClient([{"promptFeedback": {"blockReason": "SAFETY"}}])

        with pytest.raises(GeminiError, match="SAFETY"):
            await _client(http).generate_text("be brief", "what happened")

    @pytest.mark.asyncio
    async def test_a_transport_failure_is_reported_as_a_model_error(self) -> None:
        http = FakeHttpClient(error=RuntimeError("connection reset"))

        with pytest.raises(GeminiError):
            await _client(http).generate_text("be brief", "what happened")

    @pytest.mark.asyncio
    async def test_an_error_never_repeats_the_key(self) -> None:
        http = FakeHttpClient(error=RuntimeError("connection reset by test-gemini-key"))

        with pytest.raises(GeminiError) as error:
            await _client(http).generate_text("be brief", "what happened")

        assert "test-gemini-key" not in str(error.value)


class TestStructuredReplies:
    @pytest.mark.asyncio
    async def test_validates_the_reply_against_a_schema(self) -> None:
        http = FakeHttpClient([_reply('{"entity_name": "Copper", "price": 4.52}')])

        result = await _client(http).generate_model("normalize", "raw", Extracted)

        assert result.entity_name == "Copper"
        assert result.price == 4.52

    @pytest.mark.asyncio
    async def test_a_fenced_code_block_is_unwrapped(self) -> None:
        """Models wrap JSON in markdown fences even when asked not to."""
        fenced = '```json\n{"entity_name": "Copper", "price": 4.52}\n```'
        http = FakeHttpClient([_reply(fenced)])

        result = await _client(http).generate_model("normalize", "raw", Extracted)

        assert result.entity_name == "Copper"

    @pytest.mark.asyncio
    async def test_prose_around_the_json_is_ignored(self) -> None:
        chatty = 'Sure! Here you go:\n{"entity_name": "Copper", "price": 4.52}\nHope that helps.'
        http = FakeHttpClient([_reply(chatty)])

        result = await _client(http).generate_model("normalize", "raw", Extracted)

        assert result.price == 4.52

    @pytest.mark.asyncio
    async def test_a_reply_with_no_json_is_reported(self) -> None:
        http = FakeHttpClient([_reply("I could not find a price on that page")])

        with pytest.raises(GeminiError, match="JSON"):
            await _client(http).generate_model("normalize", "raw", Extracted)

    @pytest.mark.asyncio
    async def test_json_that_does_not_match_the_schema_is_rejected(self) -> None:
        """The model is not trusted to return the right shape; it is checked."""
        http = FakeHttpClient([_reply('{"entity_name": "Copper"}')])

        with pytest.raises(ValidationError):
            await _client(http).generate_model("normalize", "raw", Extracted)

    @pytest.mark.asyncio
    async def test_structured_replies_are_requested_as_json(self) -> None:
        http = FakeHttpClient([_reply('{"entity_name": "Copper", "price": 4.52}')])

        await _client(http).generate_model("normalize", "raw", Extracted)

        config: Any = http.posts[0][1]["generationConfig"]
        assert config["responseMimeType"] == "application/json"


class TestDailyCap:
    @pytest.mark.asyncio
    async def test_calls_within_the_cap_are_made(self) -> None:
        http = FakeHttpClient([_reply("one"), _reply("two")])
        client = _client(http, daily_call_cap=2)

        await client.generate_text("be brief", "first")
        await client.generate_text("be brief", "second")

        assert len(http.posts) == 2

    @pytest.mark.asyncio
    async def test_exceeding_the_cap_raises_rather_than_failing_silently(self) -> None:
        """A cost cap that quietly returns nothing would look like missing data."""
        http = FakeHttpClient([_reply("one")])
        client = _client(http, daily_call_cap=1)
        await client.generate_text("be brief", "first")

        with pytest.raises(GeminiQuotaExceededError, match="cap"):
            await client.generate_text("be brief", "second")

        assert len(http.posts) == 1

    @pytest.mark.asyncio
    async def test_remaining_calls_can_be_inspected(self) -> None:
        http = FakeHttpClient([_reply("one")])
        client = _client(http, daily_call_cap=3)

        await client.generate_text("be brief", "first")

        assert client.calls_remaining == 2

    @pytest.mark.asyncio
    async def test_the_allowance_resets_on_a_new_day(self) -> None:
        clock = {"day": "2026-08-15"}
        http = FakeHttpClient([_reply("one"), _reply("two")])
        client = GeminiClient(
            http=http,
            api_key="test-gemini-key",
            model="gemini-flash-latest",
            daily_call_cap=1,
            today=lambda: clock["day"],
        )

        await client.generate_text("be brief", "first")
        with pytest.raises(GeminiQuotaExceededError):
            await client.generate_text("be brief", "second")

        clock["day"] = "2026-08-16"
        await client.generate_text("be brief", "third")

        assert len(http.posts) == 2
        assert client.calls_remaining == 0
