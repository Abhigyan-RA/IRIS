"""Fetching a page directly, without the scraping provider.

Not every page needs unlocking. Government sites publish prices in plain HTML with no bot
protection, no rate traps, and no objection to being read. Sending those through a paid
unlocking service would cost money for nothing.

Commercial sites are different: they actively block automated readers, which is what the
provider exists for. Each source therefore says which it needs, and both fetchers satisfy
the same interface so the reading and repair logic above them is identical either way.
"""

from __future__ import annotations

from shadow_cpi.ingestion.http import HttpClient

# Sent so the site can see who is asking. A blank or obviously scripted identity is what
# most simple blocks look for, and being honest about it is also the polite thing to do.
DEFAULT_USER_AGENT = "ShadowCPI/1.0 (+https://github.com/shadow-cpi; contact in .env)"


class DirectPageError(RuntimeError):
    """A page could not be fetched."""


class DirectPageFetcher:
    """Fetches a page with an ordinary HTTP request."""

    def __init__(self, http: HttpClient, user_agent: str = DEFAULT_USER_AGENT) -> None:
        """Create the fetcher.

        Args:
            http: HTTP client to send requests through.
            user_agent: How to identify this client to the site.
        """
        self._http = http
        self._user_agent = user_agent

    @property
    def is_configured(self) -> bool:
        """Whether pages can be fetched.

        Returns:
            Always True. A direct fetch needs no credential, which is the point of using
            it where a site permits it.
        """
        return True

    async def fetch_page(self, url: str) -> str:
        """Fetch one page's content.

        Args:
            url: Page to read.

        Returns:
            The page content as text.

        Raises:
            DirectPageError: If the request fails or the page comes back empty.
        """
        try:
            content = await self._http.get_text(url, headers={"User-Agent": self._user_agent})
        except Exception as error:
            raise DirectPageError(f"Could not fetch {url}: {type(error).__name__}") from None

        if not content.strip():
            raise DirectPageError(f"{url} returned an empty page")
        return content
