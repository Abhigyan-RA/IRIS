"""The list of known data sources.

The registry exists so that the scheduler, the API, and the tests can all ask
"what sources are there" without any of them containing that list. Adding a source
means registering it in its own module; nothing that already works gets edited,
which is the property that keeps ten sources from becoming a tangle.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TypeVar

from shadow_cpi.ingestion.base import DataSourceIngestor, IngestionContext

# A factory turns the shared context into one ready-to-run source.
IngestorFactory = Callable[[IngestionContext], DataSourceIngestor]

_IngestorType = TypeVar("_IngestorType", bound=IngestorFactory)


class SourceRegistry:
    """Holds the known sources and builds them on demand."""

    def __init__(self) -> None:
        """Create an empty registry."""
        self._factories: dict[str, IngestorFactory] = {}

    def register(self, source_id: str, factory: IngestorFactory) -> None:
        """Add a source to the registry.

        Args:
            source_id: Stable identifier, for example ``eia_petroleum_spot``.
            factory: Callable that builds the source from a context. An ingestor
                class works directly, since calling it constructs an instance.

        Raises:
            ValueError: If the identifier is already registered. Overwriting
                silently would mean one source stops running with no error.
        """
        if source_id in self._factories:
            raise ValueError(f"Source {source_id!r} is already registered")
        self._factories[source_id] = factory

    def source(self, source_id: str) -> Callable[[_IngestorType], _IngestorType]:
        """Register a source with a decorator.

        Args:
            source_id: Stable identifier for the source.

        Returns:
            A decorator that registers the class and returns it unchanged.

        Example:
            >>> registry = SourceRegistry()
            >>> @registry.source("example_source")  # doctest: +SKIP
            ... class ExampleIngestor: ...
        """

        def decorate(factory: _IngestorType) -> _IngestorType:
            self.register(source_id, factory)
            return factory

        return decorate

    def source_ids(self) -> tuple[str, ...]:
        """List the registered identifiers.

        Returns:
            Identifiers in alphabetical order, so logs and API responses are
            stable between runs.
        """
        return tuple(sorted(self._factories))

    def build(self, source_id: str, context: IngestionContext) -> DataSourceIngestor:
        """Build one source.

        Args:
            source_id: Identifier of the source to build.
            context: Shared dependencies to hand it.

        Returns:
            A ready-to-run source.

        Raises:
            KeyError: If the identifier is unknown. The message lists what is
                available, because the usual cause is a typo in configuration.
        """
        try:
            factory = self._factories[source_id]
        except KeyError as error:
            available = ", ".join(self.source_ids()) or "none"
            raise KeyError(f"Unknown source {source_id!r}; registered sources: {available}") from (
                error
            )
        return factory(context)

    def build_all(self, context: IngestionContext) -> Sequence[DataSourceIngestor]:
        """Build every registered source.

        This is what a scheduled run iterates over.

        Args:
            context: Shared dependencies to hand each source.

        Returns:
            One instance per registered source, in identifier order.
        """
        return [self.build(source_id, context) for source_id in self.source_ids()]


# The registry the application uses. Source modules register themselves against it
# at import time.
default_registry = SourceRegistry()
