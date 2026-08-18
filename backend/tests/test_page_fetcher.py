"""Tests for fetching a page directly, without the scraping provider."""

from __future__ import annotations

from collections.abc import Mapping

import pytest

from shadow_cpi.ingestion.page_fetcher import DEFAULT_USER_AGENT, DirectPageError, DirectPageFetcher


class RecordingHttpClient:
    def __init__(self, page: str = "<html>4.52</html>", error: Exception | None = None) -> None:
        self.page = page
        self.error = error
        self.calls: list[tuple[str, Mapping[str, str]]] = []

    async def get_json(
        self,
        url: str,
        params: Mapping[str, str | int] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> object:
        raise AssertionError("pages are read as text")

    async def get_text(
        self,
        url: str,
        params: Mapping[str, str | int] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> str:
        self.calls.append((url, dict(headers or {})))
        if self.error is not None:
            raise self.error
        return self.page

    async def post_json(
        self,
        url: str,
        body: Mapping[str, object],
        headers: Mapping[str, str] | None = None,
    ) -> object:
        raise AssertionError("pages are read with GET")


class TestDirectPageFetcher:
    @pytest.mark.asyncio
    async def test_returns_the_page(self) -> None:
        http = RecordingHttpClient()

        page = await DirectPageFetcher(http).fetch_page("https://www.eia.gov/prices.htm")

        assert "4.52" in page

    @pytest.mark.asyncio
    async def test_identifies_itself_to_the_site(self) -> None:
        """An anonymous request is what most simple blocks look for."""
        http = RecordingHttpClient()

        await DirectPageFetcher(http).fetch_page("https://www.eia.gov/prices.htm")

        assert http.calls[0][1]["User-Agent"] == DEFAULT_USER_AGENT

    @pytest.mark.asyncio
    async def test_needs_no_credential(self) -> None:
        assert DirectPageFetcher(RecordingHttpClient()).is_configured is True

    @pytest.mark.asyncio
    async def test_an_empty_page_is_reported(self) -> None:
        http = RecordingHttpClient(page="   ")

        with pytest.raises(DirectPageError, match="empty"):
            await DirectPageFetcher(http).fetch_page("https://www.eia.gov/prices.htm")

    @pytest.mark.asyncio
    async def test_a_failure_names_the_page(self) -> None:
        http = RecordingHttpClient(error=RuntimeError("status 503"))

        with pytest.raises(DirectPageError, match="eia.gov"):
            await DirectPageFetcher(http).fetch_page("https://www.eia.gov/prices.htm")
