"""Tests for the model-backed services: normalizing, repairing, explaining, narrating."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from shadow_cpi.ai.explainer import GeminiRippleExplainer
from shadow_cpi.ai.gemini import GeminiError
from shadow_cpi.ai.instruction_drafter import GeminiInstructionDrafter
from shadow_cpi.ai.narrator import GeminiFeedNarrator
from shadow_cpi.ai.normalizer import GeminiPriceNormalizer
from shadow_cpi.db.neo4j.repository import RippleLink
from shadow_cpi.ingestion.brightdata.collectors import SCRAPED_SOURCES
from shadow_cpi.shared import IngestionMethod, PipelineEventType, PipelineHealthEvent, Sector

COPPER_SOURCE = SCRAPED_SOURCES["lme_copper_scraper"]
NOW = datetime(2026, 8, 15, 3, 0, tzinfo=UTC)


class ScriptedModel:
    """A model whose replies each test writes itself."""

    def __init__(self, replies: list[str] | None = None, error: Exception | None = None) -> None:
        self.replies = list(replies or [])
        self.error = error
        self.text_calls: list[tuple[str, str]] = []
        self.model_calls: list[tuple[str, str]] = []

    async def generate_text(
        self,
        system_instruction: str,
        user_prompt: str,
        temperature: float = 0.0,
    ) -> str:
        self.text_calls.append((system_instruction, user_prompt))
        if self.error is not None:
            raise self.error
        return self.replies.pop(0) if self.replies else ""

    async def generate_model(
        self,
        system_instruction: str,
        user_prompt: str,
        schema: type,
        temperature: float = 0.0,
    ) -> object:
        self.model_calls.append((system_instruction, user_prompt))
        if self.error is not None:
            raise self.error
        import json

        return schema.model_validate(json.loads(self.replies.pop(0)))


class TestPriceNormalizer:
    @pytest.mark.asyncio
    async def test_turns_a_messy_payload_into_a_price_record(self) -> None:
        model = ScriptedModel(
            [
                '{"entity_name": "Copper", "price": 4.52, "currency": "USD", '
                '"unit": "lb", "pct_change_1d": 1.8}'
            ]
        )
        normalizer = GeminiPriceNormalizer(model)

        price = await normalizer.normalize(
            raw_payload={"Price:": "$4.52", "Chg%": "+1.8%"},
            source=COPPER_SOURCE,
            observed_at=NOW,
        )

        assert price is not None
        assert price.entity_name == "Copper"
        assert price.price == Decimal("4.52")
        assert price.pct_change_1d == Decimal("1.8")
        assert price.sector is Sector.METALS

    @pytest.mark.asyncio
    async def test_the_result_keeps_the_source_it_came_from(self) -> None:
        model = ScriptedModel(
            ['{"entity_name": "Copper", "price": 4.52, "currency": "USD", "unit": "lb"}']
        )

        price = await GeminiPriceNormalizer(model).normalize(
            raw_payload={"Price:": "$4.52"}, source=COPPER_SOURCE, observed_at=NOW
        )

        assert price is not None
        assert price.source_url == COPPER_SOURCE.url
        assert price.source_name == COPPER_SOURCE.source_name
        assert price.ingestion_method is IngestionMethod.BRIGHTDATA_SCRAPE

    @pytest.mark.asyncio
    async def test_a_negative_price_survives_normalization(self) -> None:
        """Crude has traded below zero; treating that as an error would lose real data."""
        model = ScriptedModel(
            ['{"entity_name": "Copper", "price": -37.63, "currency": "USD", "unit": "lb"}']
        )

        price = await GeminiPriceNormalizer(model).normalize(
            raw_payload={"Price:": "-37.63"}, source=COPPER_SOURCE, observed_at=NOW
        )

        assert price is not None
        assert price.price == Decimal("-37.63")

    @pytest.mark.asyncio
    async def test_the_expected_entity_name_is_given_to_the_model(self) -> None:
        model = ScriptedModel(
            ['{"entity_name": "Copper", "price": 4.52, "currency": "USD", "unit": "lb"}']
        )

        await GeminiPriceNormalizer(model).normalize(
            raw_payload={"Price:": "$4.52"}, source=COPPER_SOURCE, observed_at=NOW
        )

        assert "Copper" in model.model_calls[0][1]

    @pytest.mark.asyncio
    async def test_a_reply_with_no_price_yields_nothing(self) -> None:
        model = ScriptedModel(
            ['{"entity_name": "Copper", "price": null, "currency": "USD", "unit": "lb"}']
        )

        price = await GeminiPriceNormalizer(model).normalize(
            raw_payload={"Price:": "n/a"}, source=COPPER_SOURCE, observed_at=NOW
        )

        assert price is None

    @pytest.mark.asyncio
    async def test_a_model_failure_yields_nothing_rather_than_raising(self) -> None:
        """One unusable payload must not abort a run that has other sources to collect."""
        model = ScriptedModel(error=GeminiError("model unavailable"))

        price = await GeminiPriceNormalizer(model).normalize(
            raw_payload={"Price:": "$4.52"}, source=COPPER_SOURCE, observed_at=NOW
        )

        assert price is None

    @pytest.mark.asyncio
    async def test_an_invalid_currency_from_the_model_is_rejected(self) -> None:
        model = ScriptedModel(
            ['{"entity_name": "Copper", "price": 4.52, "currency": "dollars", "unit": "lb"}']
        )

        price = await GeminiPriceNormalizer(model).normalize(
            raw_payload={"Price:": "$4.52"}, source=COPPER_SOURCE, observed_at=NOW
        )

        assert price is None


class TestInstructionDrafter:
    @pytest.mark.asyncio
    async def test_uses_the_model_reply_as_the_repair_instruction(self) -> None:
        model = ScriptedModel(["Find the current copper price shown near the top of the page."])

        instruction = await GeminiInstructionDrafter(model).draft(
            collector_id="lme_copper_scraper",
            missing_fields=("price",),
            reason="no rows returned",
        )

        assert instruction == "Find the current copper price shown near the top of the page."

    @pytest.mark.asyncio
    async def test_the_model_is_told_which_fields_stopped_arriving(self) -> None:
        model = ScriptedModel(["Find the current price."])

        await GeminiInstructionDrafter(model).draft(
            collector_id="lme_copper_scraper",
            missing_fields=("price", "change_pct"),
            reason="rows are missing required fields",
        )

        prompt = model.text_calls[0][1]
        assert "price" in prompt
        assert "change_pct" in prompt

    @pytest.mark.asyncio
    async def test_an_instruction_naming_markup_is_refused(self) -> None:
        """A selector-based instruction would break again at the next redesign."""
        model = ScriptedModel(["Take the third td inside table.price-table"])

        instruction = await GeminiInstructionDrafter(model).draft(
            collector_id="lme_copper_scraper",
            missing_fields=("price",),
            reason="no rows returned",
        )

        assert "td" not in instruction
        assert "price" in instruction

    @pytest.mark.asyncio
    async def test_an_overlong_instruction_falls_back(self) -> None:
        model = ScriptedModel(["word " * 200])

        instruction = await GeminiInstructionDrafter(model).draft(
            collector_id="lme_copper_scraper",
            missing_fields=("price",),
            reason="no rows returned",
        )

        assert len(instruction) <= 300

    @pytest.mark.asyncio
    async def test_a_model_failure_falls_back_to_the_written_instruction(self) -> None:
        """The repair path must work when the model is unavailable."""
        model = ScriptedModel(error=GeminiError("model unavailable"))

        instruction = await GeminiInstructionDrafter(model).draft(
            collector_id="lme_copper_scraper",
            missing_fields=("price",),
            reason="no rows returned",
        )

        assert "price" in instruction
        assert instruction


class TestRippleExplainer:
    @pytest.mark.asyncio
    async def test_returns_a_plain_language_explanation(self) -> None:
        model = ScriptedModel(
            ["Copper feeds electric vehicle manufacturing, so a rise raises battery costs."]
        )

        explanation = await GeminiRippleExplainer(model).explain(
            commodity="Copper",
            price_summary="up 8 percent this week",
            links=[
                RippleLink("Copper", "REFINED_INTO", "Stator Coil", "Component", None),
                RippleLink(
                    "Stator Coil", "REQUIRED_FOR", "EV Battery Manufacturing", "Industry", 0.18
                ),
            ],
        )

        assert explanation is not None
        assert "electric vehicle" in explanation

    @pytest.mark.asyncio
    async def test_the_relationships_are_given_to_the_model(self) -> None:
        model = ScriptedModel(["Copper feeds electric vehicle manufacturing."])

        await GeminiRippleExplainer(model).explain(
            commodity="Copper",
            price_summary="up 8 percent",
            links=[
                RippleLink(
                    "Copper", "IMPACTS_COST_OF", "EV Battery Manufacturing", "Industry", 0.18
                )
            ],
        )

        prompt = model.text_calls[0][1]
        assert "EV Battery Manufacturing" in prompt
        assert "IMPACTS_COST_OF" in prompt

    @pytest.mark.asyncio
    async def test_nothing_is_explained_when_nothing_is_mapped(self) -> None:
        """With no relationships there is nothing to ground an explanation in."""
        model = ScriptedModel(["This should never be used."])

        explanation = await GeminiRippleExplainer(model).explain(
            commodity="Unobtainium", price_summary="up 8 percent", links=[]
        )

        assert explanation is None
        assert model.text_calls == []

    @pytest.mark.asyncio
    async def test_a_model_failure_leaves_the_explanation_absent(self) -> None:
        model = ScriptedModel(error=GeminiError("model unavailable"))

        explanation = await GeminiRippleExplainer(model).explain(
            commodity="Copper",
            price_summary="up 8 percent",
            links=[RippleLink("Copper", "REQUIRED_FOR", "Construction", "Industry", 0.24)],
        )

        assert explanation is None


class TestFeedNarrator:
    @staticmethod
    def _events() -> list[PipelineHealthEvent]:
        return [
            PipelineHealthEvent(
                scraper_id="whalewisdom_13f_scraper",
                source_name="whalewisdom.com",
                event_type=PipelineEventType.DOM_SHIFT_DETECTED,
                message="[WARNING] layout changed",
                occurred_at=NOW,
            ),
            PipelineHealthEvent(
                scraper_id="whalewisdom_13f_scraper",
                source_name="whalewisdom.com",
                event_type=PipelineEventType.SELF_HEAL_RESOLVED,
                message="[RESOLVED] collection resumed",
                occurred_at=NOW,
            ),
        ]

    @pytest.mark.asyncio
    async def test_returns_a_single_narrative_line(self) -> None:
        model = ScriptedModel(
            [
                "[WARNING] 03:00 whalewisdom.com layout changed. -> "
                "[RESOLVED] 03:03 collection resumed."
            ]
        )

        line = await GeminiFeedNarrator(model).narrate(self._events())

        assert line is not None
        assert line.startswith("[WARNING]")

    @pytest.mark.asyncio
    async def test_a_reply_containing_emoji_is_replaced_by_a_written_summary(self) -> None:
        """Status text stays plain, whatever the model returns."""
        model = ScriptedModel(["\u26a0\ufe0f 03:00 broken -> \u2705 03:03 fixed"])

        line = await GeminiFeedNarrator(model).narrate(self._events())

        assert line is not None
        assert "\u26a0" not in line
        assert "\u2705" not in line
        assert "[WARNING]" in line
        assert "[RESOLVED]" in line

    @pytest.mark.asyncio
    async def test_an_empty_feed_is_not_narrated(self) -> None:
        model = ScriptedModel(["never used"])

        assert await GeminiFeedNarrator(model).narrate([]) is None
        assert model.text_calls == []

    @pytest.mark.asyncio
    async def test_a_model_failure_falls_back_to_a_written_summary(self) -> None:
        model = ScriptedModel(error=GeminiError("model unavailable"))

        line = await GeminiFeedNarrator(model).narrate(self._events())

        assert line is not None
        assert "[WARNING]" in line
        assert "[RESOLVED]" in line

    @pytest.mark.asyncio
    async def test_the_line_stays_short_enough_for_one_row(self) -> None:
        model = ScriptedModel(["[WARNING] " + "x" * 500])

        line = await GeminiFeedNarrator(model).narrate(self._events())

        assert line is not None
        assert len(line) <= 200
