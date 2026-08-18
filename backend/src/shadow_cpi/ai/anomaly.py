"""Reviewing a price series for unusual moves.

Run nightly, this is what turns a wall of numbers into a short list worth looking
at. The judgement is made against the recent range of the same series, not against
any external idea of what a price should be, so a commodity that is simply
expensive is not flagged while a sudden jump in a normally steady series is.

A finding is advisory. It is returned for display, never used to alter or discard a
stored price, because a genuine spike and a bad reading look identical from here.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from shadow_cpi.ai.gemini import GeminiError
from shadow_cpi.ai.prompts import ANOMALY_SYSTEM, ANOMALY_USER
from shadow_cpi.ai.protocols import StructuredModel
from shadow_cpi.shared import CommodityPrice

# Below this many observations there is no range to judge against, so the series is
# skipped rather than guessed at.
MIN_OBSERVATIONS = 2


class AnomalyFinding(BaseModel):
    """The model's judgement about a series.

    Attributes:
        is_anomaly: Whether the most recent move is unusual for this series.
        severity: How unusual, restricted to three values so it can drive a badge.
        explanation: One sentence saying why.
    """

    model_config = ConfigDict(extra="ignore")

    is_anomaly: bool
    severity: Literal["low", "medium", "high"]
    explanation: str


class AnomalyReviewer:
    """Judges whether the latest move in a series is unusual."""

    def __init__(self, model: StructuredModel) -> None:
        """Create the reviewer.

        Args:
            model: The model to ask, injected so tests script its replies.
        """
        self._model = model

    async def review(
        self,
        entity_name: str,
        history: Sequence[CommodityPrice],
    ) -> AnomalyFinding | None:
        """Review one series.

        Args:
            entity_name: Entity the series belongs to.
            history: Prices, oldest first.

        Returns:
            The finding, or None when the series is too short to judge, the model is
            unavailable, or its answer does not match the expected shape. A missing
            finding simply means nothing is flagged, which is a safe default for an
            advisory signal.
        """
        if len(history) < MIN_OBSERVATIONS:
            return None

        series = "\n".join(f"- {price.recorded_at:%Y-%m-%d}: {price.price}" for price in history)
        prompt = ANOMALY_USER.format(
            entity_name=entity_name,
            unit=history[-1].unit,
            series=series,
        )

        try:
            return await self._model.generate_model(ANOMALY_SYSTEM, prompt, AnomalyFinding)
        except (GeminiError, ValidationError, json.JSONDecodeError):
            return None
