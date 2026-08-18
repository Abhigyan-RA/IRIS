"""Application settings, loaded and validated from environment variables.

Why this module exists
----------------------
Every credential and tunable value the backend needs enters the process here,
and nowhere else. No other module reads ``os.environ``. That gives us three
things:

1. A single, readable list of everything the service needs to run.
2. Fail-fast startup: a missing or nonsensical value raises immediately, with a
   clear message, instead of causing a confusing failure hours later mid-job.
3. Testability: tests build settings from a plain dictionary, so they never
   mutate global process state or depend on the developer's machine.

Secrets are wrapped in ``SecretStr``. Printing a ``Settings`` object, logging it,
or including it in an error response renders ``**********`` instead of the real
value, which makes accidental credential leaks much harder.

Example:
    >>> settings = build_settings({
    ...     "GEMINI_API_KEY": "key",
    ...     "BRIGHTDATA_API_KEY": "key",
    ...     "NEO4J_PASSWORD": "password",
    ...     "CRON_SECRET": "secret",
    ... })
    >>> settings.app_env
    'local'
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal, Self

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

AppEnv = Literal["local", "staging", "production"]

# A comma-separated list of origins, read from a single environment variable.
#
# NoDecode matters: without it, the settings loader sees a collection type and tries to
# parse the value as JSON before any validator runs, so a perfectly ordinary
# "CORS_ALLOWED_ORIGINS=http://localhost:3000" fails to start the service with a JSON
# decode error. NoDecode hands the raw string to the validator below instead.
OriginList = Annotated[tuple[str, ...], NoDecode]

# Which Scraper Studio collector belongs to which source, written as a comma-separated
# list of pairs:
#
#     SCRAPER_STUDIO_COLLECTORS=lme_copper_scraper=c_abc123,fbx_scraper=c_def456
#
# A collector is a scraper built in Scraper Studio; its identifier is the stable handle
# used to run it, heal it, and schedule it. One variable holding a mapping keeps a growing
# list of sources from turning into a growing list of environment variables.
CollectorMap = Annotated[str, NoDecode]

# A usable SEC User-Agent needs at least a product token and a contact part,
# for example "ShadowCPI/1.0 (you@example.com)".
_MIN_SEC_USER_AGENT_PARTS = 2


class Settings(BaseSettings):
    """All configuration for the backend, validated once at startup.

    Each field below maps to an environment variable of the same name in upper
    case: ``gemini_api_key`` reads ``GEMINI_API_KEY``. Every variable is
    documented with a comment and a placeholder in the ``.env.example`` file at
    the repository root, which is the reference for what you need to run this.

    Attributes:
        gemini_api_key: API key for Gemini, the model used for normalization,
            explanations, and the copilot answers.
        gemini_model: Model name or alias to call. The default alias tracks the
            current recommended Flash model; pin an explicit version when you
            need byte-for-byte reproducible output.
        gemini_daily_call_cap: Maximum model calls per day. Guards against a
            runaway loop quietly running up a bill.
        brightdata_api_key: API key for the scraping provider used for sources
            that have no official API.
        scraper_studio_collectors: Which Scraper Studio collector belongs to which source,
            as ``source=collector`` pairs. A source with no collector is skipped, in the
            same way as a source whose optional API key is absent.
        brightdata_auto_approve_heal: When true, an AI-proposed repair to a
            broken scraper is applied automatically. When false, a human
            approves it first, which is the safer production choice.
        brightdata_daily_run_cap: Maximum scraper runs per day.
        database_url: PostgreSQL/TimescaleDB connection string for price history.
        neo4j_uri: Bolt URI of the graph database holding supply-chain links.
        neo4j_user: Graph database username.
        neo4j_password: Graph database password.
        redis_url: Redis connection string, used for rate limiting and for
            preventing two scheduler instances running the same job twice.
        eia_api_key: Optional free key for the US Energy Information
            Administration API. Without it, energy data falls back to scraping.
        usda_mars_api_key: Optional free key for the USDA market news API.
            Without it, agriculture data falls back to scraping.
        sec_edgar_user_agent: Contact string sent with every SEC EDGAR request.
            SEC's fair-access policy requires identifying yourself, and throttles
            or blocks anonymous traffic.
        next_public_app_url: Public URL of the dashboard. Safe to expose to the
            browser, which is what the ``NEXT_PUBLIC_`` prefix signals.
        next_public_api_url: Public URL of this API, as the browser sees it.
        cron_secret: Shared secret that scheduled jobs must present to trigger
            privileged endpoints.
        app_env: Which environment this process is running in.
        api_port: TCP port the API listens on.
        cors_allowed_origins: Exact browser origins allowed to call this API.
            Wildcards are rejected on purpose.
        rate_limit_per_minute: Requests per minute allowed per client IP.
        copilot_rate_limit_per_minute: Stricter limit for the copilot endpoint,
            because each of those requests costs money in model usage.
        log_level: Minimum severity to log.
    """

    model_config = SettingsConfigDict(
        # The env file is loaded by the process entrypoint, not here, so that
        # tests are never influenced by a developer's local .env file.
        env_file=None,
        case_sensitive=False,
        extra="ignore",
    )

    # --- AI ---
    gemini_api_key: SecretStr
    gemini_model: str = "gemini-flash-latest"
    gemini_daily_call_cap: int = Field(default=500, gt=0)

    # --- Scraping provider ---
    brightdata_api_key: SecretStr
    scraper_studio_collectors: CollectorMap = ""
    brightdata_auto_approve_heal: bool = True
    brightdata_daily_run_cap: int = Field(default=200, gt=0)

    # --- Databases ---
    database_url: str = "postgresql://shadowcpi:shadowcpi@localhost:5432/shadowcpi"
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: SecretStr
    redis_url: str = "redis://localhost:6379/0"

    # --- Optional official data-source credentials ---
    eia_api_key: SecretStr | None = None
    usda_mars_api_key: SecretStr | None = None
    sec_edgar_user_agent: str = "ShadowCPI/1.0 (contact@example.com)"

    # --- App ---
    next_public_app_url: str = "http://localhost:3000"
    next_public_api_url: str = "http://localhost:8000"
    cron_secret: SecretStr

    # --- Runtime ---
    app_env: AppEnv = "local"
    api_port: int = Field(default=8000, gt=0, lt=65536)
    cors_allowed_origins: OriginList = ("http://localhost:3000",)
    rate_limit_per_minute: int = Field(default=60, gt=0)
    copilot_rate_limit_per_minute: int = Field(default=5, gt=0)
    log_level: Literal["debug", "info", "warning", "error"] = "info"

    @field_validator("eia_api_key", "usda_mars_api_key", mode="before")
    @classmethod
    def _blank_optional_key_means_absent(cls, value: object) -> object:
        """Treat an empty optional key as not configured.

        ``.env.example`` ships these variables present but empty, because they are
        optional. Without this, an empty value would look like a configured key, and the
        source would send a request with no credential and fail confusingly instead of
        being skipped.

        Args:
            value: Raw environment value.

        Returns:
            None when the value is blank, otherwise the value unchanged.
        """
        if isinstance(value, str) and value.strip() == "":
            return None
        return value

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def _parse_origins(cls, value: object) -> object:
        """Turn a comma-separated origin list into a tuple, rejecting wildcards.

        ``CORS_ALLOWED_ORIGINS`` is a single string in the environment, such as
        ``"http://localhost:3000, https://app.example"``. A wildcard origin would
        let any website on the internet call this API with the user's cookies
        attached, so it is refused rather than silently accepted.

        Args:
            value: Raw environment value, or an already-parsed sequence.

        Returns:
            A tuple of trimmed origins when given a string; otherwise the value
            unchanged so pydantic can validate it normally.

        Raises:
            ValueError: If the list is empty or contains a wildcard.
        """
        if not isinstance(value, str):
            return value
        origins = tuple(part.strip() for part in value.split(",") if part.strip())
        if not origins:
            raise ValueError("CORS_ALLOWED_ORIGINS must list at least one origin")
        if any(origin == "*" for origin in origins):
            raise ValueError("CORS_ALLOWED_ORIGINS must not contain the wildcard origin")
        return origins

    @field_validator("sec_edgar_user_agent")
    @classmethod
    def _require_contact_in_user_agent(cls, value: str) -> str:
        """Require a real contact address in the SEC User-Agent string.

        SEC asks every automated client to identify itself with a product name
        and a contact address, and throttles or blocks requests that do not.
        Catching this at startup is far better than discovering it when an
        overnight filing job starts receiving errors.

        Args:
            value: Configured User-Agent string.

        Returns:
            The validated, whitespace-trimmed User-Agent string.

        Raises:
            ValueError: If the string has no contact address.
        """
        cleaned = value.strip()
        if "@" not in cleaned or len(cleaned.split()) < _MIN_SEC_USER_AGENT_PARTS:
            raise ValueError(
                "SEC_EDGAR_USER_AGENT must include a product name and a contact "
                "email address, for example 'ShadowCPI/1.0 (you@example.com)'"
            )
        return cleaned

    @model_validator(mode="after")
    def _check_cross_field_rules(self) -> Self:
        """Check rules that involve more than one field.

        Two rules are enforced:

        - The copilot limit must be at least as strict as the general limit.
          Copilot requests trigger a paid model call, so they must never be the
          cheapest endpoint to hammer.
        - Outside local development, all public URLs must use HTTPS. Plain HTTP
          in a deployed environment exposes traffic to interception.

        Returns:
            The validated settings instance.

        Raises:
            ValueError: If either rule is violated.
        """
        if self.copilot_rate_limit_per_minute > self.rate_limit_per_minute:
            raise ValueError(
                "COPILOT_RATE_LIMIT_PER_MINUTE must be stricter than "
                "RATE_LIMIT_PER_MINUTE because each copilot call costs money"
            )
        if self.app_env != "local":
            insecure = [
                name
                for name, url in (
                    ("NEXT_PUBLIC_APP_URL", self.next_public_app_url),
                    ("NEXT_PUBLIC_API_URL", self.next_public_api_url),
                    *((f"CORS origin {origin}", origin) for origin in self.cors_allowed_origins),
                )
                if not url.startswith("https://")
            ]
            if insecure:
                raise ValueError(
                    f"HTTPS is required outside the local environment: {', '.join(insecure)}"
                )
        return self

    @property
    def is_production(self) -> bool:
        """Whether this process is running in production.

        Returns:
            True when ``APP_ENV`` is ``production``.
        """
        return self.app_env == "production"

    def collector_for(self, source_id: str) -> str | None:
        """Return the Scraper Studio collector that belongs to a source.

        Args:
            source_id: Identifier of the source, such as ``lme_copper_scraper``.

        Returns:
            The collector identifier, or None when the source has no collector yet. A
            source without one is skipped rather than run, because there is nothing to
            run.
        """
        for pair in self.scraper_studio_collectors.split(","):
            name, separator, collector = pair.partition("=")
            if separator and name.strip() == source_id:
                return collector.strip() or None
        return None


def build_settings(env: dict[str, str] | None = None) -> Settings:
    """Build settings from an explicit mapping, or from the process environment.

    Passing the environment in as an argument is what makes configuration easy
    to test: a test can describe exactly the environment it wants without
    touching ``os.environ`` and leaking that change into other tests.

    Args:
        env: Environment mapping to read, with upper-case keys. Defaults to the
            real process environment.

    Returns:
        A validated ``Settings`` instance.

    Raises:
        pydantic.ValidationError: If a required value is missing or invalid.
    """
    if env is None:
        return Settings()
    return Settings(**{key.lower(): value for key, value in env.items()})  # type: ignore[arg-type]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the shared settings instance for this process.

    The result is cached so that request handlers and scheduled jobs all see one
    validated object instead of re-parsing the environment on every call.

    Returns:
        The cached ``Settings`` instance.
    """
    return build_settings()
