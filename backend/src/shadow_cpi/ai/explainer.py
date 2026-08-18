"""Explaining why a price move matters.

The graph knows that copper is refined into stator coils which are required for
electric-vehicle manufacturing. That is precise and useless to most readers. This
turns it into a sentence a procurement manager can act on.

The explanation is grounded in the relationships found in the graph, and nothing
else. With no relationships there is nothing to ground it in, so no explanation is
produced rather than one being invented.
"""

from __future__ import annotations

from collections.abc import Sequence

from shadow_cpi.ai.gemini import GeminiError
from shadow_cpi.ai.prompts import RIPPLE_EXPLANATION_SYSTEM, RIPPLE_EXPLANATION_USER
from shadow_cpi.ai.protocols import TextModel
from shadow_cpi.db.neo4j.repository import RippleLink

# Explanations are one or two sentences. A longer answer means the model started
# adding context of its own, which is what must not happen here.
MAX_EXPLANATION_LENGTH = 400


class GeminiRippleExplainer:
    """Writes a plain-language explanation of a commodity's downstream effect."""

    def __init__(self, model: TextModel) -> None:
        """Create the explainer.

        Args:
            model: The model to ask, injected so tests script its replies.
        """
        self._model = model

    async def explain(
        self,
        commodity: str,
        price_summary: str,
        links: Sequence[RippleLink],
    ) -> str | None:
        """Explain what a commodity move affects.

        Args:
            commodity: The commodity in question.
            price_summary: Short description of the move, such as "up 8 percent
                this week".
            links: Relationships found in the graph, which are the only facts the
                explanation may draw on.

        Returns:
            The explanation, or None when there are no relationships to explain or
            the model is unavailable. An absent explanation is honest; an invented
            one is not.
        """
        if not links:
            return None

        relationships = "\n".join(
            f"- {link.source} {link.relationship} {link.target}"
            + (f" (cost share {link.weight})" if link.weight is not None else "")
            for link in links
        )
        prompt = RIPPLE_EXPLANATION_USER.format(
            commodity=commodity,
            price_summary=price_summary,
            relationships=relationships,
        )

        try:
            explanation = (
                await self._model.generate_text(RIPPLE_EXPLANATION_SYSTEM, prompt)
            ).strip()
        except GeminiError:
            return None

        if not explanation:
            return None
        return explanation[:MAX_EXPLANATION_LENGTH]
