"""Tests that the shipped sources are discoverable without a hard-coded list."""

from __future__ import annotations

from collections.abc import Mapping

import pytest

from shadow_cpi.config import build_settings
from shadow_cpi.ingestion.base import DataSourceIngestor, IngestionContext
from shadow_cpi.ingestion.official import (
    EiaPetroleumSpotIngestor,
    SecThirteenFIngestor,
    UsdaGrainPriceIngestor,
)
from shadow_cpi.ingestion.registry import default_registry

SETTINGS = build_settings(
    {
        "GEMINI_API_KEY": "test-gemini-key",
        "BRIGHTDATA_API_KEY": "test-brightdata-key",
        "NEO4J_PASSWORD": "test-neo4j-password",
        "CRON_SECRET": "test-cron-secret",
    }
)


class UnusedHttpClient:
    """Fails loudly if a request is attempted; building a source must not fetch."""

    async def get_json(
        self,
        url: str,
        params: Mapping[str, str | int] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> object:
        raise AssertionError("constructing a source must not make requests")

    async def get_text(
        self,
        url: str,
        params: Mapping[str, str | int] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> str:
        raise AssertionError("constructing a source must not make requests")


def _context() -> IngestionContext:
    return IngestionContext(http=UnusedHttpClient(), settings=SETTINGS)


def test_every_official_source_registers_itself() -> None:
    assert set(default_registry.source_ids()) >= {
        "eia_petroleum_spot",
        "usda_grain_prices",
        "sec_edgar_13f",
    }


@pytest.mark.parametrize(
    ("source_id", "expected_type"),
    [
        ("eia_petroleum_spot", EiaPetroleumSpotIngestor),
        ("usda_grain_prices", UsdaGrainPriceIngestor),
        ("sec_edgar_13f", SecThirteenFIngestor),
    ],
)
def test_each_source_can_be_built_from_its_identifier(source_id: str, expected_type: type) -> None:
    built = default_registry.build(source_id, _context())

    assert isinstance(built, expected_type)


def test_registry_builds_every_source_in_one_call() -> None:
    """This is the call a scheduled run makes; new sources need no change to it."""
    built = default_registry.build_all(_context())

    assert len(built) == len(default_registry.source_ids())


def test_every_source_satisfies_the_shared_interface() -> None:
    for ingestor in default_registry.build_all(_context()):
        assert isinstance(ingestor, DataSourceIngestor)
        assert ingestor.source_id
        assert ingestor.source_name
