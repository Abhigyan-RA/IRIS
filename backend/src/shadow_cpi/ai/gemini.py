"""Talking to Gemini.

One wrapper for every model call in the project, so the things that must be true
everywhere are true in one place:

- The key travels in a header, never in a URL, because URLs end up in logs.
- Replies are deterministic by default. This project uses the model for data work,
  where the same input should give the same answer, not for creative writing.
- Structured replies are validated against a schema. A model is not trusted to
  return the right shape; it is checked, and a mismatch is an error rather than
  something that flows onward as bad data.
- Calls are counted against a daily cap. Exceeding it raises, because a cost limit
  that quietly returns nothing is indistinguishable from missing data.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any, TypeVar

from pydantic import BaseModel

from shadow_cpi.ingestion.http import HttpClient

API_ROOT = "https://generativelanguage.googleapis.com/v1beta/models"

# Data work wants repeatability, so creativity is turned off unless a caller asks.
DEFAULT_TEMPERATURE = 0.0

# Matches the first JSON object in a reply, including one wrapped in a code fence.
_JSON_PATTERN = re.compile(r"\{.*\}", re.DOTALL)

_ModelType = TypeVar("_ModelType", bound=BaseModel)


class GeminiError(RuntimeError):
    """A model call failed, or returned something unusable."""


class GeminiQuotaExceededError(GeminiError):
    """The daily call cap has been reached.

    Raised rather than returning empty, so the condition is visible in logs and
    monitoring instead of looking like an absence of data.
    """


def build_endpoint(model: str) -> str:
    """Return the endpoint URL for a model.

    Args:
        model: Model name or alias, such as ``gemini-flash-latest``.

    Returns:
        The full endpoint URL.
    """
    return f"{API_ROOT}/{model}:generateContent"


def _utc_today() -> str:
    """Return today's date in UTC, as a string.

    Returns:
        The date, used as the key for the daily call counter.
    """
    return datetime.now(UTC).date().isoformat()


def extract_json(text: str) -> str:
    """Pull the JSON object out of a model reply.

    Models wrap JSON in markdown fences, and sometimes add a sentence before or
    after it, even when asked for JSON only. Rather than fail on that, the object
    itself is located and everything around it discarded.

    Args:
        text: The reply text.

    Returns:
        The JSON substring.

    Raises:
        GeminiError: If the reply contains no JSON object at all.
    """
    match = _JSON_PATTERN.search(text)
    if match is None:
        raise GeminiError("Model reply contained no JSON object")
    return match.group()


class GeminiClient:
    """Sends prompts to Gemini and returns text or validated objects."""

    def __init__(
        self,
        http: HttpClient,
        api_key: str,
        model: str,
        daily_call_cap: int,
        today: Callable[[], str] = _utc_today,
    ) -> None:
        """Create the client.

        Args:
            http: HTTP client to send requests through, injected so tests never
                reach the network.
            api_key: Model API key.
            model: Model name or alias to call.
            daily_call_cap: Maximum calls per day.
            today: Returns the current date as a string. Injected so the daily
                reset can be tested without waiting for midnight.
        """
        self._http = http
        self._api_key = api_key
        self._model = model
        self._cap = daily_call_cap
        self._today = today
        self._counted_day = today()
        self._calls_made = 0

    @property
    def calls_remaining(self) -> int:
        """How many calls are left today.

        Returns:
            The remaining allowance, never below zero.
        """
        self._roll_over_if_new_day()
        return max(0, self._cap - self._calls_made)

    def _roll_over_if_new_day(self) -> None:
        """Reset the counter when the date changes."""
        current = self._today()
        if current != self._counted_day:
            self._counted_day = current
            self._calls_made = 0

    def _reserve_call(self) -> None:
        """Count one call against the daily allowance.

        Raises:
            GeminiQuotaExceededError: If the allowance is used up.
        """
        self._roll_over_if_new_day()
        if self._calls_made >= self._cap:
            raise GeminiQuotaExceededError(
                f"Daily model call cap of {self._cap} reached; no further calls will be made today"
            )
        self._calls_made += 1

    async def _post(self, body: Mapping[str, object]) -> object:
        """Send one request to the model.

        Args:
            body: Request body.

        Returns:
            The decoded reply.

        Raises:
            GeminiError: If the request fails. The message deliberately omits the
                original error text, which can contain the request and therefore
                the key.
        """
        try:
            return await self._http.post_json(
                build_endpoint(self._model),
                body=body,
                headers={"x-goog-api-key": self._api_key, "Content-Type": "application/json"},
            )
        except Exception as error:
            raise GeminiError(
                f"Model call failed: {type(error).__name__}. " "See the transport logs for details."
            ) from None

    def _build_body(
        self,
        system_instruction: str,
        user_prompt: str,
        temperature: float,
        json_only: bool,
    ) -> dict[str, object]:
        """Assemble a request body.

        Args:
            system_instruction: What the model should do, and the rules it must
                follow.
            user_prompt: The material to work on.
            temperature: How much variation to allow.
            json_only: Whether to ask for a JSON reply.

        Returns:
            The request body.
        """
        generation_config: dict[str, object] = {"temperature": temperature}
        if json_only:
            generation_config["responseMimeType"] = "application/json"
        return {
            "system_instruction": {"parts": [{"text": system_instruction}]},
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "generationConfig": generation_config,
        }

    @staticmethod
    def _read_text(payload: object) -> str:
        """Read the reply text out of a model response.

        Args:
            payload: Decoded response body.

        Returns:
            The reply text, with surrounding whitespace removed.

        Raises:
            GeminiError: If the response carries no usable reply, including when it
                was blocked, which is reported with the stated reason.
        """
        if not isinstance(payload, dict):
            raise GeminiError("Model returned no reply")

        feedback: Any = payload.get("promptFeedback")
        if isinstance(feedback, dict) and feedback.get("blockReason"):
            raise GeminiError(f"Model declined to answer: {feedback['blockReason']}")

        candidates: Any = payload.get("candidates") or []
        if not candidates:
            raise GeminiError("Model returned no reply")

        parts: Any = candidates[0].get("content", {}).get("parts", [])
        text = "".join(str(part.get("text", "")) for part in parts if isinstance(part, dict))
        if not text.strip():
            raise GeminiError("Model returned no reply")
        return text.strip()

    async def generate_text(
        self,
        system_instruction: str,
        user_prompt: str,
        temperature: float = DEFAULT_TEMPERATURE,
    ) -> str:
        """Ask the model for a text reply.

        Args:
            system_instruction: What the model should do.
            user_prompt: The material to work on.
            temperature: How much variation to allow.

        Returns:
            The reply text.

        Raises:
            GeminiError: If the call fails or the reply is unusable.
            GeminiQuotaExceededError: If the daily cap is reached.
        """
        self._reserve_call()
        payload = await self._post(
            self._build_body(system_instruction, user_prompt, temperature, json_only=False)
        )
        return self._read_text(payload)

    async def generate_model(
        self,
        system_instruction: str,
        user_prompt: str,
        schema: type[_ModelType],
        temperature: float = DEFAULT_TEMPERATURE,
    ) -> _ModelType:
        """Ask the model for a reply and validate it against a schema.

        Args:
            system_instruction: What the model should do.
            user_prompt: The material to work on.
            schema: Shape the reply must match.
            temperature: How much variation to allow.

        Returns:
            The validated object.

        Raises:
            GeminiError: If the call fails, or the reply contains no JSON.
            pydantic.ValidationError: If the JSON does not match the schema.
            GeminiQuotaExceededError: If the daily cap is reached.
        """
        self._reserve_call()
        payload = await self._post(
            self._build_body(system_instruction, user_prompt, temperature, json_only=True)
        )
        text = self._read_text(payload)
        return schema.model_validate(json.loads(extract_json(text)))
