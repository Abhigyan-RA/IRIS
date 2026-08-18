"""Quarterly fund holdings from SEC EDGAR.

Any investment manager overseeing more than 100 million dollars must disclose its
US equity positions to the SEC every quarter, on a form called 13F. This is public
information, filed as XML, and free to read. It is the production source for
holdings data: official, no anti-bot protection, and no page layout that can break.

Reading one filing takes three requests, because that is how EDGAR is organised:

1. The filer's submission history, to find the newest 13F filing.
2. That filing's folder listing, to find the information table inside it.
3. The information table itself, which holds one row per position.

Two details are worth knowing:

- SEC asks every automated client to identify itself with a contact address, and
  throttles requests that do not. That header is sent on every request here.
- A 13F identifies each holding by issuer name and CUSIP, never by ticker. Tickers
  are resolved through SEC's own company directory, and any position that cannot be
  matched confidently is skipped rather than guessed at.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from xml.etree.ElementTree import Element

from defusedxml.ElementTree import ParseError, fromstring
from pydantic import BaseModel, ConfigDict, Field

from shadow_cpi.ingestion.base import IngestionContext, IngestionResult
from shadow_cpi.ingestion.registry import default_registry
from shadow_cpi.shared import InstitutionalHolding, normalize_cik

SOURCE_ID = "sec_edgar_13f"
SOURCE_NAME = "sec.gov"

SUBMISSIONS_URL_TEMPLATE = "https://data.sec.gov/submissions/CIK{cik}.json"
ARCHIVES_URL_TEMPLATE = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}"
TICKER_DIRECTORY_URL = "https://www.sec.gov/files/company_tickers.json"

# Filing types that contain holdings. 13F-HR is the holdings report; 13F-HR/A is
# an amendment to one.
_HOLDINGS_FORMS = ("13F-HR",)

# Company-name noise that differs between the filing and SEC's own directory.
_NAME_NOISE = re.compile(r"[^A-Z0-9 ]+")
_NAME_SUFFIXES = (
    " INCORPORATED",
    " INC",
    " CORPORATION",
    " CORP",
    " COMPANY",
    " CO",
    " LIMITED",
    " LTD",
    " PLC",
    " LP",
    " LLC",
    " CLASS A",
    " CL A",
    " COM",
)

_PERCENT_PRECISION = Decimal("0.001")


@dataclass(frozen=True, slots=True)
class TrackedFiler:
    """A fund whose filings this platform follows.

    Attributes:
        cik: The fund's SEC identifier.
        name: The fund's name, as shown in the dashboard.
    """

    cik: str
    name: str


# Funds followed by default. Widely covered managers whose positions are
# recognisable; extend the tuple to follow more.
TRACKED_FILERS: tuple[TrackedFiler, ...] = (
    TrackedFiler(cik="0001350694", name="Bridgewater Associates"),
    TrackedFiler(cik="0001067983", name="Berkshire Hathaway"),
)


@dataclass(frozen=True, slots=True)
class InformationTableRow:
    """One position from a filing's information table.

    Attributes:
        name_of_issuer: Issuer name as written in the filing.
        cusip: Security identifier used in the filing.
        value: Reported market value of the position, in US dollars.
        shares: Number of shares held.
    """

    name_of_issuer: str
    cusip: str
    value: Decimal
    shares: int


class _RecentFilings(BaseModel):
    """The parallel arrays EDGAR uses to list recent filings.

    Attributes:
        form: Filing type for each entry.
        accession_number: Filing identifier for each entry.
        report_date: Period each filing covers.
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    form: list[str] = Field(default_factory=list)
    accession_number: list[str] = Field(default_factory=list, alias="accessionNumber")
    report_date: list[str] = Field(default_factory=list, alias="reportDate")


class _Filings(BaseModel):
    """Wrapper around the recent-filings arrays.

    Attributes:
        recent: The recent filings block.
    """

    model_config = ConfigDict(extra="ignore")

    recent: _RecentFilings


class SubmissionsResponse(BaseModel):
    """A filer's submission history.

    Attributes:
        filings: The filings block, required so that a changed payload shape is
            reported rather than treated as "this filer has nothing".
    """

    model_config = ConfigDict(extra="ignore")

    filings: _Filings


