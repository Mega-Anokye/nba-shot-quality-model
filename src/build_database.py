"""Load the season files into SQLite as a small star schema.

Tables:
  fact_shot             one row per shot attempt (primary key SHOT_ID = GAME_ID-GAME_EVENT_ID)
  dim_player            PLAYER_ID -> PLAYER_NAME
  dim_team              TEAM_ID -> TEAM_NAME (most recent name)
  official_team_totals  NBA's own team-season totals, used by the checks
"""

import sqlite3

import pandas as pd

from nba_common import DB_PATH, RAW

LEAGUE = RAW / "league"

FACT_COLUMNS = [
    "SHOT_ID", "SEASON", "GAME_ID", "GAME_EVENT_ID", "GAME_DATE", "PLAYER_ID", "TEAM_ID",
    "PERIOD", "MINUTES_REMAINING", "SECONDS_REMAINING", "ACTION_TYPE", "SHOT_TYPE",
    "SHOT_ZONE_BASIC", "SHOT_ZONE_AREA", "SHOT_ZONE_RANGE", "SHOT_DISTANCE",
    "LOC_X", "LOC_Y", "SHOT_MADE_FLAG", "HTM", "VTM",
]

DDL = """
DROP TABLE IF EXISTS fact_shot;
DROP TABLE IF EXISTS dim_player;
DROP TABLE IF EXISTS dim_team;
DROP TABLE IF EXISTS official_team_totals;
DROP TABLE IF EXISTS shots;            -- legacy table names from the first Curry run
DROP TABLE IF EXISTS official_totals;

CREATE TABLE dim_player (PLAYER_ID INTEGER PRIMARY KEY, PLAYER_NAME TEXT NOT NULL);
CREATE TABLE dim_team   (TEAM_ID   INTEGER PRIMARY KEY, TEAM_NAME   TEXT NOT NULL);

CREATE TABLE fact_shot (
    SHOT_ID           TEXT PRIMARY KEY,
    SEASON            TEXT NOT NULL,
    GAME_ID           TEXT NOT NULL,
    GAME_EVENT_ID     INTEGER NOT NULL,
    GAME_DATE         TEXT NOT NULL,
    PLAYER_ID         INTEGER NOT NULL REFERENCES dim_player(PLAYER_ID),
    TEAM_ID           INTEGER NOT NULL REFERENCES dim_team(TEAM_ID),
    PERIOD            INTEGER,
    MINUTES_REMAINING INTEGER,
    SECONDS_REMAINING INTEGER,
    ACTION_TYPE       TEXT,
    SHOT_TYPE         TEXT,
    SHOT_ZONE_BASIC   TEXT,
    SHOT_ZONE_AREA    TEXT,
    SHOT_ZONE_RANGE   TEXT,
    SHOT_DISTANCE     INTEGER,
    LOC_X             INTEGER,
    LOC_Y             INTEGER,
    SHOT_MADE_FLAG    INTEGER NOT NULL CHECK (SHOT_MADE_FLAG IN (0, 1)),
    HTM               TEXT,
    VTM               TEXT
);

CREATE TABLE official_team_totals (
    SEASON TEXT, TEAM_ID INTEGER, TEAM_NAME TEXT, GP INTEGER,
    FGM INTEGER, FGA INTEGER, FG3M INTEGER, FG3A INTEGER,
    PRIMARY KEY (SEASON, TEAM_ID)
);
"""

INDEXES = """
CREATE INDEX ix_shot_season ON fact_shot (SEASON);
CREATE INDEX ix_shot_player ON fact_shot (PLAYER_ID, SEASON);
CREATE INDEX ix_shot_team   ON fact_shot (TEAM_ID, SEASON);
"""


def main() -> None:
    shot_files = sorted(LEAGUE.glob("shots_*.csv.gz"))
    total_files = sorted(LEAGUE.glob("team_totals_*.csv"))
    print(f"Loading {len(shot_files)} season files ...")

    shots = pd.concat(
        (pd.read_csv(f, dtype={"GAME_ID": str, "GAME_DATE": str}) for f in shot_files),
        ignore_index=True,
    )
    shots["SHOT_ID"] = shots["GAME_ID"] + "-" + shots["GAME_EVENT_ID"].astype(str)

    # Duplicates: only drop a repeated SHOT_ID if every column is identical.
    dup_ids = shots["SHOT_ID"].duplicated(keep=False)
    if dup_ids.any():
        dups = shots[dup_ids]
        n_distinct = len(dups.drop_duplicates())
        if n_distinct != dups["SHOT_ID"].nunique():
            raise ValueError("Some repeated SHOT_IDs have different contents - investigate before loading.")
        print(f"Dropping {dup_ids.sum() - dups['SHOT_ID'].nunique()} exact duplicate rows")
        shots = shots.drop_duplicates()
    else:
        print("No duplicate shot IDs")

    players = shots[["PLAYER_ID", "PLAYER_NAME"]].drop_duplicates("PLAYER_ID", keep="last")
    teams = shots.sort_values("SEASON")[["TEAM_ID", "TEAM_NAME"]].drop_duplicates("TEAM_ID", keep="last")
    totals = pd.concat((pd.read_csv(f) for f in total_files), ignore_index=True)

    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript(DDL)
        players.to_sql("dim_player", conn, if_exists="append", index=False)
        teams.to_sql("dim_team", conn, if_exists="append", index=False)
        shots[FACT_COLUMNS].to_sql("fact_shot", conn, if_exists="append", index=False, chunksize=50_000)
        totals.to_sql("official_team_totals", conn, if_exists="append", index=False)
        conn.executescript(INDEXES)

    print(f"fact_shot: {len(shots):,} rows | dim_player: {len(players):,} | dim_team: {len(teams)} "
          f"| official_team_totals: {len(totals)}")
    print(f"Database: {DB_PATH} ({DB_PATH.stat().st_size / 1e6:,.0f} MB)")


if __name__ == "__main__":
    main()
