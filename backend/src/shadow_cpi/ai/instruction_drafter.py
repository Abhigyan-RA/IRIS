"""Writing the repair instruction sent when a collector breaks.

When a page is redesigned, the provider can rebuild the extraction from a
description of what to look for. The quality of that description is the whole
game: naming a position in the page is what stopped working, so the instruction has
to describe meaning instead.

A model writes a better description than a template can. But the repair path must
keep working when the model is unavailable, over quota, or returns something
unusable, so every failure falls back to the written instruction rather than
leaving a broken collector unrepaired.
"""

from __future__ import annotations

from collections.abc import Sequence

from shadow_cpi.ai.gemini import GeminiError
from shadow_cpi.ai.prompts import REPAIR_INSTRUCTION_SYSTEM, REPAIR_INSTRUCTION_USER
from shadow_cpi.ai.protocols import TextModel
from shadow_cpi.ingestion.repair import FieldNameInstructionDrafter

# The provider expects a short instruction. Anything longer is a sign the model
# started explaining itself rather than describing the data.
MAX_INSTRUCTION_LENGTH = 300

# Words that mean the instruction describes markup rather than meaning. An
# instruction like this would break again at the next redesign, so it is discarded.
_MARKUP_WORDS = (
    "css",
    "xpath",
    "selector",
    "class=",
    "classname",
    "<td",
    "<div",
    "<span",
    "nth-child",
    "third td",
    "table.",
    "div.",
)


class GeminiInstructionDrafter:
    """Asks the model to describe what a broken collector should look for."""

    def __init__(self, model: TextModel) -> None:
        """Create the drafter.

        Args:
            model: The model to ask, injected so tests script its replies.
        """
        self._model = model
        self._fallback = FieldNameInstructionDrafter()

    async def draft(
        self,
        collector_id: str,
        missing_fields: Sequence[str],
        reason: str,
    ) -> str:
        """Write a repair instruction.

        Args:
            collector_id: Collector being repaired.
            missing_fields: Fields that stopped arriving.
            reason: Why the run was judged broken.

        Returns:
            A short instruction describing what to find. Falls back to the written
            instruction if the model is unavailable or its answer names markup, is
            too long, or is empty.
        """
        # Imported here rather than at module scope: the source descriptions import the
        # drafter, so a top-level import would close a cycle between the two modules.
        from shadow_cpi.ingestion.brightdata.collectors import SCRAPED_SOURCES

        source = SCRAPED_SOURCES.get(collector_id)
        prompt = REPAIR_INSTRUCTION_USER.format(
            collector_id=collector_id,
            source_name=source.source_name if source else "unknown site",
            expected_description=source.extraction_prompt if source else "the expected values",
            missing_fields=", ".join(missing_fields) or "the expected values",
            reason=reason,
        )

        try:
            drafted = (await self._model.generate_text(REPAIR_INSTRUCTION_SYSTEM, prompt)).strip()
        except GeminiError:
            drafted = ""

        if not _is_usable(drafted):
            return await self._fallback.draft(
                collector_id=collector_id,
                missing_fields=missing_fields,
                reason=reason,
            )
        return drafted


def _is_usable(instruction: str) -> bool:
    """Whether a drafted instruction is worth sending.

    Args:
        instruction: The model's answer.

    Returns:
        True when it is present, short enough, and free of markup language.
    """
    if not instruction or len(instruction) > MAX_INSTRUCTION_LENGTH:
        return False
    lowered = instruction.lower()
    return not any(word in lowered for word in _MARKUP_WORDS)