def parse_information_table(xml_text: str) -> list[InformationTableRow]:
    """Read positions out of a 13F information table.

    Filings are external input, so parsing is done with a hardened parser that
    refuses document type definitions. Without that, a filing could declare nested
    entities that expand to gigabytes and exhaust memory.

    Args:
        xml_text: The information table document.

    Returns:
        One row per position that reports both a value and a share count. Rows
        missing either are skipped, since a holding with no share count cannot be
        compared between quarters.

    Raises:
        ValueError: If the document is not well-formed XML, or declares entities.
    """
    try:
        root: Element = fromstring(xml_text)
    except (ParseError, ValueError) as error:
        raise ValueError(f"Filing is not valid XML: {error}") from error

    rows: list[InformationTableRow] = []
    for entry in root.iter():
        if _tag(entry) != "infoTable":
            continue
        fields = {_tag(child): child for child in entry.iter()}
        issuer = _text(fields.get("nameOfIssuer"))
        cusip = _text(fields.get("cusip"))
        value = _decimal(_text(fields.get("value")))
        shares = _integer(_text(fields.get("sshPrnamt")))
        if not issuer or value is None or shares is None:
            continue
        rows.append(
            InformationTableRow(
                name_of_issuer=issuer,
                cusip=cusip,
                value=value,
                shares=shares,
            )
        )
    return rows


@default_registry.source(SOURCE_ID)
class SecThirteenFIngestor:
    """Reads quarterly fund holdings from SEC EDGAR."""

    source_id = SOURCE_ID
    source_name = SOURCE_NAME

    def __init__(
        self,
        context: IngestionContext,
        filers: tuple[TrackedFiler, ...] = TRACKED_FILERS,
    ) -> None:
        """Create the ingestor.

        Args:
            context: Shared HTTP client and settings.
            filers: Funds to follow. Injected so a run can be narrowed, and so
                tests do not depend on the default list.
        """
        self._http = context.http
        self._settings = context.settings
        self._filers = filers
        self._headers = {
            "User-Agent": self._settings.sec_edgar_user_agent,
            "Accept": "application/json",
        }

    @property
    def is_configured(self) -> bool:
        """Whether this source can run.

        Returns:
            Always True. SEC issues no API keys; it requires a contact string,
            which configuration already guarantees is present and valid.
        """
        return True

    async def ingest(self) -> IngestionResult:
        """Fetch the newest filing for each followed fund.

        Returns:
            One holding record per position that could be matched to a ticker,
            including the change in share count since the previous quarter where
            an earlier filing is available.

        Raises:
            pydantic.ValidationError: If a submission history does not match the
                documented shape.
        """
        tickers_by_name = await self._load_ticker_directory()
        holdings: list[InstitutionalHolding] = []

        for filer in self._filers:
            holdings.extend(await self._ingest_filer(filer, tickers_by_name))

        return IngestionResult(source_name=self.source_name, holdings=tuple(holdings))

    async def _ingest_filer(
        self,
        filer: TrackedFiler,
        tickers_by_name: dict[str, str],
    ) -> list[InstitutionalHolding]:
        """Read one fund's newest filing.

        Args:
            filer: The fund to read.
            tickers_by_name: Issuer name to ticker lookup.

        Returns:
            Holding records for that fund, or an empty list when it has filed no
            holdings report or the filing contains no readable table.
        """
        cik = normalize_cik(filer.cik)
        payload = await self._http.get_json(
            SUBMISSIONS_URL_TEMPLATE.format(cik=cik), headers=self._headers
        )
        recent = SubmissionsResponse.model_validate(payload).filings.recent
        filings = _holdings_filings(recent)
        if not filings:
            return []

        newest = filings[0]
        rows, source_url = await self._read_information_table(cik, newest.accession)
        if not rows:
            return []

        previous_shares: dict[str, int] = {}
        if len(filings) > 1:
            previous_rows, _ = await self._read_information_table(cik, filings[1].accession)
            previous_shares = _shares_by_cusip(previous_rows)

        total_value = sum((row.value for row in rows), start=Decimal(0))
        holdings: list[InstitutionalHolding] = []
        for row in rows:
            ticker = tickers_by_name.get(_normalize_company_name(row.name_of_issuer))
            if ticker is None:
                continue
            earlier = previous_shares.get(row.cusip)
            holdings.append(
                InstitutionalHolding(
                    filer_name=filer.name,
                    filer_cik=cik,
                    stock_ticker=ticker,
                    shares_held=row.shares,
                    market_value_usd=row.value,
                    pct_portfolio=_portfolio_share(row.value, total_value),
                    shares_change_qoq=None if earlier is None else row.shares - earlier,
                    quarter_end=newest.report_date,
                    source_url=source_url,
                )
            )
        return holdings

    async def _read_information_table(
        self,
        cik: str,
        accession: str,
    ) -> tuple[list[InformationTableRow], str]:
        """Find and read the information table inside one filing.

        Args:
            cik: The filer's identifier.
            accession: The filing's identifier.

        Returns:
            The parsed rows and the URL they were read from. The rows are empty
            when the filing folder holds no information table, which happens for
            filings that only reference another manager's report.
        """
        folder = ARCHIVES_URL_TEMPLATE.format(
            cik=str(int(cik)), accession=accession.replace("-", "")
        )
        listing = await self._http.get_json(f"{folder}/index.json", headers=self._headers)
        filename = _find_information_table(listing)
        if filename is None:
            return [], folder

        document_url = f"{folder}/{filename}"
        xml_text = await self._http.get_text(document_url, headers=self._headers)
        return parse_information_table(xml_text), document_url

    async def _load_ticker_directory(self) -> dict[str, str]:
        """Build an issuer-name to ticker lookup from SEC's own directory.

        Returns:
            Normalized company name mapped to ticker symbol.
        """
        payload = await self._http.get_json(TICKER_DIRECTORY_URL, headers=self._headers)
        directory: dict[str, str] = {}
        if not isinstance(payload, dict):
            return directory
        for entry in payload.values():
            if not isinstance(entry, dict):
                continue
            title = entry.get("title")
            ticker = entry.get("ticker")
            if isinstance(title, str) and isinstance(ticker, str):
                directory[_normalize_company_name(title)] = ticker.upper()
        return directory


