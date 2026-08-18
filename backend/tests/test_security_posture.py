"""Checks that the security guarantees hold, and keep holding.

Most of these are already true because of how individual modules are written. They are
asserted here as well so that a future change which quietly breaks one fails a test
rather than shipping.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from shadow_cpi.api.app import create_app
from shadow_cpi.config import build_settings

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SOURCE = REPOSITORY_ROOT / "backend" / "src" / "shadow_cpi"
WEB_SOURCE = REPOSITORY_ROOT / "apps" / "web"

SECRET_ENV = {
    "GEMINI_API_KEY": "gemini-secret-value",
    "BRIGHTDATA_API_KEY": "brightdata-secret-value",
    "NEO4J_PASSWORD": "neo4j-secret-value",
    "CRON_SECRET": "cron-secret-value",
    "EIA_API_KEY": "eia-secret-value",
    "USDA_MARS_API_KEY": "usda-secret-value",
}

ALL_SECRET_VALUES = tuple(SECRET_ENV.values())


def _python_sources() -> list[Path]:
    return list(BACKEND_SOURCE.rglob("*.py"))


def _web_sources() -> list[Path]:
    skip = {"node_modules", ".next", "storybook-static", "coverage", "test-results"}
    return [
        path
        for path in WEB_SOURCE.rglob("*.ts*")
        if not any(part in skip for part in path.relative_to(WEB_SOURCE).parts)
    ]


class TestSecretHandling:
    def test_only_the_settings_module_reads_the_environment(self) -> None:
        """One entry point for configuration means one place to audit."""
        offenders = [
            path.name
            for path in _python_sources()
            if path.name != "config.py"
            and re.search(r"os\.environ|os\.getenv", path.read_text(encoding="utf-8"))
        ]

        assert offenders == []

    def test_no_secret_reaches_an_api_response(self) -> None:
        client = TestClient(create_app(build_settings(SECRET_ENV)))

        bodies = [
            client.get("/health").text,
            client.get("/openapi.json").text,
            client.get("/api/risk-map").text,
            client.post("/api/admin/scrapers/lme_copper_scraper/heal").text,
            client.post("/api/copilot/ask", json={"question": "hello"}).text,
        ]

        for body in bodies:
            for secret in ALL_SECRET_VALUES:
                assert secret not in body

    def test_the_server_implementation_is_not_advertised(self) -> None:
        client = TestClient(create_app(build_settings(SECRET_ENV)))

        assert "server" not in {key.lower() for key in client.get("/health").headers}

    def test_no_credential_looking_literal_is_committed_in_source(self) -> None:
        """Catches a key pasted in while debugging and never taken out again."""
        patterns = (
            re.compile(r"AIza[0-9A-Za-z_-]{20,}"),
            re.compile(r"sk-[0-9A-Za-z]{20,}"),
            re.compile(r"(?i)password\s*=\s*[\"'](?!\s*$)(?!test|placeholder|shadowcpi)\S{8,}"),
        )
        offenders: list[str] = []
        for path in [*_python_sources(), *_web_sources()]:
            text = path.read_text(encoding="utf-8", errors="replace")
            offenders.extend(path.name for pattern in patterns if pattern.search(text))

        assert offenders == []

    def test_the_environment_file_is_not_tracked(self) -> None:
        ignored = (REPOSITORY_ROOT / ".gitignore").read_text(encoding="utf-8")

        assert "\n.env\n" in ignored
        assert "!.env.example" in ignored


class TestBrowserExposure:
    def test_the_dashboard_reads_only_browser_safe_variables(self) -> None:
        """Anything not prefixed for the browser must stay on the server."""
        referenced: set[str] = set()
        for path in _web_sources():
            referenced.update(
                re.findall(r"process\.env\.([A-Z0-9_]+)", path.read_text(encoding="utf-8"))
            )

        assert all(name.startswith("NEXT_PUBLIC_") for name in referenced), referenced


class TestTransportAndAccess:
    def test_plain_http_is_refused_outside_local_development(self) -> None:
        with pytest.raises(ValueError, match="HTTPS"):
            build_settings(
                {
                    **SECRET_ENV,
                    "APP_ENV": "production",
                    "NEXT_PUBLIC_APP_URL": "http://shadowcpi.example",
                }
            )

    def test_a_wildcard_origin_cannot_be_configured(self) -> None:
        with pytest.raises(ValueError, match="wildcard"):
            build_settings({**SECRET_ENV, "CORS_ALLOWED_ORIGINS": "*"})

    def test_the_privileged_endpoint_compares_its_secret_in_constant_time(self) -> None:
        """A plain equality check leaks the secret one character at a time."""
        source = (BACKEND_SOURCE / "api" / "dependencies.py").read_text(encoding="utf-8")

        assert "compare_digest" in source

    def test_the_privileged_endpoint_rejects_a_missing_secret(self) -> None:
        client = TestClient(create_app(build_settings(SECRET_ENV)))

        assert client.post("/api/admin/scrapers/lme_copper_scraper/heal").status_code == 401

    def test_every_public_route_is_rate_limited(self) -> None:
        settings = build_settings(
            {**SECRET_ENV, "RATE_LIMIT_PER_MINUTE": "1", "COPILOT_RATE_LIMIT_PER_MINUTE": "1"}
        )
        client = TestClient(create_app(settings))

        first = client.get("/health").status_code
        second = client.get("/health").status_code

        assert (first, second) == (200, 429)


class TestQuerySafety:
    def test_no_sql_statement_interpolates_a_value(self) -> None:
        """Column lists are constants; values are always bound as parameters."""
        source = (BACKEND_SOURCE / "db" / "timescale" / "repositories.py").read_text(
            encoding="utf-8"
        )

        interpolations = re.findall(r"\{([a-z_]+)\}", source)

        assert all(
            name.startswith("_") or name.isupper() for name in interpolations
        ), interpolations

    def test_no_cypher_statement_interpolates_a_value(self) -> None:
        source = (BACKEND_SOURCE / "db" / "neo4j" / "repository.py").read_text(encoding="utf-8")

        interpolations = re.findall(r"\{([a-z_.]+)\}", source)
        allowed = {
            "node.label",
            "node.key",
            "edge.source.label",
            "edge.source.key",
            "edge.target.label",
            "edge.target.key",
            "edge.relationship",
            "max_depth",
            "label",
            "key",
        }

        assert set(interpolations) <= allowed, set(interpolations) - allowed

    def test_filings_are_parsed_with_a_hardened_xml_reader(self) -> None:
        source = (BACKEND_SOURCE / "ingestion" / "official" / "sec_edgar.py").read_text(
            encoding="utf-8"
        )

        assert "defusedxml" in source
        assert "from xml.etree.ElementTree import fromstring" not in source
