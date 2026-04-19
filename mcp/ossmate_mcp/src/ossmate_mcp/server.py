"""Ossmate MCP server entry point.

Exposes OSS-maintainer tools (GitHub, changelog, deps, repo) and templates
to any MCP client (Claude Code, Claude Desktop, Agent SDK CLI, etc.) over
stdio.

Run directly:
    python -m ossmate_mcp
or via the console script:
    ossmate-mcp

Self-test (lists registered tools without starting the stdio loop):
    python -m ossmate_mcp --selftest
"""

from __future__ import annotations

import sys

from mcp.server.fastmcp import FastMCP

from .resources import templates as templates_resources
from .tools import changelog as changelog_tools
from .tools import deps as deps_tools
from .tools import github as github_tools
from .tools import repo as repo_tools

mcp = FastMCP("ossmate")

# Register every tool/resource module. Each module exposes a `register(mcp)`
# callable that wires its decorators onto the shared FastMCP instance.
repo_tools.register(mcp)
changelog_tools.register(mcp)
github_tools.register(mcp)
deps_tools.register(mcp)
templates_resources.register(mcp)


def _selftest() -> int:
    """Print registered tools and resources without starting stdio."""
    import asyncio

    async def _list() -> None:
        tools = await mcp.list_tools()
        resources = await mcp.list_resources()
        templates = await mcp.list_resource_templates()
        print(f"ossmate-mcp: {len(tools)} tools, "
              f"{len(resources)} resources, "
              f"{len(templates)} resource templates")
        for t in tools:
            print(f"  tool      {t.name}")
        for r in resources:
            print(f"  resource  {r.uri}")
        for t in templates:
            print(f"  template  {t.uriTemplate}")

    asyncio.run(_list())
    return 0


def main() -> None:
    if "--selftest" in sys.argv[1:]:
        sys.exit(_selftest())
    # stdio loop — JSON-RPC over stdin/stdout. Anything written to stdout
    # outside the protocol will corrupt the client; tools must use stderr
    # for diagnostics.
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
