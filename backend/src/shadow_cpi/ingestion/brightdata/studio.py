"""Driving a Bright Data Scraper Studio collector.

A collector is a scraper built in Scraper Studio, identified by a handle like
``c_mswnopw72dyj64c7s3``. Running one takes two calls, and repairing one takes three. The
endpoints below were each exercised against the live service before this module was
written; the shapes are what it actually returns, not what seemed likely.

Running a collector:

    POST /dca/trigger_immediate?collector=c_...
         body: {"url": "..."}  ->  {"response_id": "d2t..."}
    GET  /dca/get_result?response_id=d2t...       -> a JSON object while it works,
                                                     a JSON array once rows exist

Repairing a collector after the target site changes, which Scraper Studio calls
self-healing:

    POST /dca/collectors/{c}/refactor_template    body: {"prompt": "what broke"}
    GET  /dca/collectors/{c}/refactor_template/progress  -> poll until pending_answer
    POST /dca/collectors/{c}/resume_automation_job body: {"message": true, "auto_save": true}

The repair keeps the same collector handle, so every schedule and integration pointing at
the scraper keeps working. That is the whole point: the fix is a sentence describing what
broke, not a rewritten selector, and nothing downstream has to be told about it.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping, Sequence
from enum import StrEnum
from typing import Any

from shadow_cpi.ingestion.http import HttpClient

API_ROOT = "https://api.brightdata.com"

TRIGGER_URL = f"{API_ROOT}/dca/trigger_immediate"
RESULT_URL = f"{API_ROOT}/dca/get_result"
REFACTOR_URL_TEMPLATE = f"{API_ROOT}/dca/collectors/{{collector_id}}/refactor_template"
REFACTOR_PROGRESS_URL_TEMPLATE = (
    f"{API_ROOT}/dca/collectors/{{collector_id}}/refactor_template/progress"
)
RESUME_URL_TEMPLATE = f"{API_ROOT}/dca/collectors/{{collector_id}}/resume_automation_job"

# A run of a single-page collector returns in under ten seconds in practice. The ceiling is
# generous because a page behind a bot challenge can take several retries on the provider's
# side, and giving up early would look like a broken scraper.
DEFAULT_POLL_SECONDS = 5.0
DEFAULT_MAX_POLLS = 120

# A repair is an AI code change and is documented as taking up to fifteen minutes.
DEFAULT_HEAL_POLL_SECONDS = 10.0
DEFAULT_HEAL_MAX_POLLS = 90

# The provider's own guidance: keep a repair prompt under a thousand characters.
MAX_HEAL_PROMPT_LENGTH = 1_000


class ScraperStudioError(RuntimeError):
    """A collector could not be run or repaired."""


class HealStatus(StrEnum):
    """Where a repair has got to.

    Attributes:
        AWAITING_APPROVAL: A fix has been drafted and is waiting to be accepted.
        DONE: The fix has been applied to the collector.
        FAILED: No fix could be produced.
    """

    AWAITING_APPROVAL = "awaiting_approval"
    DONE = "done"
    FAILED = "failed"


class ScraperStudioClient:
    """Runs and repairs Scraper Studio collectors."""

    def __init__(
        self,
        http: HttpClient,
        api_key: str,
        sleep: Callable[[float], Awaitable[None]] | None = None,
        poll_seconds: float = DEFAULT_POLL_SECONDS,
        max_polls: int = DEFAULT_MAX_POLLS,
    ) -> None:
        """Create the client.

        Args:
            http: HTTP client to send requests through, injected so tests never reach the
                network.
            api_key: Account token.
            sleep: How to wait between polls. Injected so tests do not actually wait.
            poll_seconds: Seconds between polls while a run is in progress.
            max_polls: How many times to poll before giving up on a run.
        """
        self._http = http
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        self._sleep = sleep or asyncio.sleep
        self._poll_seconds = poll_seconds
        self._max_polls = max_polls

    async def run(self, collector_id: str, url: str) -> list[Mapping[str, object]]:
        """Run a collector against one page and return its rows.

        Args:
            collector_id: The collector to run.
            url: Page to scrape.

        Returns:
            The rows the collector produced, exactly as it defined them. An empty list
            means the run finished with nothing, which is the signal that the target page
            has changed.

        Raises:
            ScraperStudioError: If the run cannot be started, or does not finish within
                the polling budget.
        """
        response_id = await self._trigger(collector_id, url)

        for _ in range(self._max_polls):
            rows = await self._fetch_result(response_id)
            if rows is not None:
                return rows
            await self._sleep(self._poll_seconds)

        raise ScraperStudioError(
            f"Collector {collector_id} did not finish within "
            f"{int(self._poll_seconds * self._max_polls)} seconds"
        )

    async def _trigger(self, collector_id: str, url: str) -> str:
        """Start a run.

        Args:
            collector_id: The collector to run.
            url: Page to scrape.

        Returns:
            The run's identifier.

        Raises:
            ScraperStudioError: If the run does not start.
        """
        try:
            reply = await self._http.post_json(
                f"{TRIGGER_URL}?collector={collector_id}",
                # A single object, not a list. A list is rejected with 400 here, unlike the
                # batch endpoint which expects one.
                body={"url": url},
                headers=self._headers,
            )
        except Exception as error:
            raise ScraperStudioError(
                f"Could not start collector {collector_id}: {type(error).__name__}"
            ) from None

        if not isinstance(reply, dict) or not isinstance(reply.get("response_id"), str):
            raise ScraperStudioError(
                f"Collector {collector_id} returned no run identifier, so there is nothing "
                "to wait for"
            )
        return str(reply["response_id"])

    async def _fetch_result(self, response_id: str) -> list[Mapping[str, object]] | None:
        """Read a run's rows if they are ready.

        Args:
            response_id: The run to read.

        Returns:
            The rows when the run has finished, or None while it is still working. The
            endpoint signals progress by returning an object rather than an array, which is
            why the distinction is made on the reply's shape.
        """
        try:
            reply = await self._http.get_json(
                f"{RESULT_URL}?response_id={response_id}", headers=self._headers
            )
        except Exception:
            # A transient failure mid-run is worth another poll rather than an abort.
            return None

        if isinstance(reply, list):
            return [row for row in reply if isinstance(row, dict)]
        return None

    async def heal(self, collector_id: str, prompt: str) -> HealStatus:
        """Ask Scraper Studio to repair a collector.

        Args:
            collector_id: The collector to repair.
            prompt: Plain-language description of what broke, which is what the repair is
                generated from. Trimmed to the provider's documented limit.

        Returns:
            Whether a fix is awaiting approval, already applied, or could not be made.

        Raises:
            ScraperStudioError: If the request to start a repair fails outright.
        """
        try:
            reply = await self._http.post_json(
                REFACTOR_URL_TEMPLATE.format(collector_id=collector_id),
                body={"prompt": prompt[:MAX_HEAL_PROMPT_LENGTH]},
                headers=self._headers,
            )
        except Exception as error:
            raise ScraperStudioError(
                f"Could not start a repair for {collector_id}: {type(error).__name__}"
            ) from None

        return _read_heal_status(reply)

    async def heal_progress(self, collector_id: str) -> HealStatus:
        """Check how a repair is getting on.

        Args:
            collector_id: The collector being repaired.

        Returns:
            The current state of the repair.
        """
        try:
            reply = await self._http.get_json(
                REFACTOR_PROGRESS_URL_TEMPLATE.format(collector_id=collector_id),
                headers=self._headers,
            )
        except Exception:
            return HealStatus.FAILED
        return _read_heal_status(reply)

    async def wait_for_heal(
        self,
        collector_id: str,
        poll_seconds: float = DEFAULT_HEAL_POLL_SECONDS,
        max_polls: int = DEFAULT_HEAL_MAX_POLLS,
    ) -> HealStatus:
        """Wait until a repair is drafted, applied, or has failed.

        Args:
            collector_id: The collector being repaired.
            poll_seconds: Seconds between checks.
            max_polls: How many checks before giving up.

        Returns:
            The state the repair reached. Giving up is reported as a failure rather than
            raising, because the caller is a collection run that must carry on.
        """
        for _ in range(max_polls):
            status = await self.heal_progress(collector_id)
            # Anything other than a failure is a definite answer: the repair is either
            # drafted and waiting, or already applied. A failure here also covers a status
            # the endpoint has not settled on yet, so it is worth another look.
            if status is not HealStatus.FAILED:
                return status
            await self._sleep(poll_seconds)
        return HealStatus.FAILED

    async def approve_heal(self, collector_id: str, accept: bool = True) -> None:
        """Accept or discard a drafted repair.

        Accepting saves the change against the same collector handle, so nothing
        downstream needs to be updated. Discarding leaves the collector as it was, ready
        for a sharper description of the problem.

        Args:
            collector_id: The collector being repaired.
            accept: True to apply the fix, False to discard it.

        Raises:
            ScraperStudioError: If the decision cannot be recorded.
        """
        try:
            await self._http.post_json(
                RESUME_URL_TEMPLATE.format(collector_id=collector_id),
                body={"message": accept, "auto_save": accept},
                headers=self._headers,
            )
        except Exception as error:
            raise ScraperStudioError(
                f"Could not {'approve' if accept else 'reject'} the repair for "
                f"{collector_id}: {type(error).__name__}"
            ) from None


def _read_heal_status(reply: object) -> HealStatus:
    """Interpret a repair reply.

    Args:
        reply: Decoded reply from a repair endpoint.

    Returns:
        The state it describes. Anything unrecognised counts as a failure, because acting
        on a status we do not understand is worse than reporting that we cannot proceed.
    """
    if not isinstance(reply, dict):
        return HealStatus.FAILED

    status: Any = reply.get("status", "")
    text = str(status).lower()
    if text in {"pending_answer", "awaiting_approval"}:
        return HealStatus.AWAITING_APPROVAL
    if text in {"done", "ok", "saved", "completed"}:
        return HealStatus.DONE
    return HealStatus.FAILED


def first_value(row: Mapping[str, object], paths: Sequence[str]) -> object:
    """Read the first value present at any of several paths.

    Collectors define their own output shapes, and a generated one often nests values, for
    example ``price.value`` alongside ``price.currency``. Paths are dotted so a mapping can
    describe where a value lives without the caller knowing the shape in advance.

    Args:
        row: One row from a collector.
        paths: Dotted paths to try, in order of preference.

    Returns:
        The first value found, or None when none of the paths exist.
    """
    for path in paths:
        current: object = row
        for part in path.split("."):
            if isinstance(current, Mapping) and part in current:
                current = current[part]
            else:
                current = None
                break
        if current is not None:
            return current
    return None
