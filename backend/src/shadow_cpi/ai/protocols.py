"""The model, as the services see it.

Services depend on this narrow interface rather than on the client class, so each
one can be tested with a few lines of scripted replies and no network.
"""

from __future__ import annotations

from typing import Protocol, TypeVar

from pydantic import BaseModel

_ModelType = TypeVar("_ModelType", bound=BaseModel)


class TextModel(Protocol):
    """Answers a prompt with text."""

    async def generate_text(
        self,
        system_instruction: str,
        user_prompt: str,
        temperature: float = 0.0,
    ) -> str:
        """Return the model's reply as text."""
        ...


class StructuredModel(Protocol):
    """Answers a prompt with an object matching a given shape."""

    async def generate_model(
        self,
        system_instruction: str,
        user_prompt: str,
        schema: type[_ModelType],
        temperature: float = 0.0,
    ) -> _ModelType:
        """Return the model's reply, validated against ``schema``."""
        ...
