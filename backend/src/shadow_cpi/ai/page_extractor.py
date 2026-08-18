"""Reading prices out of a web page with the model.

A traditional scraper is told where to look: the third cell of a table with a particular
class. That works until the page is redesigned, which is the failure this project is
built around.

Here nothing is told where to look. The page text is handed to the model along with a
description of what to find, in words, and the model returns the values. A redesign moves
the numbers around the page without changing what they mean, so the same instruction
keeps working. When it does stop working, the repair is a better sentence rather than a
new selector.

Pages are trimmed of markup and truncated before being sent. A commodity page is mostly
navigation, adverts, and scripts, and sending all of it would be slow, expensive, and no
more accurate.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from shadow_cpi.ai.gemini import GeminiError
from shadow_cpi.ai.protocols import StructuredModel

# How much page text to send. Enough to include a price table well down the page,
# bounded so one enormous page cannot exhaust the model's context or the daily budget.
MAX_PAGE_CHARACTERS = 12_000

# When a page is longer than the window, the beginning and the end are both kept.
#
# This matters more than it sounds. A quote page puts the current value near the top,
# while a historical table puts the newest row at the bottom, so keeping only the start
# of a long table hands the model data from decades ago and it answers with a price that
# looks plausible and is wrong. Keeping both ends covers both layouts, and the gap in the
# middle is marked so the model knows text was removed.
_TAIL_SHARE = 0.4
_OMISSION_MARKER = "\n\n[... middle of page omitted ...]\n\n"

_SCRIPT_AND_STYLE = re.compile(r"<(script|style|noscript|svg)\b.*?</\1>", re.DOTALL | re.IGNORECASE)
_TAGS = re.compile(r"<[^>]+>")
_WHITESPACE = re.compile(r"[ \t\r\f\v]+")
_BLANK_LINES = re.compile(r"\n{3,}")

EXTRACTION_SYSTEM = """
You read financial values out of the text of a web page.

Rules:
- Return only JSON: {"rows": [{"price": number|null, "change_pct": number|null,
  "label": string|null, "as_of": string|null}]}
- Find the values by what they mean on the page, never by where they sit. Position is
  what changes when a page is redesigned.
- Always take the most recent observation. Pages often list history, oldest first, and an
  older row is a wrong answer even though it looks plausible. If the page shows dates,
  choose the latest one and put it in as_of.
- Some pages are shown to you with the middle removed and marked as omitted. The newest
  row of a historical table is usually at the very end of the text.
- price is that most recent value, as a plain number with no currency symbol or thousands
  separators. Negative values are valid and must be kept.
- change_pct is the percentage change over the most recent period shown, as a plain
  number. Use null when the page does not show one.
- If the page does not contain the value at all, return {"rows": []}. Never guess, and
  never carry a number over from your own knowledge.
""".strip()

EXTRACTION_USER = """
What to find: {description}
Expected value: {entity_name}
{repair_note}

Page text:
{page_text}
""".strip()


class ExtractedRow(BaseModel):
    """One value read from a page.

    Attributes:
        price: The value found, or None when the page did not show it.
        change_pct: Percentage change over the most recent period shown.
        label: What the model believes the value is, used for diagnosis when a page
            changes and the wrong number starts arriving.
        as_of: The date the model took the value from, when the page shows one. Recorded
            so that a value read from the wrong row of a historical table is visible
            rather than silently stored as today's price.
    """

    model_config = ConfigDict(extra="ignore")

    price: Decimal | None = None
    change_pct: Decimal | None = None
    label: str | None = None
    as_of: str | None = None


class ExtractedPage(BaseModel):
    """Everything read from one page.

    Attributes:
        rows: The values found. Empty when the page does not contain them, which is what
            the health check treats as a page that has changed.
    """

    model_config = ConfigDict(extra="ignore")

    rows: list[ExtractedRow] = Field(default_factory=list)


def page_to_text(html: str, limit: int = MAX_PAGE_CHARACTERS) -> str:
    """Reduce a page to the text a reader would see.

    Args:
        html: The page as fetched.
        limit: How many characters to keep.

    Returns:
        Plain text, with scripts, styles, and markup removed and whitespace collapsed. A
        page longer than the limit is kept from both ends, because the value being looked
        for may be at the top of a quote page or at the bottom of a historical table.
    """
    without_code = _SCRIPT_AND_STYLE.sub(" ", html)
    without_tags = _TAGS.sub("\n", without_code)
    collapsed = _WHITESPACE.sub(" ", without_tags)
    tidied = _BLANK_LINES.sub("\n\n", collapsed)
    text = "\n".join(line.strip() for line in tidied.splitlines() if line.strip())

    if len(text) <= limit:
        return text

    tail_length = int(limit * _TAIL_SHARE)
    head_length = limit - tail_length
    return f"{text[:head_length]}{_OMISSION_MARKER}{text[-tail_length:]}"


class GeminiPageExtractor:
    """Reads values from a page using the model."""

    def __init__(self, model: StructuredModel) -> None:
        """Create the extractor.

        Args:
            model: The model to ask, injected so tests script its replies.
        """
        self._model = model

    async def extract(
        self,
        html: str,
        description: str,
        entity_name: str,
        repair_instruction: str | None = None,
    ) -> list[dict[str, object]]:
        """Read the requested values out of a page.

        Args:
            html: The page as fetched.
            description: What to look for, in words.
            entity_name: What the value should be, which anchors the model when a page
                lists many instruments.
            repair_instruction: Extra guidance written after a failed attempt, used by
                the repair loop.

        Returns:
            One dictionary per value found, shaped for the health check and the price
            mapper. An empty list means the page did not contain the values, which is
            the signal that the page has changed.
        """
        page_text = page_to_text(html)
        if not page_text:
            return []

        prompt = EXTRACTION_USER.format(
            description=description,
            entity_name=entity_name,
            repair_note=(
                f"Previous attempt failed. Additional guidance: {repair_instruction}"
                if repair_instruction
                else ""
            ),
            page_text=page_text,
        )

        try:
            extracted = await self._model.generate_model(EXTRACTION_SYSTEM, prompt, ExtractedPage)
        except (GeminiError, ValidationError, json.JSONDecodeError):
            # Treated as a page that yielded nothing, which sends the run into the repair
            # path rather than raising and losing the other sources in this run.
            return []

        return [
            {
                "price": None if row.price is None else str(row.price),
                "change_pct": None if row.change_pct is None else str(row.change_pct),
                "label": row.label,
                "as_of": row.as_of,
            }
            for row in extracted.rows
        ]
