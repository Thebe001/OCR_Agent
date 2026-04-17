"""Floravi Daily Close MCP server (stdio transport)."""

from __future__ import annotations

import os
import sys

from mcp.server.fastmcp import FastMCP

# Ensure imports from src/ resolve when launched by VS Code MCP.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

mcp = FastMCP("Floravi Daily Close Agent", version="1.0.0")


@mcp.tool()
def get_pos_transactions(date: str, pos_profile: str | None = None) -> dict:
    """Retrieve POS transactions for a date and optional POS profile."""
    from src.tools.daily_close.get_pos_transactions import execute

    return execute(date=date, pos_profile=pos_profile)


@mcp.tool()
def validate_pos_totals(date: str) -> dict:
    """Validate invoice totals against payment records for a date."""
    from src.tools.daily_close.validate_pos_totals import execute

    return execute(date=date)


@mcp.tool()
def detect_anomalies(date: str) -> dict:
    """Run anomaly detection rules on daily POS data."""
    from src.tools.daily_close.detect_anomalies import execute

    return execute(date=date)


@mcp.tool()
def close_pos_session(date: str, force_close: bool = False) -> dict:
    """Close the POS session, optionally forcing close when anomalies exist."""
    from src.tools.daily_close.close_pos_session import execute

    return execute(date=date, force_close=force_close)


if __name__ == "__main__":
    mcp.run(transport="stdio")
