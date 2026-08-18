"""The copilot endpoint: a free-form question, answered from stored data.

This is the way in for someone who does not want to navigate five screens. It is
also the only endpoint that costs money per request, which is why it has a stricter
rate limit than everything else.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from shadow_cpi.ai.copilot import MAX_QUESTION_LENGTH
from shadow_cpi.ai.gemini import GeminiQuotaExceededError
from shadow_cpi.api.dependencies import Copilot, require_copilot

router = APIRouter(prefix="/api/copilot", tags=["copilot"])


class AskRequest(BaseModel):
    """A question to answer.

    Attributes:
        question: The question, in plain language.
    """

    question: str = Field(min_length=1, max_length=MAX_QUESTION_LENGTH)


class AskResponse(BaseModel):
    """An answer and the evidence behind it.

    Attributes:
        answer: The reply, in plain language.
        sources: URLs of the data the answer used, so any claim can be checked.
        data_as_of: Timestamp of the newest evidence used, when prices were involved.
    """

    answer: str
    sources: list[str]
    data_as_of: datetime | None


@router.post("/ask", response_model=AskResponse, summary="Ask a question about the data")
async def ask(
    copilot: Annotated[Copilot, Depends(require_copilot)],
    request: AskRequest,
) -> AskResponse:
    """Answer a question using stored prices, relationships, and filings.

    Args:
        copilot: The grounded copilot service.
        request: The question.

    Returns:
        The answer with its sources. A question nothing covers still returns a
        successful reply that says so, because that is the honest answer rather
        than an error.

    Raises:
        HTTPException: If the question is unusable, or the daily model cap has been
            reached, which is a temporary condition and reported as such.
    """
    if not request.question.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A question cannot be only whitespace",
        )

    try:
        answer = await copilot.ask(request.question)
    except GeminiQuotaExceededError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"The daily model call cap has been reached: {error}",
        ) from error
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error

    return AskResponse(
        answer=answer.answer,
        sources=answer.sources,
        data_as_of=answer.data_as_of,
    )
