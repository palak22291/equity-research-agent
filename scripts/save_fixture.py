#!/usr/bin/env python3
"""Save a Cipla financial-data fixture for offline/demo mode.

Fetches the full financial-data payload via the MCP server's aggregating tool and
writes it to tests/fixtures/cipla_fy2026.json. Run this once (with network) so the
pipeline can later run with --offline (no yfinance, no network) for demo safety.

Usage:
    python3 scripts/save_fixture.py
"""
import json
import sys
from pathlib import Path

# Make the `app` package importable when run as a plain script.
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))

from app.mcp.financial_data_server import fetch_all_financial_data

_FIXTURE = _PROJECT_ROOT / "tests" / "fixtures" / "cipla_fy2026.json"


def main():
    data = fetch_all_financial_data("CIPLA", "pharmaceuticals", 0.4468)
    if isinstance(data, dict) and "error" in data:
        print(f"Fetch failed: {data['error']}")
        sys.exit(1)

    _FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    _FIXTURE.write_text(json.dumps(data, indent=2))
    print("Fixture saved successfully")


if __name__ == "__main__":
    main()
