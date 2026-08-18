"""Entry point that starts the MCP server.

Run it with:

    python -m shadow_cpi.mcp_server.main

It speaks over standard input and output, which is how editors and agent runtimes
launch a tool server. Add it to an MCP-capable client with:

    {
      "mcpServers": {
        "shadow-cpi": {
          "command": "python",
          "args": ["-m", "shadow_cpi.mcp_server.main"]
        }
      }
    }

The client must run it with the same environment as the rest of the service, since
it reads the same databases.
"""

from __future__ import annotations

import asyncio

from shadow_cpi.config import get_settings
from shadow_cpi.mcp_server.server import build_server
from shadow_cpi.runtime import bootstrap
from shadow_cpi.wiring import open_dependencies


async def serve() -> None:  # pragma: no cover - requires live databases and a transport
    """Open the databases and serve MCP over standard input and output."""
    settings = get_settings()
    async with open_dependencies(settings) as dependencies:
        server = build_server(dependencies)
        await server.run_stdio_async()


def main() -> None:  # pragma: no cover - thin entry point around serve
    """Start the server."""
    bootstrap()
    asyncio.run(serve())


if __name__ == "__main__":  # pragma: no cover
    main()
