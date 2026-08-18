"""Summarising a run of health events as one readable line.

The health feed records what happened step by step, which is right for an audit
trail and dense to read. This turns a sequence into one sentence:

    [WARNING] 03:00 whalewisdom.com layout changed. -> [AUTO-HEALING] 03:02 repair
    requested. -> [RESOLVED] 03:03 collection resumed.

The bracketed labels are not decoration. They are the reason this reads correctly
in a terminal, in a log aggregator, and to a screen reader, where emoji do not. The
model is instructed to use them, and any reply that contains emoji anyway is
discarded in favour of a written summary, so the rule holds regardless of what the
model returns.
"""

from __future__ import annotations

from collections.abc import Sequence

from shadow_cpi.ai.gemini import GeminiError
from shadow_cpi.ai.prompts import NARRATION_SYSTEM, NARRATION_USER
from shadow_cpi.ai.protocols import TextModel
from shadow_cpi.shared import PipelineEventType, PipelineHealthEvent
from shadow_cpi.tooling.no_emoji import find_emoji

# One line in a feed. Anything longer stops being a summary.
MAX_LINE_LENGTH = 200

# The label each event stage is written with.
_LABELS: dict[PipelineEventType, str] = {
    PipelineEventType.SUCCESS: "[OK]",
    PipelineEventType.DOM_SHIFT_DETECTED: "[WARNING]",
    PipelineEventType.SELF_HEAL_TRIGGERED: "[AUTO-HEALING]",
    PipelineEventType.SELF_HEAL_RESOLVED: "[RESOLVED]",
    PipelineEventType.SELF_HEAL_FAILED: "[FAILED]",
}


class GeminiFeedNarrator:
    """Writes a one-line summary of a sequence of health events."""

    def __init__(self, model: TextModel) -> None:
        """Create the narrator.

        Args:
            model: The model to ask, injected so tests script its replies.
        """
        self._model = model

    async def narrate(self, events: Sequence[PipelineHealthEvent]) -> str | None:
        """Summarise a sequence of events as one line.

        Args:
            events: The events, oldest first.

        Returns:
            The summary line, or None when there are no events. Falls back to a
            written summary if the model is unavailable or returns emoji.
        """
        if not events:
            return None

        prompt = NARRATION_USER.format(events=_describe(events))
        try:
            line = (await self._model.generate_text(NARRATION_SYSTEM, prompt)).strip()
        except GeminiError:
            line = ""

        if not line or find_emoji(line):
            line = _written_summary(events)
        return line[:MAX_LINE_LENGTH]


def _describe(events: Sequence[PipelineHealthEvent]) -> str:
    """Render events as lines for the prompt.

    Args:
        events: The events to describe.

    Returns:
        One line per event, with its time, label, source, and message.
    """
    return "\n".join(
        f"- {event.occurred_at:%H:%M} {_LABELS.get(event.event_type, '[INFO]')} "
        f"{event.source_name}: {event.message or event.event_type.value}"
        for event in events
    )


def _written_summary(events: Sequence[PipelineHealthEvent]) -> str:
    """Build the summary without the model.

    Args:
        events: The events, oldest first.

    Returns:
        A line in the same shape the model is asked for, so the feed reads
        consistently whether or not the model was involved.
    """
    return " -> ".join(
        f"{_LABELS.get(event.event_type, '[INFO]')} {event.occurred_at:%H:%M} "
        f"{event.source_name} {event.event_type.value.replace('_', ' ')}"
        for event in events
    )
