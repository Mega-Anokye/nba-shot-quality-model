"""Export small, clean tables for the Power BI dashboard (dashboard/data/).

Uses the main (location-only, season-recalibrated) out-of-sample predictions from career_pae.py,
so every number in the dashboard matches the reports/ folder.

Tables (star schema):
  dim_player.csv           PLAYER_ID, PLAYER_NAME
  dim_season.csv           SEASON, SEASON_START
  fact_player_season.csv   one row per player-season: shots, makes, threes, points, expected points
  fact_curry_shot.csv      every Curry shot with court location, outcome and expected points
"""

import sqlite3

import numpy as np
import pandas as pd

from career_pae import MODELS, recalibrate
from features import add_features, load_shots
from nba_common import DB_PATH, ROOT

OUT = ROOT / "dashboard" / "data"
CURRY_ID = 201939

ZONE_GROUP = {
    "Above the Break 3": "Above-break 3",
    "Left Corner 3": "Corner 3",
    "Right Corner 3": "Corner 3",
    "Mid-Range": "Mid-range",
    "Restricted Area": "Restricted area",
    "In The Paint (Non-RA)": "Paint (non-RA)",
    "Backcourt": "Backcourt",
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    shots, _ = add_features(load_shots())
    saved = pd.read_csv(MODELS / "crossfit_predictions.csv.gz", usecols=["SHOT_ID", "p"])
    shots = shots.merge(saved.rename(columns={"p": "p_raw"}), on="SHOT_ID", validate="one_to_one")
    shots["p"], _ = recalibrate(shots)
    shots["xpts"] = shots["p"] * shots["points_value"]

    # Dimensions
    players = shots[["PLAYER_ID", "PLAYER_NAME"]].drop_duplicates("PLAYER_ID").sort_values("PLAYER_NAME")
    seasons = pd.DataFrame({"SEASON": sorted(shots["SEASON"].unique())})
    seasons["SEASON_START"] = seasons["SEASON"].str[:4].astype(int)

    # Player-season fact
    ps = shots.groupby(["PLAYER_ID", "SEASON"]).agg(
        SHOTS=("SHOT_ID", "size"), MAKES=("SHOT_MADE_FLAG", "sum"), THREES=("is_three", "sum"),
        POINTS=("points", "sum"), XPTS=("xpts", "sum"),
    ).reset_index()

    # Curry shot fact
    with sqlite3.connect(DB_PATH) as conn:
        dates = pd.read_sql("SELECT SHOT_ID, GAME_DATE FROM fact_shot WHERE PLAYER_ID = ?", conn,
                            params=(CURRY_ID,))
    c = shots[shots["PLAYER_ID"] == CURRY_ID].merge(dates, on="SHOT_ID", how="left")
    c["GAME_DATE"] = pd.to_datetime(c["GAME_DATE"], format="%Y%m%d").dt.date
    c["ZONE"] = c["SHOT_ZONE_BASIC"].map(ZONE_GROUP)
    c["RESULT"] = np.where(c["SHOT_MADE_FLAG"] == 1, "Made", "Missed")
    c["DIST_FT"] = c["dist_ft"].round(1)
    curry = c[["SHOT_ID", "SEASON", "GAME_DATE", "LOC_X", "LOC_Y", "DIST_FT", "ZONE", "SHOT_TYPE",
               "RESULT", "SHOT_MADE_FLAG", "points_value", "points", "p", "xpts"]].rename(columns={
        "points_value": "SHOT_VALUE", "points": "POINTS", "p": "MAKE_PROB", "xpts": "XPTS"})

    players.to_csv(OUT / "dim_player.csv", index=False)
    seasons.to_csv(OUT / "dim_season.csv", index=False)
    ps.to_csv(OUT / "fact_player_season.csv", index=False, float_format="%.4f")
    curry.to_csv(OUT / "fact_curry_shot.csv", index=False, float_format="%.4f")

    # Reconciliation printed for the record
    print(f"dim_player {len(players):,} | dim_season {len(seasons)} | fact_player_season {len(ps):,} "
          f"| fact_curry_shot {len(curry):,}")
    print(f"player-season shots {ps['SHOTS'].sum():,} = model shots {len(shots):,}: "
          f"{ps['SHOTS'].sum() == len(shots)}")
    cp = ps[ps["PLAYER_ID"] == CURRY_ID]
    print(f"Curry PAE from player-season: {cp['POINTS'].sum() - cp['XPTS'].sum():.1f}; "
          f"from shots: {curry['POINTS'].sum() - curry['XPTS'].sum():.1f}")


if __name__ == "__main__":
    main()
