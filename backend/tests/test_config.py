"""Tests for the environment-backed settings loader."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from shadow_cpi.config import Settings, build_settings

MINIMUM_ENV: dict[str, str] = {
    "GEMINI_API_KEY": "test-gemini-key",
    "BRIGHTDATA_API_KEY": "test-brightdata-key",
    "NEO4J_PASSWORD": "test-neo4j-password",
    "CRON_SECRET": "test-cron-secret",
}


def _env(**overrides: str) -> dict[str, str]:
    return {**MINIMUM_ENV, **overrides}


def test_build_settings_accepts_the_documented_minimum_env() -> None:
    settings = build_settings(_env())

    assert settings.gemini_model == "gemini-flash-latest"
    assert settings.app_env == "local"
    assert settings.api_port == 8000


def test_missing_required_secret_is_rejected() -> None:
    incomplete = _env()
    del incomplete["GEMINI_API_KEY"]

    with pytest.raises(ValidationError):
        build_settings(incomplete)


def test_optional_official_api_keys_default_to_none() -> None:
    settings = build_settings(_env())

    assert settings.eia_api_key is None
    assert settings.usda_mars_api_key is None


def test_an_optional_key_present_but_empty_counts_as_absent() -> None:
    """The example environment file ships these present and empty."""
    settings = build_settings(_env(EIA_API_KEY="", USDA_MARS_API_KEY="   "))

    assert settings.eia_api_key is None
    assert settings.usda_mars_api_key is None


def test_an_optional_key_with_a_value_is_kept() -> None:
    settings = build_settings(_env(EIA_API_KEY="real-key"))

    assert settings.eia_api_key is not None
    assert settings.eia_api_key.get_secret_value() == "real-key"


def test_secrets_are_not_exposed_in_repr_or_str() -> None:
    settings = build_settings(_env())

    rendered = f"{settings!r} {settings}"

    assert "test-gemini-key" not in rendered
    assert "test-brightdata-key" not in rendered
    assert "test-neo4j-password" not in rendered
    assert "test-cron-secret" not in rendered


def test_secret_values_are_readable_server_side() -> None:
    settings = build_settings(_env())

    assert settings.gemini_api_key.get_secret_value() == "test-gemini-key"
    assert settings.brightdata_api_key.get_secret_value() == "test-brightdata-key"


def test_cors_origins_are_parsed_from_a_comma_separated_list() -> None:
    settings = build_settings(
        _env(CORS_ALLOWED_ORIGINS="http://localhost:3000, https://shadowcpi.example ")
    )

    assert settings.cors_allowed_origins == (
        "http://localhost:3000",
        "https://shadowcpi.example",
    )


def test_wildcard_cors_origin_is_rejected() -> None:
    with pytest.raises(ValidationError, match="wildcard"):
        build_settings(_env(CORS_ALLOWED_ORIGINS="*"))


def test_empty_cors_origin_list_is_rejected() -> None:
    with pytest.raises(ValidationError):
        build_settings(_env(CORS_ALLOWED_ORIGINS="   "))


@pytest.mark.parametrize("user_agent", ["", "ShadowCPI", "ShadowCPI/1.0 (no contact)"])
def test_sec_user_agent_must_carry_a_contact_address(user_agent: str) -> None:
    """SEC asks automated clients to identify themselves with a contact address."""
    with pytest.raises(ValidationError, match="contact"):
        build_settings(_env(SEC_EDGAR_USER_AGENT=user_agent))


def test_copilot_rate_limit_must_be_stricter_than_the_general_limit() -> None:
    with pytest.raises(ValidationError, match="stricter"):
        build_settings(_env(RATE_LIMIT_PER_MINUTE="10", COPILOT_RATE_LIMIT_PER_MINUTE="20"))


@pytest.mark.parametrize("value", ["0", "-1"])
def test_daily_caps_must_be_positive(value: str) -> None:
    with pytest.raises(ValidationError):
        build_settings(_env(GEMINI_DAILY_CALL_CAP=value))


def test_unknown_app_env_is_rejected() -> None:
    with pytest.raises(ValidationError):
        build_settings(_env(APP_ENV="qa"))


def test_auto_approve_heal_parses_boolean_strings() -> None:
    disabled = build_settings(_env(BRIGHTDATA_AUTO_APPROVE_HEAL="false"))
    enabled = build_settings(_env(BRIGHTDATA_AUTO_APPROVE_HEAL="true"))

    assert disabled.brightdata_auto_approve_heal is False
    assert enabled.brightdata_auto_approve_heal is True


def test_non_local_environments_require_https_urls() -> None:
    with pytest.raises(ValidationError, match="HTTPS"):
        build_settings(
            _env(
                APP_ENV="production",
                NEXT_PUBLIC_APP_URL="http://shadowcpi.example",
                CORS_ALLOWED_ORIGINS="https://shadowcpi.example",
            )
        )


def test_production_environment_is_flagged() -> None:
    settings = build_settings(
        _env(
            APP_ENV="production",
            NEXT_PUBLIC_APP_URL="https://shadowcpi.example",
            NEXT_PUBLIC_API_URL="https://api.shadowcpi.example",
            CORS_ALLOWED_ORIGINS="https://shadowcpi.example",
        )
    )

    assert settings.is_production is True
    assert isinstance(settings, Settings)


def test_local_environment_is_not_flagged_as_production() -> None:
    assert build_settings(_env()).is_production is False


class TestCollectorMapping:
    """Which Scraper Studio collector belongs to which source."""

    def test_finds_the_collector_for_a_source(self) -> None:
        settings = build_settings(
            _env(SCRAPER_STUDIO_COLLECTORS="lme_copper_scraper=c_abc123,fbx_scraper=c_def456")
        )

        assert settings.collector_for("lme_copper_scraper") == "c_abc123"
        assert settings.collector_for("fbx_scraper") == "c_def456"

    def test_a_source_with_no_collector_has_none(self) -> None:
        settings = build_settings(_env(SCRAPER_STUDIO_COLLECTORS="lme_copper_scraper=c_abc123"))

        assert settings.collector_for("fbx_scraper") is None

    def test_no_mapping_at_all_yields_none(self) -> None:
        assert build_settings(_env()).collector_for("lme_copper_scraper") is None

    def test_spacing_around_the_pairs_is_tolerated(self) -> None:
        settings = build_settings(
            _env(SCRAPER_STUDIO_COLLECTORS=" lme_copper_scraper = c_abc123 , fbx_scraper=c_def456 ")
        )

        assert settings.collector_for("lme_copper_scraper") == "c_abc123"

    def test_a_pair_with_an_empty_collector_counts_as_absent(self) -> None:
        settings = build_settings(_env(SCRAPER_STUDIO_COLLECTORS="lme_copper_scraper="))

        assert settings.collector_for("lme_copper_scraper") is None

    def test_a_malformed_entry_is_ignored_rather_than_failing_startup(self) -> None:
        settings = build_settings(
            _env(SCRAPER_STUDIO_COLLECTORS="nonsense,lme_copper_scraper=c_abc123")
        )

        assert settings.collector_for("lme_copper_scraper") == "c_abc123"


class TestReadingFromTheRealEnvironment:
    """Settings built from the process environment, not from constructor arguments.

    This is the path every entry point actually uses, and it behaves differently:
    values arrive as strings and a field whose type is a collection gets decoded before
    any validator runs. These tests exercise that path directly, because passing a
    dictionary in bypasses it and hides real failures.
    """

    @staticmethod
    def _apply(monkeypatch: pytest.MonkeyPatch, values: dict[str, str]) -> None:
        for name, value in {**MINIMUM_ENV, **values}.items():
            monkeypatch.setenv(name, value)

    def test_a_single_origin_is_read_from_the_environment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._apply(monkeypatch, {"CORS_ALLOWED_ORIGINS": "http://localhost:3000"})

        settings = build_settings()

        assert settings.cors_allowed_origins == ("http://localhost:3000",)

    def test_several_origins_are_read_from_the_environment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._apply(
            monkeypatch,
            {"CORS_ALLOWED_ORIGINS": "http://localhost:3000, https://shadowcpi.example"},
        )

        settings = build_settings()

        assert settings.cors_allowed_origins == (
            "http://localhost:3000",
            "https://shadowcpi.example",
        )

    def test_a_wildcard_from_the_environment_is_still_refused(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._apply(monkeypatch, {"CORS_ALLOWED_ORIGINS": "*"})

        with pytest.raises(ValidationError, match="wildcard"):
            build_settings()

    def test_an_empty_optional_key_from_the_environment_counts_as_absent(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._apply(monkeypatch, {"EIA_API_KEY": ""})

        assert build_settings().eia_api_key is None

    def test_the_documented_minimum_environment_is_enough_to_start(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._apply(monkeypatch, {})

        settings = build_settings()

        assert settings.app_env == "local"
        assert settings.cors_allowed_origins == ("http://localhost:3000",)
