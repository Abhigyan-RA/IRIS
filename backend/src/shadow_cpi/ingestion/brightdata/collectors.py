"""Sources read from a web page rather than an API.

Freight indices, metal prices, and the fund-holdings site publish numbers on pages
but offer no free API, so they are collected by describing what to look for in
plain language and letting the provider find it.

Every source here shares one implementation. A source is a description, not code:
which collector to run, which page it reads, what to extract, and how to store the
result. Adding a source is one entry in the table below, which is why the eleventh
source needs no change to the code that runs the first ten.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Protocol

from shadow_cpi.ai.gemini import GeminiClient
from shadow_cpi.ai.instruction_drafter import GeminiInstructionDrafter
from shadow_cpi.ai.page_extractor import GeminiPageExtractor
from shadow_cpi.ingestion.base import IngestionContext, IngestionResult
from shadow_cpi.ingestion.brightdata.self_heal import RunOutcome, SelfHealingPageRunner
from shadow_cpi.ingestion.brightdata.studio import ScraperStudioClient, first_value
from shadow_cpi.ingestion.brightdata.studio_runner import SelfHealingStudioRunner
from shadow_cpi.ingestion.page_fetcher import DirectPageFetcher
from shadow_cpi.ingestion.registry import default_registry
from shadow_cpi.ingestion.repair import InstructionDrafter
from shadow_cpi.shared import CommodityPrice, IngestionMethod, PipelineHealthEvent, Sector

# Scraped values arrive as display text: "$4.52", "4,520.75", "+1.80%".
_NUMBER_PATTERN = re.compile(r"[-+]?\d[\d,]*\.?\d*")


@dataclass(frozen=True, slots=True)
class ScrapedSource:
    """A page this platform reads prices from.

    Attributes:
        collector_id: Identifier of the collector that reads the page.
        source_name: The website, as a person would name it.
        url: Page the collector reads, stored with every price for attribution.
        entity_name: Name to store the value under.
        sector: Which category the value belongs to.
        unit: What one unit of the price refers to.
        currency: Currency the page quotes in.
        extraction_prompt: Plain-language description of what to extract. It names
            the meaning of each value rather than its position, which is what lets
            the extraction be repaired after a redesign.
        requires_unlocking: Whether the site blocks automated readers. Those are collected
            through a Scraper Studio collector, which owns the interaction and parsing and
            can be healed in place when the site changes. Government sites publish openly
            and are read directly, which costs nothing and needs no collector.
        price_paths: Where the price may live in a row, as dotted paths tried in order. A
            generated collector nests values, for example ``price.value``.
        change_paths: Where the percentage change may live, as dotted paths.
        series_value_paths: Where a value that differs from row to row may live. Some pages
            publish a headline figure alongside a table of its parts: one container freight
            index with a price per trade lane, for example. Those parts are worth storing in
            their own right, so a reader can see which lane moved rather than only that the
            average did.
        series_label_paths: Where the name of that row's part may live, usually a link to the
            page describing it. Without a name there is nothing to store the value under.
        series_name_prefix: Prepended to the derived name, so a lane reads as
            ``FBX03_China_to_North_America_East_Coast`` rather than an unqualified slug.
    """

    collector_id: str
    source_name: str
    url: str
    entity_name: str
    sector: Sector
    unit: str
    extraction_prompt: str
    requires_unlocking: bool = True
    currency: str = "USD"
    price_paths: tuple[str, ...] = (
        "price.value",
        "price",
        "current_price",
        "last",
        "value",
    )
    change_paths: tuple[str, ...] = (
        "price_change_percent",
        "change_pct",
        "daily_change",
        "percent_change",
        "change_percent",
    )
    price_fields: tuple[str, ...] = ("price", "current_price", "last", "value")

    series_value_paths: tuple[str, ...] = ()
    series_label_paths: tuple[str, ...] = ()
    series_name_prefix: str = ""

    @property
    def collects_a_series(self) -> bool:
        """Whether this source publishes parts alongside its headline figure.

        Returns:
            True when both a per-row value and a name for it are declared. One without the
            other cannot be stored, so both are required.
        """
        return bool(self.series_value_paths) and bool(self.series_label_paths)

    @property
    def required_paths(self) -> tuple[str, ...]:
        """Where a usable row must carry its value.

        Returns:
            The price paths. A run is judged by whether the value can be found, not by
            whether a field with a particular name exists, because every collector defines
            its own output schema.
        """
        return self.price_paths


# The pages this platform reads, described rather than coded.
#
# The two government pages are read directly: they publish openly, so no unlocking
# service is involved and they work with no credential at all. The commercial pages block
# automated readers and go through the provider.
SCRAPED_SOURCES: dict[str, ScrapedSource] = {
    "eia_wti_page": ScrapedSource(
        collector_id="eia_wti_page",
        source_name="eia.gov",
        url="https://www.eia.gov/dnav/pet/hist/RWTCd.htm",
        entity_name="WTI_Crude",
        sector=Sector.ENERGY,
        unit="barrel",
        requires_unlocking=False,
        extraction_prompt=(
            "Extract the most recent daily Cushing, Oklahoma WTI crude oil spot price in "
            "dollars per barrel, taking the latest date shown."
        ),
    ),
    "eia_brent_page": ScrapedSource(
        collector_id="eia_brent_page",
        source_name="eia.gov",
        url="https://www.eia.gov/dnav/pet/hist/RBRTEd.htm",
        entity_name="Brent_Crude",
        sector=Sector.ENERGY,
        unit="barrel",
        requires_unlocking=False,
        extraction_prompt=(
            "Extract the most recent daily Europe Brent crude oil spot price in dollars "
            "per barrel, taking the latest date shown."
        ),
    ),
    "lme_copper_scraper": ScrapedSource(
        collector_id="lme_copper_scraper",
        source_name="investing.com",
        url="https://www.investing.com/commodities/copper",
        entity_name="Copper",
        sector=Sector.METALS,
        unit="lb",
        price_paths=("price.value", "price"),
        change_paths=("price_change_percent", "change_pct"),
        extraction_prompt=(
            "Extract the current price, the daily percent change, and today's high "
            "and low for copper futures."
        ),
    ),
    "fbx_scraper": ScrapedSource(
        collector_id="fbx_scraper",
        source_name="fbx.freightos.com",
        url="https://fbx.freightos.com/",
        entity_name="FBX_Global",
        sector=Sector.FREIGHT,
        unit="feu",
        price_paths=("fbx_global_index_value.value", "price.value", "price"),
        change_paths=("fbx_global_index_percent_change", "price_change_percent"),
        # The page prices each trade lane as well as the global average, and names the lane
        # in the link beside it. Those lane prices are the useful part: an importer cares
        # what their own route costs, not what the world average costs.
        series_value_paths=("fbx01_value.value",),
        series_label_paths=("product_page_url",),
        series_name_prefix="FBX",
        extraction_prompt=(
            "Extract the global container freight index value and each trade lane "
            "index value with its day-over-day percent change."
        ),
    ),
    "baltic_dry_scraper": ScrapedSource(
        collector_id="baltic_dry_scraper",
        source_name="tradingeconomics.com",
        url="https://tradingeconomics.com/commodity/baltic-dry",
        entity_name="Baltic_Dry_Index",
        sector=Sector.FREIGHT,
        unit="index_point",
        price_paths=("baltic_dry_index_value", "price.value", "price", "value"),
        change_paths=("baltic_dry_percent_change", "price_change_percent"),
        extraction_prompt=(
            "Extract the current Baltic Dry Index value and its daily percent change."
        ),
    ),
    "oilprice_scraper": ScrapedSource(
        collector_id="oilprice_scraper",
        source_name="oilprice.com",
        url="https://oilprice.com/oil-price-charts/",
        entity_name="WTI_Crude_Delayed",
        sector=Sector.ENERGY,
        unit="barrel",
        price_paths=("wti_price.value", "price.value", "price"),
        change_paths=("wti_percent_change", "price_change_percent"),
        extraction_prompt=(
            "Extract the benchmark name, price, unit, and percent change for each "
            "crude oil and refined product listed."
        ),
    ),
    "gold_scraper": ScrapedSource(
        collector_id="gold_scraper",
        source_name="investing.com",
        url="https://www.investing.com/commodities/gold",
        entity_name="Gold",
        sector=Sector.METALS,
        unit="troy_oz",
        price_paths=("price.value", "price", "current_price", "last"),
        change_paths=("price_change_percent", "change_pct", "daily_change"),
        extraction_prompt=(
            "Extract the current gold price per troy ounce, the daily percent change, "
            "and today's high and low."
        ),
    ),
    "aluminum_scraper": ScrapedSource(
        collector_id="aluminum_scraper",
        source_name="investing.com",
        url="https://www.investing.com/commodities/aluminum",
        entity_name="Aluminum",
        sector=Sector.METALS,
        unit="metric_ton",
        price_paths=("price.value", "price", "current_price", "last"),
        change_paths=("price_change_percent", "change_pct", "daily_change"),
        extraction_prompt=(
            "Extract the current aluminum price per metric ton and its daily percent change."
        ),
    ),
    "natural_gas_scraper": ScrapedSource(
        collector_id="natural_gas_scraper",
        source_name="investing.com",
        url="https://www.investing.com/commodities/natural-gas",
        entity_name="Natural_Gas",
        sector=Sector.ENERGY,
        unit="mmbtu",
        price_paths=("price.value", "price", "current_price", "last"),
        change_paths=("price_change_percent", "change_pct", "daily_change"),
        extraction_prompt=(
            "Extract the current Henry Hub natural gas price per MMBtu "
            "and its daily percent change."
        ),
    ),
    "wheat_scraper": ScrapedSource(
        collector_id="wheat_scraper",
        source_name="investing.com",
        url="https://www.investing.com/commodities/us-wheat",
        entity_name="Wheat",
        sector=Sector.AGRICULTURE,
        unit="bushel",
        price_paths=("price.value", "price", "current_price", "last"),
        change_paths=("price_change_percent", "change_pct", "daily_change"),
        extraction_prompt=(
            "Extract the current CBOT wheat futures price per bushel and its daily percent change."
        ),
    ),
    "corn_scraper": ScrapedSource(
        collector_id="corn_scraper",
        source_name="investing.com",
        url="https://www.investing.com/commodities/us-corn",
        entity_name="Corn",
        sector=Sector.AGRICULTURE,
        unit="bushel",
        price_paths=("price.value", "price", "current_price", "last"),
        change_paths=("price_change_percent", "change_pct", "daily_change"),
        extraction_prompt=(
            "Extract the current CBOT corn futures price per bushel and its daily percent change."
        ),
    ),
    "soybeans_scraper": ScrapedSource(
        collector_id="soybeans_scraper",
        source_name="investing.com",
        url="https://www.investing.com/commodities/soybeans",
        entity_name="Soybeans",
        sector=Sector.AGRICULTURE,
        unit="bushel",
        price_paths=("price.value", "price", "current_price", "last"),
        change_paths=("price_change_percent", "change_pct", "daily_change"),
        extraction_prompt=(
            "Extract the current CBOT soybean futures price per bushel "
            "and its daily percent change."
        ),
    ),
    "steel_scraper": ScrapedSource(
        collector_id="steel_scraper",
        source_name="investing.com",
        url="https://www.investing.com/commodities/us-hrc-steel",
        entity_name="Steel_HRC_US",
        sector=Sector.METALS,
        unit="short_ton",
        price_paths=("price.value", "price", "current_price", "last"),
        change_paths=("price_change_percent", "change_pct", "daily_change"),
        extraction_prompt=(
            "Extract the current US Hot-Rolled Coil steel futures price per short ton "
            "and its daily percent change."
        ),
    ),
}


class PageRunner(Protocol):
    """Reads a page and repairs the attempt if the page has changed."""

    async def run(
        self,
        collector_id: str,
        source_name: str,
        url: str,
        description: str,
        entity_name: str,
    ) -> RunOutcome:
        """Read the page and report what came back."""
        ...


class HealthEventSink(Protocol):
    """Somewhere to record what happened during a run."""

    async def record_event(self, event: PipelineHealthEvent) -> None:
        """Append one event."""
        ...


class _DiscardingEventSink:
    """Drops health events.

    Used when no sink is supplied, so a source can be run in isolation without a
    database. Real runs pass the repository that persists the health feed.
    """

    async def record_event(self, event: PipelineHealthEvent) -> None:
        """Ignore the event.

        Args:
            event: The event that would have been recorded.
        """
        return None


def parse_scraped_price(raw: object) -> Decimal | None:
    """Read a number out of scraped display text.

    Pages quote prices for people, not programs: currency symbols, thousands
    separators, percent signs, and placeholders such as "n/a" all appear.

    Args:
        raw: The scraped value.

    Returns:
        The number, or None when the text carries no number. Returning None rather
        than zero matters: zero is a price, and a missing value is not.

    Example:
        >>> parse_scraped_price("$4,520.75")
        Decimal('4520.75')
        >>> parse_scraped_price("n/a") is None
        True
    """
    if isinstance(raw, bool) or raw is None:
        return None
    if isinstance(raw, int | float | Decimal):
        return Decimal(str(raw))
    if not isinstance(raw, str):
        return None

    match = _NUMBER_PATTERN.search(raw)
    if match is None:
        return None
    try:
        return Decimal(match.group().replace(",", "").lstrip("+"))
    except InvalidOperation:  # pragma: no cover - pattern already constrains this
        return None


def first_text(row: Mapping[str, object], dotted_paths: Sequence[str]) -> str | None:
    """Read the first path that holds usable text.

    Args:
        row: One scraped row.
        dotted_paths: Paths to try, in order.

    Returns:
        The text, stripped, or None when no path holds any.
    """
    for path in dotted_paths:
        value = first_value(row, (path,))
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def name_from_label(label: str, *, prefix: str = "") -> str | None:
    """Turn a label into a stable entity name.

    Collectors identify each part of a page by the link that describes it, so the name has to
    be read out of a URL such as
    ``.../terminal/fbx-03-china-to-north-america-east-coast/``. The last path segment carries
    the meaning; the code at its start is folded into the prefix so the result reads as
    ``FBX03_China_to_North_America_East_Coast``.

    Names must be stable across runs, because they are the key a price history is stored
    under. Anything derived from position on the page would not be.

    Args:
        label: The row's label, usually a URL.
        prefix: Prepended to the result, naming the family the part belongs to.

    Returns:
        The name, or None when the label carries nothing usable.
    """
    text = label.strip().strip("/")
    if not text:
        return None

    segment = text.rsplit("/", 1)[-1] if "/" in text else text
    words = [word for word in re.split(r"[-_\s]+", segment) if word]
    if not words:
        return None

    prefix_lower = prefix.lower()
    # A slug usually repeats the family and its number, as in "fbx-03-china-to-...". Folding
    # those into the prefix avoids a name that says the same thing twice.
    if prefix and words and words[0].lower() == prefix_lower:
        words = words[1:]
        if words and words[0].isdigit():
            prefix = f"{prefix}{words[0]}"
            words = words[1:]
    if not words:
        return prefix or None

    # Small joining words stay lowercase, so a lane reads as "China_to_North_America" rather
    # than "China_To_North_America".
    titled = "_".join(
        word if word in {"to", "and", "of"} else word[:1].upper() + word[1:] for word in words
    )
    return f"{prefix}_{titled}" if prefix else titled


class ScrapedPriceIngestor:
    """Collects one page's price, repairing the collector if the page changed."""

    def __init__(
        self,
        context: IngestionContext,
        source: ScrapedSource,
        runner: PageRunner | None = None,
        events: HealthEventSink | None = None,
    ) -> None:
        """Create the ingestor.

        Args:
            context: Shared HTTP client and settings.
            source: Description of the page to read.
            runner: Reads the page. Injected so tests exercise the mapping without a
                scraping provider or a model; defaults to the self-healing reader.
            events: Where health events are recorded. Defaults to discarding them, which
                keeps a source runnable in isolation.
        """
        self._source = source
        self.source_id = source.collector_id
        self.source_name = source.source_name
        self._settings = context.settings
        self._studio_collector = (
            context.settings.collector_for(source.collector_id)
            if source.requires_unlocking
            else None
        )

        drafter: InstructionDrafter = GeminiInstructionDrafter(
            GeminiClient(
                http=context.http,
                api_key=context.settings.gemini_api_key.get_secret_value(),
                model=context.settings.gemini_model,
                daily_call_cap=context.settings.gemini_daily_call_cap,
            )
        )
        # A run started by the collection service passes its event store on the context, so
        # a detected change and its repair are recorded rather than lost.
        sink = events or context.events or _DiscardingEventSink()

        if source.requires_unlocking:
            # A site that blocks automated readers is collected by a Scraper Studio
            # collector, which owns the interaction and parsing and can be healed in place.
            self._studio_runner: SelfHealingStudioRunner | None = SelfHealingStudioRunner(
                api=ScraperStudioClient(
                    http=context.http,
                    api_key=context.settings.brightdata_api_key.get_secret_value(),
                ),
                events=sink,
                drafter=drafter,
                auto_approve_repairs=context.settings.brightdata_auto_approve_heal,
                required_fields=source.required_paths,
            )
            self._page_runner: PageRunner | None = None
        else:
            self._studio_runner = None
            self._page_runner = runner or SelfHealingPageRunner(
                fetcher=DirectPageFetcher(context.http),
                reader=GeminiPageExtractor(
                    GeminiClient(
                        http=context.http,
                        api_key=context.settings.gemini_api_key.get_secret_value(),
                        model=context.settings.gemini_model,
                        daily_call_cap=context.settings.gemini_daily_call_cap,
                    )
                ),
                events=sink,
                auto_approve_repairs=context.settings.brightdata_auto_approve_heal,
                required_fields=source.required_paths,
            )
        # A runner passed in by a test replaces whichever one this source would use.
        if runner is not None:
            self._injected_runner: PageRunner | None = runner
        else:
            self._injected_runner = None

    @property
    def is_configured(self) -> bool:
        """Whether this source can run.

        Returns:
            True when the source reads a page directly, or when a Scraper Studio collector
            has been built for it and named in configuration. A source with no collector is
            skipped rather than run, because there is nothing to run.
        """
        if not self._source.requires_unlocking:
            return True
        return self._studio_collector is not None

    async def ingest(self) -> IngestionResult:
        """Collect the source and return price records.

        Returns:
            One price per usable row. Empty when the source could not be collected:
            showing a stale value with a staleness badge is better than inventing a fresh
            one.
        """
        outcome = await self._collect()
        observed_at = datetime.now(UTC)
        return IngestionResult(
            source_name=self.source_name,
            prices=tuple(self._to_prices(outcome.rows, observed_at)),
        )

    async def _collect(self) -> RunOutcome:
        """Run whichever collection strategy this source uses.

        Returns:
            What the run produced.
        """
        if self._injected_runner is not None:
            return await self._injected_runner.run(
                collector_id=self._source.collector_id,
                source_name=self._source.source_name,
                url=self._source.url,
                description=self._source.extraction_prompt,
                entity_name=self._source.entity_name,
            )

        if self._studio_runner is not None and self._studio_collector is not None:
            return await self._studio_runner.run(
                collector_id=self._studio_collector,
                source_name=self._source.source_name,
                url=self._source.url,
            )

        if self._page_runner is not None:
            return await self._page_runner.run(
                collector_id=self._source.collector_id,
                source_name=self._source.source_name,
                url=self._source.url,
                description=self._source.extraction_prompt,
                entity_name=self._source.entity_name,
            )

        return RunOutcome(rows=[], healed=False, reason="no collector is configured")

    def _to_prices(
        self,
        rows: Sequence[Mapping[str, object]],
        observed_at: datetime,
    ) -> list[CommodityPrice]:
        """Convert scraped rows into price records.

        Args:
            rows: Rows the collector produced.
            observed_at: When the page was read. Scraped pages show a live value
                without saying when it was published, so the read time is the only
                honest timestamp available.

        Returns:
            One price per distinct value read. A page listing many trade lanes or
            benchmarks repeats the headline figure on every row, so identical values are
            collected once: storing each copy would write a dozen identical records and
            report a dozen prices collected, which misleads in both the count and the feed.
            Where a source declares a per-row series as well, each row's own value is stored
            under its own name, so a reader can see which part moved.
        """
        prices: list[CommodityPrice] = []
        seen: set[tuple[Decimal, Decimal | None]] = set()
        for row in rows:
            price = parse_scraped_price(first_value(row, self._source.price_paths))
            if price is not None:
                change = parse_scraped_price(first_value(row, self._source.change_paths))
                if (price, change) not in seen:
                    seen.add((price, change))
                    prices.append(
                        self._price_record(
                            entity_name=self._source.entity_name,
                            price=price,
                            change=change,
                            observed_at=observed_at,
                        )
                    )

            series = self._series_record(row, observed_at)
            if series is not None:
                prices.append(series)
        return prices

    def _series_record(
        self,
        row: Mapping[str, object],
        observed_at: datetime,
    ) -> CommodityPrice | None:
        """Read one row's own value, if the source publishes parts as well as a headline.

        The change is deliberately not carried across: on the freight page every row repeats
        the same percentage regardless of which lane it describes, so attaching it to each
        lane would state a move that was never measured for that lane.

        Args:
            row: One scraped row.
            observed_at: When the page was read.

        Returns:
            The part's price, or None when this source has no parts or the row has no name.
        """
        if not self._source.collects_a_series:
            return None

        value = parse_scraped_price(first_value(row, self._source.series_value_paths))
        if value is None:
            return None

        label = first_text(row, self._source.series_label_paths)
        if label is None:
            return None

        name = name_from_label(label, prefix=self._source.series_name_prefix)
        if name is None:
            return None

        return self._price_record(
            entity_name=name,
            price=value,
            change=None,
            observed_at=observed_at,
        )

    def _price_record(
        self,
        *,
        entity_name: str,
        price: Decimal,
        change: Decimal | None,
        observed_at: datetime,
    ) -> CommodityPrice:
        """Build one stored price, with its provenance attached.

        Args:
            entity_name: What the value is called.
            price: The value.
            change: The percentage change, when the source reported one for this value.
            observed_at: When the page was read.

        Returns:
            The record.
        """
        return CommodityPrice(
            entity_name=entity_name,
            sector=self._source.sector,
            price=price,
            currency=self._source.currency,
            unit=self._source.unit,
            pct_change_1d=change,
            recorded_at=observed_at,
            source_name=self._source.source_name,
            source_url=self._source.url,
            ingestion_method=IngestionMethod.BRIGHTDATA_SCRAPE,
        )


def _first_value(
    row: Mapping[str, object],
    field_names: Sequence[str],
    parse: Callable[[object], Decimal | None] = parse_scraped_price,
) -> Decimal | None:
    """Read the first field that holds a usable number.

    Scrapers do not agree on field names, so the known spellings are tried in turn.

    Args:
        row: One scraped row.
        field_names: Field names to try, in order.
        parse: Parser to apply to the raw value.

    Returns:
        The parsed number, or None when no field held one.
    """
    for name in field_names:
        if name in row:
            value = parse(row[name])
            if value is not None:
                return value
    return None


def _register_scraped_sources() -> None:
    """Register every described source so the scheduler can discover it."""
    for source_id, source in SCRAPED_SOURCES.items():

        def build(
            context: IngestionContext,
            source: ScrapedSource = source,
        ) -> ScrapedPriceIngestor:
            """Build one scraped source.

            Args:
                context: Shared dependencies.
                source: The page description, bound per registration so each
                    registered factory keeps its own source rather than sharing the
                    loop variable.

            Returns:
                A ready-to-run source.
            """
            return ScrapedPriceIngestor(context, source=source)

        default_registry.register(source_id, build)


_register_scraped_sources()
