"""Ossmate MCP server — OSS maintainer tools exposed via Model Context Protocol."""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

try:
    __version__ = _pkg_version("ossmate-mcp")
except PackageNotFoundError:
    __version__ = "0.0.0+source"
