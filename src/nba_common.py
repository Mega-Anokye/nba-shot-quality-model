"""Shared settings and helpers for talking to NBA.com's stats API."""

import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKS = ROOT / "data_checks"

# The data (~700 MB) lives outside the repo so it isn't synced by OneDrive or committed.
# Override the location with the NBA_DATA_DIR environment variable.
DATA_DIR = Path(os.environ.get("NBA_DATA_DIR", Path.home() / "nba-shot-quality-data"))
RAW = DATA_DIR / "raw"
DB_PATH = DATA_DIR / "nba.db"

# NBA.com silently hangs on requests that don't look like they come from its own website,
# so send the same headers a browser on nba.com would.
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Origin": "https://www.nba.com",
    "Referer": "https://www.nba.com/",
    "x-nba-stats-origin": "stats",
    "x-nba-stats-token": "true",
    "Sec-Fetch-Site": "same-site",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
}


def season_label(start_year: int) -> str:
    """2015 -> '2015-16'."""
    return f"{start_year}-{str(start_year + 1)[-2:]}"


def call_with_retry(fn, tries: int = 4, wait: float = 5.0):
    """NBA.com sometimes times out; wait longer each time and try again."""
    for attempt in range(1, tries + 1):
        try:
            return fn()
        except Exception as err:  # noqa: BLE001
            if attempt == tries:
                raise
            print(f"   retry {attempt}/{tries - 1} after error: {err}", flush=True)
            time.sleep(wait * attempt)