@dataclass(frozen=True, slots=True)
class _Filing:
    """A filing worth reading.

    Attributes:
        accession: Filing identifier.
        report_date: Quarter the filing covers.
    """

    accession: str
    report_date: date


def _holdings_filings(recent: _RecentFilings) -> list[_Filing]:
    """Pick out the holdings reports from a filer's recent filings.

    Args:
        recent: The parallel arrays EDGAR returns.

    Returns:
        Holdings filings, newest quarter first.
    """
    filings: list[_Filing] = []
    for form, accession, report_date in zip(
        recent.form, recent.accession_number, recent.report_date, strict=False
    ):
        if not form.startswith(_HOLDINGS_FORMS):
            continue
        try:
            period = date.fromisoformat(report_date)
        except ValueError:
            continue
        filings.append(_Filing(accession=accession, report_date=period))
    return sorted(filings, key=lambda filing: filing.report_date, reverse=True)


def _find_information_table(listing: object) -> str | None:
    """Find the information table file in a filing folder listing.

    Args:
        listing: The folder listing EDGAR returns.

    Returns:
        The filename, or None when the folder holds no information table.
    """
    if not isinstance(listing, dict):
        return None
    directory: Any = listing.get("directory", {})
    items: Any = directory.get("item", []) if isinstance(directory, dict) else []
    names = [item["name"] for item in items if isinstance(item, dict) and "name" in item]
    for name in names:
        lowered = str(name).lower()
        if lowered.endswith(".xml") and "primary_doc" not in lowered:
            return str(name)
    return None


def _shares_by_cusip(rows: list[InformationTableRow]) -> dict[str, int]:
    """Index share counts by security identifier.

    Args:
        rows: Rows from an earlier filing.

    Returns:
        Share count per CUSIP, which is stable across quarters even when the
        issuer name is written differently.
    """
    return {row.cusip: row.shares for row in rows}


def _portfolio_share(value: Decimal, total: Decimal) -> Decimal | None:
    """Work out what share of the portfolio one position represents.

    Args:
        value: Value of the position.
        total: Total value of all reported positions.

    Returns:
        The share in percent, or None when the total is zero.
    """
    if total == 0:
        return None
    return (value / total * Decimal(100)).quantize(_PERCENT_PRECISION, rounding=ROUND_HALF_UP)


def _normalize_company_name(name: str) -> str:
    """Reduce a company name to a form that matches across sources.

    Filings write "Apple, Inc." where the directory writes "Apple Inc". Punctuation
    and legal suffixes are removed so the two meet in the middle.

    Args:
        name: Company name as published.

    Returns:
        The normalized name.
    """
    cleaned = _NAME_NOISE.sub(" ", name.upper())
    cleaned = " ".join(cleaned.split())
    changed = True
    while changed:
        changed = False
        for suffix in _NAME_SUFFIXES:
            if cleaned.endswith(suffix):
                cleaned = cleaned[: -len(suffix)].strip()
                changed = True
    return cleaned


def _tag(element: Element) -> str:
    """Return an element's tag without its namespace.

    Args:
        element: The element to inspect.

    Returns:
        The local tag name.
    """
    return element.tag.rsplit("}", maxsplit=1)[-1]


def _text(element: Element | None) -> str:
    """Return an element's trimmed text.

    Args:
        element: The element, or None when the field was absent.

    Returns:
        The text, or an empty string.
    """
    if element is None or element.text is None:
        return ""
    return element.text.strip()


def _decimal(text: str) -> Decimal | None:
    """Parse a decimal, returning None when the text is not a number.

    Args:
        text: Text to parse.

    Returns:
        The parsed value, or None.
    """
    try:
        return Decimal(text)
    except (ArithmeticError, ValueError):
        return None


def _integer(text: str) -> int | None:
    """Parse a whole number, returning None when the text is not one.

    Args:
        text: Text to parse.

    Returns:
        The parsed value, or None.
    """
    try:
        return int(Decimal(text))
    except (ArithmeticError, ValueError):
        return None
