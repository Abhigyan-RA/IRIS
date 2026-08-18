"""Describing what broke, so a scraper can be repaired.

This sits deliberately low in the layering, with no dependency on any particular way of
collecting data. Both collection paths need it, and the model-written version needs it
too, so putting it here is what keeps those modules from importing each other in a circle.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol


class InstructionDrafter(Protocol):
    """Writes the description of what broke that a repair is generated from."""

    async def draft(
        self,
        collector_id: str,
        missing_fields: Sequence[str],
        reason: str,
    ) -> str:
        """Describe what the scraper should be looking for."""
        ...


class FieldNameInstructionDrafter:
    """Builds a description from the names of the values that stopped arriving.

    Deterministic and dependency-free, which makes it a dependable default: the repair path
    still works when no model is configured or reachable. A model-written description can be
    substituted without any of the collection logic changing.
    """

    async def draft(
        self,
        collector_id: str,
        missing_fields: Sequence[str],
        reason: str,
    ) -> str:
        """Describe what to look for.

        Args:
            collector_id: Scraper being repaired, for context.
            missing_fields: Values that stopped arriving.
            reason: Why the attempt was judged to have failed.

        Returns:
            A short instruction naming the values to find by meaning rather than by
            position, since naming a position is exactly what stops working when a site is
            redesigned.
        """
        fields = ", ".join(missing_fields) or "the expected values"
        return (
            f"The page appears to have changed and {reason}. Find these values again by "
            f"what they mean on the page, not by their position: {fields}. "
            "Look for the most prominent current value near the instrument's name."
        )
