"""Pull every regular-season NBA shot from 2013-14 to 2025-26, team by team.

Why team by team: a single league-wide request silently returns only about half the
shots (NBA.com caps the response), so we ask for each of the 30 teams separately.

Output (one file per season, so a failed run can resume where it stopped):
  data/raw/league/shots_<season>.csv.gz        one row per shot attempt
  data/raw/league/team_totals_<season>.csv     official team totals, for reconciliation

Run again with --force to re-download seasons that already exist.
"""

import argparse
import time

import pandas as pd
from nba_api.stats.endpoints import leaguedashteamstats, shotchartdetail

from nba_common import HEADERS, RAW, call_with_retry, season_label

FIRST_SEASON_START = 2013   # 2013-14
LAST_SEASON_START = 2025    # 2025-26, the last completed season
OUT = RAW / "league"


def team_totals(season: str) -> pd.DataFrame:
    resp = call_with_retry(lambda: leaguedashteamstats.LeagueDashTeamStats(
        season=season,
        season_type_all_star="Regular Season",
        per_mode_detailed="Totals",
        measure_type_detailed_defense="Base",
        headers=HEADERS,
        timeout=60,
    ))
    df = resp.get_data_frames()[0]
    df["SEASON"] = season
    return df[["SEASON", "TEAM_ID", "TEAM_NAME", "GP", "FGM", "FGA", "FG3M", "FG3A"]]


def team_shots(season: str, team_id: int) -> pd.DataFrame:
    resp = call_with_retry(lambda: shotchartdetail.ShotChartDetail(
        team_id=team_id,
        player_id=0,
        season_nullable=season,
        season_type_all_star="Regular Season",
        context_measure_simple="FGA",
        headers=HEADERS,
        timeout=120,
    ))
    return resp.get_data_frames()[0]


def pull_season(season: str) -> None:
    totals = team_totals(season)
    frames = []
    for i, row in enumerate(totals.itertuples(), start=1):
        df = team_shots(season, int(row.TEAM_ID))
        flag = "" if len(df) == row.FGA else f"   <-- official FGA {row.FGA}"
        print(f"   {i:>2}/30 {row.TEAM_NAME:<24} {len(df):>6,} shots{flag}", flush=True)
        frames.append(df)
        time.sleep(1.0)  # be polite to the API

    shots = pd.concat(frames, ignore_index=True)
    shots["SEASON"] = season
    shots.to_csv(OUT / f"shots_{season}.csv.gz", index=False, compression="gzip")
    totals.to_csv(OUT / f"team_totals_{season}.csv", index=False)
    print(f"   saved {len(shots):,} shots (official: {totals['FGA'].sum():,})", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="re-download seasons already saved")
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    started = time.time()
    for year in range(FIRST_SEASON_START, LAST_SEASON_START + 1):
        season = season_label(year)
        if (OUT / f"shots_{season}.csv.gz").exists() and not args.force:
            print(f"{season}: already saved, skipping")
            continue
        print(f"{season}:", flush=True)
        pull_season(season)
    print(f"\nDone in {(time.time() - started) / 60:.1f} minutes.")


if __name__ == "__main__":
    main()
