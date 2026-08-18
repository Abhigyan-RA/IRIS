"""Connects the graph repository to a real Neo4j server.

The repository works with plain dictionaries so it can be tested without a
database. This adapter is the only place that knows about the Neo4j driver's own
result objects, and it converts them to those dictionaries.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol


class _Result(Protocol):
    """The part of a driver result this adapter uses."""

    async def data(self) -> Sequence[Mapping[str, object]]: ...


class DriverSession(Protocol):
    """The part of a driver session this adapter uses.

    The signature mirrors the Neo4j driver: the statement first, then a mapping of
    named parameters. Declaring it as an interface keeps the repository free of
    driver imports and lets tests pass a fake.
    """

    async def run(
        self,
        query: str,
        parameters: dict[str, object] | None = None,
    ) -> _Result:
        """Run Cypher with named parameters."""
        ...


class Neo4jSessionAdapter:
    """Presents a Neo4j session as the simple interface the repository expects."""

    def __init__(self, session: DriverSession) -> None:
        """Create the adapter.

        Args:
            session: An open driver session.
        """
        self._session = session

    async def run(
        self,
        query: str,
        params: Mapping[str, object] | None = None,
    ) -> list[Mapping[str, object]]:
        """Run a query and return its rows.

        Args:
            query: Cypher statement using ``$name`` placeholders.
            params: Values to bind to those placeholders.

        Returns:
            Rows as plain dictionaries.
        """
        result: _Result = await self._session.run(query, dict(params or {}))
        rows = await result.data()
        return [dict(row) for row in rows]
