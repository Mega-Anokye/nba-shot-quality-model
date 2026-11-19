"""Pull every regular-season shot Stephen Curry has taken, plus his official season totals.

Output:
  data/raw/curry_shots.csv           one row per shot attempt
  data/raw/curry_official_totals.csv official per-season totals (for reconciliation)
  data/nba.db                        SQLite database with tables `shots` and `official_totals`
"""

import sqlite3
import time
from pathlib import Path

import pandas as pd
from nba_api.stats.endpoints import playercareerstats, shotchartdetail

CURRY_ID = 201939
FIRST_SEASON_START = 2009   # 2009-10 rookie season
LAST_SEASON_START = 2025    # 2025-26, the last completed season

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
DB_PATH = ROOT / "data" / "nba.db"

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
    return f"{start_year}-{str(start_year + 1)[-2:]}"


def call_with_retry(fn, tries: int = 4, wait: float = 5.0):
    """NBA.com sometimes times out; wait and try again."""
    for attempt in range(1, tries + 1):
        try:
            return fn()
        except Exception as err:  # noqa: BLE001
            if attempt == tries:
                raise
            print(f"   retry {attempt}/{tries - 1} after error: {err}")
            time.sleep(wait * attempt)


def pull_shots() -> pd.DataFrame:
    frames = []
    for year in range(FIRST_SEASON_START, LAST_SEASON_START + 1):
        season = season_label(year)
        print(f"Pulling shots for {season} ...")
        resp = call_with_retry(lambda: shotchartdetail.ShotChartDetail(
            team_id=0,
            player_id=CURRY_ID,
            season_nullable=season,
            season_type_all_star="Regular Season",
            context_measure_simple="FGA",
            headers=HEADERS,
            timeout=60,
        ))
        df = resp.get_data_frames()[0]
        df["SEASON"] = season
        print(f"   {len(df):,} shots")
        frames.append(df)
        time.sleep(1.5)  # be polite to the API
    return pd.concat(frames, ignore_index=True)


def pull_official_totals() -> pd.DataFrame:
    print("Pulling official season totals ...")
    resp = call_with_retry(lambda: playercareerstats.PlayerCareerStats(
        player_id=CURRY_ID, per_mode36="Totals", headers=HEADERS, timeout=60,
    ))
    totals = resp.season_totals_regular_season.get_data_frame()
    # If a player was traded mid-season there is a 'TOT' row; keep it and drop the team splits.
    has_tot = totals.groupby("SEASON_ID")["TEAM_ABBREVIATION"].transform(lambda s: (s == "TOT").any())
    totals = totals[~has_tot | (totals["TEAM_ABBREVIATION"] == "TOT")]
    return totals[["SEASON_ID", "TEAM_ABBREVIATION", "GP", "FGM", "FGA", "FG3M", "FG3A"]]


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)

    shots = pull_shots()
    shots["SHOT_ID"] = shots["GAME_ID"].astype(str) + "-" + shots["GAME_EVENT_ID"].astype(str)
    shots.to_csv(RAW / "curry_shots.csv", index=False)

    totals = pull_official_totals()
    totals.to_csv(RAW / "curry_official_totals.csv", index=False)

    with sqlite3.connect(DB_PATH) as conn:
        shots.to_sql("shots", conn, if_exists="replace", index=False)
        totals.to_sql("official_totals", conn, if_exists="replace", index=False)

    print(f"\nDone: {len(shots):,} shots across {shots['SEASON'].nunique()} seasons.")
    print(f"Saved to {RAW} and {DB_PATH}")


if __name__ == "__main__":
    main()
