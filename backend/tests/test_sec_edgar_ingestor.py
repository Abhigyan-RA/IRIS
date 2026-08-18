"""Tests for the SEC EDGAR 13F holdings ingestor."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from shadow_cpi.config import build_settings
from shadow_cpi.ingestion.base import IngestionContext
from shadow_cpi.ingestion.official.sec_edgar import (
    SUBMISSIONS_URL_TEMPLATE,
    TICKER_DIRECTORY_URL,
    SecThirteenFIngestor,
    TrackedFiler,
    parse_information_table,
)

BASE_ENV = {
    "GEMINI_API_KEY": "test-gemini-key",
    "BRIGHTDATA_API_KEY": "test-brightdata-key",
    "NEO4J_PASSWORD": "test-neo4j-password",
    "CRON_SECRET": "test-cron-secret",
    "SEC_EDGAR_USER_AGENT": "ShadowCPI/1.0 (dev@example.com)",
}

FILER = TrackedFiler(cik="0001350694", name="Bridgewater Associates")

TICKER_DIRECTORY = {
    "0": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"},
    "1": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
}


def _submissions(*filings: tuple[str, str, str]) -> dict[str, object]:
    """Build a submissions payload from (form, accession, reportDate) triples."""
    return {
        "cik": "1350694",
        "name": "Bridgewater Associates",
        "filings": {
            "recent": {
                "form": [form for form, _, _ in filings],
                "accessionNumber": [accession for _, accession, _ in filings],
                "reportDate": [report_date for _, _, report_date in filings],
            }
        },
    }


def _folder_index(*filenames: str) -> dict[str, object]:
    return {"directory": {"item": [{"name": name} for name in filenames]}}


def _information_table(*rows: tuple[str, str, int, int]) -> str:
    entries = "".join(
        f"""
        <infoTable>
          <nameOfIssuer>{name}</nameOfIssuer>
          <cusip>{cusip}</cusip>
          <value>{value}</value>
          <shrsOrPrnAmt><sshPrnamt>{shares}</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
        </infoTable>
        """
        for name, cusip, value, shares in rows
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">'
        f"{entries}</informationTable>"
    )


class ScriptedHttpClient:
    """Returns a canned response per URL, and records every request made."""

    def __init__(
        self,
        json_by_url: Mapping[str, object] | None = None,
        text_by_url: Mapping[str, str] | None = None,
    ) -> None:
        self._json = dict(json_by_url or {})
        self._text = dict(text_by_url or {})
        self.requests: list[tuple[str, Mapping[str, str]]] = []

    async def get_json(
        self,
        url: str,
        params: Mapping[str, str | int] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> object:
        self.requests.append((url, dict(headers or {})))
        for candidate, payload in self._json.items():
            if url.startswith(candidate) or url == candidate:
                return payload
        raise AssertionError(f"unexpected JSON request: {url}")

    async def get_text(
        self,
        url: str,
        params: Mapping[str, str | int] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> str:
        self.requests.append((url, dict(headers or {})))
        for candidate, body in self._text.items():
            if url.startswith(candidate) or url == candidate:
                return body
        raise AssertionError(f"unexpected text request: {url}")


def _client(
    *,
    submissions: object | None = None,
    folder: object | None = None,
    table: str | None = None,
    previous_folder: object | None = None,
    previous_table: str | None = None,
) -> ScriptedHttpClient:
    accession_folder = "https://www.sec.gov/Archives/edgar/data/1350694/000135069426000012"
    previous_accession_folder = "https://www.sec.gov/Archives/edgar/data/1350694/000135069426000008"
    json_by_url: dict[str, object] = {TICKER_DIRECTORY_URL: TICKER_DIRECTORY}
    if submissions is not None:
        json_by_url[SUBMISSIONS_URL_TEMPLATE.format(cik="0001350694")] = submissions
    if folder is not None:
        json_by_url[f"{accession_folder}/index.json"] = folder
    if previous_folder is not None:
        json_by_url[f"{previous_accession_folder}/index.json"] = previous_folder

    text_by_url: dict[str, str] = {}
    if table is not None:
        text_by_url[f"{accession_folder}/infotable.xml"] = table
    if previous_table is not None:
        text_by_url[f"{previous_accession_folder}/infotable.xml"] = previous_table

    return ScriptedHttpClient(json_by_url, text_by_url)


def _context(client: ScriptedHttpClient, **env: str) -> IngestionContext:
    return IngestionContext(http=client, settings=build_settings({**BASE_ENV, **env}))


def _healthy_client() -> ScriptedHttpClient:
    return _client(
        submissions=_submissions(
            ("13F-HR", "0001350694-26-000012", "2026-06-30"),
            ("13F-HR", "0001350694-26-000008", "2026-03-31"),
        ),
        folder=_folder_index("primary_doc.xml", "infotable.xml"),
        table=_information_table(("NVIDIA CORP", "67066G104", 144_000_000, 1_200_000)),
        previous_folder=_folder_index("primary_doc.xml", "infotable.xml"),
        previous_table=_information_table(("NVIDIA CORP", "67066G104", 120_000_000, 1_050_000)),
    )


class TestIdentification:
    def test_source_is_identified_for_schedules_and_logs(self) -> None:
        ingestor = SecThirteenFIngestor(_context(_healthy_client()))

        assert ingestor.source_id == "sec_edgar_13f"
        assert ingestor.source_name == "sec.gov"

    def test_source_needs_no_api_key(self) -> None:
        """SEC asks for a contact string instead of issuing keys."""
        assert SecThirteenFIngestor(_context(_healthy_client())).is_configured is True

    @pytest.mark.asyncio
    async def test_every_request_identifies_us_by_contact_address(self) -> None:
        client = _healthy_client()

        await SecThirteenFIngestor(_context(client), filers=(FILER,)).ingest()

        assert client.requests
        for _, headers in client.requests:
            assert headers["User-Agent"] == "ShadowCPI/1.0 (dev@example.com)"


class TestHealthyFiling:
    @pytest.mark.asyncio
    async def test_maps_a_holding_to_a_record(self) -> None:
        result = await SecThirteenFIngestor(_context(_healthy_client()), filers=(FILER,)).ingest()

        holding = result.holdings[0]
        assert holding.filer_name == "Bridgewater Associates"
        assert holding.filer_cik == "0001350694"
        assert holding.stock_ticker == "NVDA"
        assert holding.shares_held == 1_200_000
        assert holding.market_value_usd == Decimal("144000000")

    @pytest.mark.asyncio
    async def test_quarter_end_comes_from_the_filing(self) -> None:
        result = await SecThirteenFIngestor(_context(_healthy_client()), filers=(FILER,)).ingest()

        assert result.holdings[0].quarter_end == date(2026, 6, 30)

    @pytest.mark.asyncio
    async def test_quarterly_change_is_computed_against_the_previous_filing(self) -> None:
        result = await SecThirteenFIngestor(_context(_healthy_client()), filers=(FILER,)).ingest()

        assert result.holdings[0].shares_change_qoq == 150_000

    @pytest.mark.asyncio
    async def test_portfolio_share_is_computed_from_reported_values(self) -> None:
        client = _client(
            submissions=_submissions(("13F-HR", "0001350694-26-000012", "2026-06-30")),
            folder=_folder_index("infotable.xml"),
            table=_information_table(
                ("NVIDIA CORP", "67066G104", 75_000_000, 1_200_000),
                ("APPLE INC", "037833100", 25_000_000, 500_000),
            ),
        )

        result = await SecThirteenFIngestor(_context(client), filers=(FILER,)).ingest()

        by_ticker = {holding.stock_ticker: holding for holding in result.holdings}
        assert by_ticker["NVDA"].pct_portfolio == Decimal("75.000")
        assert by_ticker["AAPL"].pct_portfolio == Decimal("25.000")

    @pytest.mark.asyncio
    async def test_records_the_filing_it_read(self) -> None:
        result = await SecThirteenFIngestor(_context(_healthy_client()), filers=(FILER,)).ingest()

        source_url = result.holdings[0].source_url
        assert source_url is not None
        assert "Archives/edgar/data/1350694" in source_url

    @pytest.mark.asyncio
    async def test_a_new_position_has_no_previous_quarter_to_compare(self) -> None:
        client = _client(
            submissions=_submissions(("13F-HR", "0001350694-26-000012", "2026-06-30")),
            folder=_folder_index("infotable.xml"),
            table=_information_table(("NVIDIA CORP", "67066G104", 144_000_000, 1_200_000)),
        )

        result = await SecThirteenFIngestor(_context(client), filers=(FILER,)).ingest()

        assert result.holdings[0].shares_change_qoq is None

    @pytest.mark.asyncio
    async def test_a_filer_with_no_thirteen_f_filings_is_skipped(self) -> None:
        client = _client(
            submissions=_submissions(("10-K", "0001350694-26-000001", "2026-06-30")),
        )

        result = await SecThirteenFIngestor(_context(client), filers=(FILER,)).ingest()

        assert result.record_count == 0

    @pytest.mark.asyncio
    async def test_issuers_that_cannot_be_matched_to_a_ticker_are_skipped(self) -> None:
        """13F filings identify issuers by name and CUSIP, never by ticker."""
        client = _client(
            submissions=_submissions(("13F-HR", "0001350694-26-000012", "2026-06-30")),
            folder=_folder_index("infotable.xml"),
            table=_information_table(
                ("SOME PRIVATE FUND LP", "999999999", 5_000_000, 1_000),
                ("NVIDIA CORP", "67066G104", 144_000_000, 1_200_000),
            ),
        )

        result = await SecThirteenFIngestor(_context(client), filers=(FILER,)).ingest()

        assert [holding.stock_ticker for holding in result.holdings] == ["NVDA"]

    @pytest.mark.asyncio
    async def test_issuer_names_match_despite_punctuation_and_suffixes(self) -> None:
        client = _client(
            submissions=_submissions(("13F-HR", "0001350694-26-000012", "2026-06-30")),
            folder=_folder_index("infotable.xml"),
            table=_information_table(("Apple, Inc.", "037833100", 25_000_000, 500_000)),
        )

        result = await SecThirteenFIngestor(_context(client), filers=(FILER,)).ingest()

        assert result.holdings[0].stock_ticker == "AAPL"


class TestMalformedFiling:
    @pytest.mark.asyncio
    async def test_a_submissions_payload_missing_its_filings_is_rejected(self) -> None:
        client = _client(submissions={"cik": "1350694"})

        with pytest.raises(ValidationError):
            await SecThirteenFIngestor(_context(client), filers=(FILER,)).ingest()

    @pytest.mark.asyncio
    async def test_a_filing_folder_without_an_information_table_is_skipped(self) -> None:
        client = _client(
            submissions=_submissions(("13F-HR", "0001350694-26-000012", "2026-06-30")),
            folder=_folder_index("primary_doc.xml", "cover.txt"),
        )

        result = await SecThirteenFIngestor(_context(client), filers=(FILER,)).ingest()

        assert result.record_count == 0

    @pytest.mark.asyncio
    async def test_rows_missing_a_share_count_are_skipped(self) -> None:
        table = (
            '<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">'
            "<infoTable><nameOfIssuer>NVIDIA CORP</nameOfIssuer><cusip>67066G104</cusip>"
            "<value>144000000</value></infoTable>"
            "</informationTable>"
        )
        client = _client(
            submissions=_submissions(("13F-HR", "0001350694-26-000012", "2026-06-30")),
            folder=_folder_index("infotable.xml"),
            table=table,
        )

        result = await SecThirteenFIngestor(_context(client), filers=(FILER,)).ingest()

        assert result.record_count == 0


class TestInformationTableParser:
    def test_reads_issuer_value_and_share_count(self) -> None:
        rows = parse_information_table(
            _information_table(("NVIDIA CORP", "67066G104", 144_000_000, 1_200_000))
        )

        assert rows[0].name_of_issuer == "NVIDIA CORP"
        assert rows[0].cusip == "67066G104"
        assert rows[0].value == Decimal("144000000")
        assert rows[0].shares == 1_200_000

    def test_an_empty_table_returns_no_rows(self) -> None:
        rows = parse_information_table(
            '<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable"/>'
        )

        assert rows == []

    def test_malformed_xml_is_reported_clearly(self) -> None:
        with pytest.raises(ValueError, match="XML"):
            parse_information_table("<informationTable><infoTable>")

    def test_an_entity_expansion_attack_is_refused(self) -> None:
        """Filings are external input, so the parser must not expand entities."""
        payload = (
            '<?xml version="1.0"?>'
            "<!DOCTYPE lolz [<!ENTITY lol 'lol'>"
            "<!ENTITY lol2 '&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;'>]>"
            "<informationTable><infoTable><nameOfIssuer>&lol2;</nameOfIssuer></infoTable>"
            "</informationTable>"
        )

        with pytest.raises(ValueError, match="XML"):
            parse_information_table(payload)
