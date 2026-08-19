"""Sources that have no official API and must be read from the page itself.

These are the sources where a redesign breaks collection, which is why the repair
loop in ``self_heal.py`` exists.

Importing this package registers every scraped source, so the scheduler discovers
them without holding a list of its own.
"""

from shadow_cpi.ingestion.brightdata.collectors import (
    SCRAPED_SOURCES,
    ScrapedPriceIngestor,
    ScrapedSource,
)
from shadow_cpi.ingestion.brightdata.whalewisdom import (
    DEFAULT_WHALEWISDOM_FUNDS,
    WHALEWISDOM_SOURCE_ID,
    WhaleWisdomIngestor,
)

__all__ = [
    "DEFAULT_WHALEWISDOM_FUNDS",
    "SCRAPED_SOURCES",
    "WHALEWISDOM_SOURCE_ID",
    "ScrapedPriceIngestor",
    "ScrapedSource",
    "WhaleWisdomIngestor",
]
