"""What every data source has in common.

The platform reads from around ten sources with nothing in common technically:
some are government JSON APIs, some are scraped web pages. This module defines the
one thing they all share, so that everything downstream, including the scheduler,
treats them identically.

Adding a source means writing a class with a ``source_id``, a ``source_name``, and
an ``ingest`` method, then registering it. No existing file changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from shadow_cpi.config import Settings
from shadow_cpi.db.protocols import HealthEventWriter
from shadow_cpi.ingestion.http import HttpClient
from shadow_cpi.shared import CommodityPrice, InstitutionalHolding


@dataclass(frozen=True, slots=True)
class IngestionContext:
    """Everything a source needs from the outside world.

    Passing this in, rather than letting each source create its own HTTP client
    and read its own configuration, is what makes sources testable: a test builds
    a context around a fake client and nothing reaches the network.

    Attributes:
        http: Client used for outbound requests.
        settings: Application settings, including any API keys the source needs.
        events: Where a source records what happened during its run. Optional so a source
            can be exercised in isolation, but a real run always supplies it: without it
            the detection and repair of a broken scraper would happen and leave no trace.
    """

    http: HttpClient
    settings: Settings
    events: HealthEventWriter | None = None


@dataclass(frozen=True, slots=True)
class IngestionResult:
    """What one run of one source produced.

    A run that finds nothing is normal, not a failure: most sources publish on a
    schedule, so polling between publications legitimately returns nothing.

    Attributes:
        source_name: Which source produced this, for logging and attribution.
        prices: Price observations found.
        holdings: Disclosure lines found.
    """

    source_name: str
    prices: tuple[CommodityPrice, ...] = field(default=())
    holdings: tuple[InstitutionalHolding, ...] = field(default=())

    @property
    def record_count(self) -> int:
        """Total number of records in this result.

        Returns:
            Prices plus holdings.
        """
        return len(self.prices) + len(self.holdings)


@runtime_checkable
class DataSourceIngestor(Protocol):
    """One source of data.

    Attributes:
        source_id: Stable identifier used in configuration, schedules, and logs,
            for example ``eia_petroleum_spot``.
        source_name: The origin as a person would name it, for example ``eia.gov``.
    """

    source_id: str
    source_name: str

    async def ingest(self) -> IngestionResult:
        """Fetch from the source and return validated records.

        Implementations validate the raw payload before converting it, so a change
        at the source surfaces as a clear error instead of bad data spreading.
        """
        ...
