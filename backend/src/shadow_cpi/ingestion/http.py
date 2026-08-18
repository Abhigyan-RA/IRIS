"""Outbound HTTP, kept behind a small interface.

Sources depend on ``HttpClient``, not on a specific HTTP library. Tests therefore
pass a fake and never touch the network, and cross-cutting concerns such as
timeouts, retries, or request logging can be added in one place.

Failures from any source are reported as ``HttpError`` with the credentials
stripped out of the URL, because the first thing anyone does with an exception is
log it.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import TracebackType
from typing import Protocol, Self

import httpx

# Long enough for a slow government API, short enough that one stuck request does
# not hold up a scheduled run.
DEFAULT_TIMEOUT_SECONDS = 30.0


class HttpError(RuntimeError):
    """A request failed, or returned something unusable.

    Raised for connection failures, error statuses, and bodies that were supposed
    to be JSON but were not.
    """


def _safe_url(url: str) -> str:
    """Strip the query string from a URL so credentials are not logged.

    Args:
        url: URL that may carry an API key in its query string.

    Returns:
        The URL without its query string.
    """
    return url.split("?", maxsplit=1)[0]


class HttpClient(Protocol):
    """Fetches data over HTTP."""

    async def get_json(
        self,
        url: str,
        params: Mapping[str, str | int] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> object:
        """Fetch a URL and decode the JSON body."""
        ...

    async def get_text(
        self,
        url: str,
        params: Mapping[str, str | int] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> str:
        """Fetch a URL and return the body as text."""
        ...

    async def post_json(
        self,
        url: str,
        body: Mapping[str, object],
        headers: Mapping[str, str] | None = None,
    ) -> object:
        """Send a JSON body and return the decoded reply."""
        ...


class HttpxClient:
    """The real HTTP client.

    Use it as a context manager so connections are reused across requests within a
    run and closed afterwards:

        async with HttpxClient() as client:
            payload = await client.get_json(url)
    """

    def __init__(self, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS) -> None:
        """Create the client.

        Args:
            timeout_seconds: Maximum time to wait for a single request.
        """
        self._client = httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True)

    async def __aenter__(self) -> Self:
        """Enter the context manager.

        Returns:
            This client.
        """
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the underlying connections."""
        await self.aclose()

    async def aclose(self) -> None:
        """Close the underlying connections."""
        await self._client.aclose()

    async def _get(
        self,
        url: str,
        params: Mapping[str, str | int] | None,
        headers: Mapping[str, str] | None,
    ) -> httpx.Response:
        """Perform a GET request and check the status.

        Args:
            url: URL to fetch.
            params: Query string values.
            headers: Request headers.

        Returns:
            The successful response.

        Raises:
            HttpError: On a connection failure or an error status.
        """
        try:
            # Only pass query values when there are some. Handing httpx an empty mapping
            # replaces whatever query string the caller already put in the URL, which
            # silently drops parameters and produces a puzzling 400 from the far end.
            request_params = dict(params) if params else None
            response = await self._client.get(
                url,
                params=request_params,
                headers=dict(headers or {}),
            )
        except httpx.HTTPError as error:
            raise HttpError(
                f"Request to {_safe_url(url)} failed: {type(error).__name__}"
            ) from error

        if response.is_error:
            raise HttpError(f"Request to {_safe_url(url)} returned status {response.status_code}")
        return response

    async def get_json(
        self,
        url: str,
        params: Mapping[str, str | int] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> object:
        """Fetch a URL and decode the JSON body.

        Args:
            url: URL to fetch.
            params: Query string values.
            headers: Request headers.

        Returns:
            The decoded body, which callers validate against a schema before use.

        Raises:
            HttpError: If the request fails or the body is not valid JSON. A source
                returning an HTML maintenance page instead of JSON is a common and
                important case to report clearly.
        """
        response = await self._get(url, params, headers)
        try:
            return response.json()
        except ValueError as error:
            raise HttpError(f"Response from {_safe_url(url)} was not valid JSON") from error

    async def get_text(
        self,
        url: str,
        params: Mapping[str, str | int] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> str:
        """Fetch a URL and return the body as text.

        Args:
            url: URL to fetch.
            params: Query string values.
            headers: Request headers.

        Returns:
            The response body.

        Raises:
            HttpError: If the request fails or returns an error status.
        """
        response = await self._get(url, params, headers)
        return response.text

    async def post_json(
        self,
        url: str,
        body: Mapping[str, object],
        headers: Mapping[str, str] | None = None,
    ) -> object:
        """Send a JSON body and return the decoded reply.

        Args:
            url: URL to post to.
            body: Values to send as a JSON document.
            headers: Request headers.

        Returns:
            The decoded reply, or None when the service replies with no content.
            Job-control endpoints often acknowledge with an empty body, which is a
            success rather than something to report.

        Raises:
            HttpError: If the request fails, returns an error status, or returns a
                non-empty body that is not valid JSON.
        """
        try:
            response = await self._client.post(url, json=dict(body), headers=dict(headers or {}))
        except httpx.HTTPError as error:
            raise HttpError(
                f"Request to {_safe_url(url)} failed: {type(error).__name__}"
            ) from error

        if response.is_error:
            raise HttpError(f"Request to {_safe_url(url)} returned status {response.status_code}")
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError as error:
            raise HttpError(f"Response from {_safe_url(url)} was not valid JSON") from error
