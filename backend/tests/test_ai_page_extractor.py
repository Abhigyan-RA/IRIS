"""Tests for reading prices out of a page with the model."""

from __future__ import annotations

import json

import pytest

from shadow_cpi.ai.gemini import GeminiError
from shadow_cpi.ai.page_extractor import (
    MAX_PAGE_CHARACTERS,
    GeminiPageExtractor,
    page_to_text,
)


class ScriptedModel:
    """A model whose replies each test writes itself."""

    def __init__(self, replies: list[str] | None = None, error: Exception | None = None) -> None:
        self.replies = list(replies or [])
        self.error = error
        self.calls: list[tuple[str, str]] = []

    async def generate_model(
        self,
        system_instruction: str,
        user_prompt: str,
        schema: type,
        temperature: float = 0.0,
    ) -> object:
        self.calls.append((system_instruction, user_prompt))
        if self.error is not None:
            raise self.error
        return schema.model_validate(json.loads(self.replies.pop(0)))


class TestPageToText:
    def test_removes_markup_and_keeps_the_words_a_reader_sees(self) -> None:
        text = page_to_text("<div><h1>Copper</h1><span>4.52</span></div>")

        assert "Copper" in text
        assert "4.52" in text
        assert "<div>" not in text

    def test_drops_scripts_and_styles_which_are_most_of_a_page(self) -> None:
        html = "<style>.a{color:red}</style><script>var x=1;</script><p>4.52</p>"

        text = page_to_text(html)

        assert "color:red" not in text
        assert "var x" not in text
        assert "4.52" in text

    def test_collapses_the_whitespace_a_page_is_padded_with(self) -> None:
        text = page_to_text("<p>Copper     price</p>")

        assert "Copper price" in text

    def test_truncates_a_very_long_page(self) -> None:
        text = page_to_text("<p>" + ("word " * 20_000) + "</p>")

        assert len(text) <= MAX_PAGE_CHARACTERS + 50

    def test_keeps_both_ends_of_a_long_page(self) -> None:
        """A quote sits at the top of a page; the newest row of a table sits at the end."""
        html = "<p>FIRST</p>" + ("<p>filler</p>" * 5_000) + "<p>LAST</p>"

        text = page_to_text(html)

        assert "FIRST" in text
        assert "LAST" in text

    def test_says_where_text_was_removed(self) -> None:
        html = "<p>FIRST</p>" + ("<p>filler</p>" * 5_000) + "<p>LAST</p>"

        assert "omitted" in page_to_text(html)

    def test_a_short_page_is_kept_whole_with_no_marker(self) -> None:
        text = page_to_text("<p>Copper 4.52</p>")

        assert "omitted" not in text

    def test_an_empty_page_yields_no_text(self) -> None:
        assert page_to_text("") == ""


class TestExtraction:
    @pytest.mark.asyncio
    async def test_returns_the_values_the_model_found(self) -> None:
        model = ScriptedModel(['{"rows": [{"price": 4.52, "change_pct": 1.8, "label": "Copper"}]}'])

        rows = await GeminiPageExtractor(model).extract(
            "<p>Copper 4.52 +1.8%</p>", "the current copper price", "Copper"
        )

        assert rows == [{"price": "4.52", "change_pct": "1.8", "label": "Copper", "as_of": None}]

    @pytest.mark.asyncio
    async def test_keeps_a_negative_value(self) -> None:
        """A commodity can trade below zero, and a fall is not an error."""
        model = ScriptedModel(['{"rows": [{"price": -37.63, "change_pct": -300.0}]}'])

        rows = await GeminiPageExtractor(model).extract("<p>-37.63</p>", "the price", "WTI")

        assert rows[0]["price"] == "-37.63"

    @pytest.mark.asyncio
    async def test_a_page_without_the_value_yields_nothing(self) -> None:
        """This is the signal that a page has changed, so it must not be an error."""
        model = ScriptedModel(['{"rows": []}'])

        rows = await GeminiPageExtractor(model).extract("<p>Maintenance</p>", "the price", "Copper")

        assert rows == []

    @pytest.mark.asyncio
    async def test_the_instruction_describes_meaning_and_never_position(self) -> None:
        model = ScriptedModel(['{"rows": []}'])

        await GeminiPageExtractor(model).extract("<p>x</p>", "the current copper price", "Copper")

        system, prompt = model.calls[0]
        assert "never by where they sit" in system
        assert "the current copper price" in prompt
        assert "Copper" in prompt

    @pytest.mark.asyncio
    async def test_repair_guidance_is_passed_on_when_a_first_attempt_failed(self) -> None:
        model = ScriptedModel(['{"rows": []}'])

        await GeminiPageExtractor(model).extract(
            "<p>x</p>",
            "the current copper price",
            "Copper",
            repair_instruction="the price now sits beside the word Last",
        )

        assert "beside the word Last" in model.calls[0][1]

    @pytest.mark.asyncio
    async def test_a_model_failure_yields_nothing_rather_than_raising(self) -> None:
        """One unreadable page must not abort a run that has other sources left."""
        model = ScriptedModel(error=GeminiError("model unavailable"))

        rows = await GeminiPageExtractor(model).extract("<p>4.52</p>", "the price", "Copper")

        assert rows == []

    @pytest.mark.asyncio
    async def test_an_empty_page_is_not_sent_to_the_model_at_all(self) -> None:
        model = ScriptedModel(['{"rows": []}'])

        rows = await GeminiPageExtractor(model).extract("", "the price", "Copper")

        assert rows == []
        assert model.calls == []

    @pytest.mark.asyncio
    async def test_a_row_with_no_price_is_passed_through_for_the_health_check_to_judge(
        self,
    ) -> None:
        model = ScriptedModel(['{"rows": [{"price": null, "change_pct": null}]}'])

        rows = await GeminiPageExtractor(model).extract("<p>x</p>", "the price", "Copper")

        assert rows == [{"price": None, "change_pct": None, "label": None, "as_of": None}]
