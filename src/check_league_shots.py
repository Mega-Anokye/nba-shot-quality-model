"""Sanity-check the league shot database before any modelling.

Checks:
  1. Every team-season ties to the NBA's official FGA, FGM, 3PA and 3PM.
  2. Season and grand totals tie.
  3. No duplicate shots, no missing locations, made flag only 0/1.
  4. Cross-check: Curry's shots in the league table match the separate Curry pull.

Writes:
  data_checks/league_reconciliation_by_season.csv
  data_checks/league_team_season_mismatches.csv   (only if there are any)
  data_checks/league_quality_checks.csv
"""

import sqlite3

import pandas as pd

from nba_common import CHECKS, DB_PATH

STATS = ["FGA", "FGM", "FG3A", "FG3M"]

TEAM_SEASON_SQL = """
WITH pulled AS (
    SELECT SEASON, TEAM_ID,
           COUNT(*)                                                    AS FGA_pulled,
           SUM(SHOT_MADE_FLAG)                                         AS FGM_pulled,
           SUM(SHOT_TYPE = '3PT Field Goal')                           AS FG3A_pulled,
           SUM(SHOT_TYPE = '3PT Field Goal' AND SHOT_MADE_FLAG = 1)    AS FG3M_pulled
    FROM fact_shot
    GROUP BY SEASON, TEAM_ID
)
SELECT o.SEASON, o.TEAM_ID, o.TEAM_NAME, o.FGA, o.FGM, o.FG3A, o.FG3M,
       p.FGA_pulled, p.FGM_pulled, p.FG3A_pulled, p.FG3M_pulled
FROM official_team_totals o
LEFT JOIN pulled p USING (SEASON, TEAM_ID)
"""

QUALITY_SQL = {
    "duplicate SHOT_IDs":           "SELECT COUNT(*) - COUNT(DISTINCT SHOT_ID) FROM fact_shot",
    "shots with missing location":  "SELECT COUNT(*) FROM fact_shot WHERE LOC_X IS NULL OR LOC_Y IS NULL OR SHOT_DISTANCE IS NULL",
    "made flag not 0/1":            "SELECT COUNT(*) FROM fact_shot WHERE SHOT_MADE_FLAG NOT IN (0, 1)",
    "shots with unknown player":    "SELECT COUNT(*) FROM fact_shot s LEFT JOIN dim_player p USING (PLAYER_ID) WHERE p.PLAYER_ID IS NULL",
    "shots with unknown team":      "SELECT COUNT(*) FROM fact_shot s LEFT JOIN dim_team t USING (TEAM_ID) WHERE t.TEAM_ID IS NULL",
    "Curry shots: league table vs Curry pull (difference)": """
        SELECT (SELECT COUNT(*) FROM fact_shot WHERE PLAYER_ID = 201939)
             - (SELECT COUNT(*) FROM curry_shots WHERE SEASON >= '2013-14')""",
    "Curry shots missing from league table": """
        SELECT COUNT(*) FROM curry_shots c
        WHERE c.SEASON >= '2013-14'
          AND NOT EXISTS (SELECT 1 FROM fact_shot f
                          WHERE f.SHOT_ID = c.SHOT_ID)""",  # SHOT_ID is the indexed primary key
}


def main() -> None:
    CHECKS.mkdir(exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        ts = pd.read_sql(TEAM_SEASON_SQL, conn)
        quality = pd.DataFrame(
            [(name, conn.execute(sql).fetchone()[0]) for name, sql in QUALITY_SQL.items()],
            columns=["CHECK", "VALUE"],
        )

    # 1. Team-season level
    for s in STATS:
        ts[f"{s}_diff"] = ts[f"{s}_pulled"].fillna(0) - ts[s]
    diff_cols = [f"{s}_diff" for s in STATS]
    bad = ts[ts[diff_cols].abs().sum(axis=1) > 0]
    mismatch_path = CHECKS / "league_team_season_mismatches.csv"
    if len(bad):
        bad.to_csv(mismatch_path, index=False)
    elif mismatch_path.exists():
        mismatch_path.unlink()

    # 2. Season level + grand total
    season = ts.groupby("SEASON")[STATS + [f"{s}_pulled" for s in STATS] + diff_cols].sum().reset_index()
    season["TEAMS"] = ts.groupby("SEASON").size().values
    season["STATUS"] = season[diff_cols].abs().sum(axis=1).map(lambda d: "PASS" if d == 0 else "MISMATCH")
    grand = season.drop(columns=["SEASON", "STATUS"]).sum()
    grand["SEASON"] = "ALL SEASONS"
    grand["STATUS"] = "PASS" if (season["STATUS"] == "PASS").all() else "MISMATCH"
    season = pd.concat([season, grand.to_frame().T], ignore_index=True)
    season.to_csv(CHECKS / "league_reconciliation_by_season.csv", index=False)

    # 3 + 4. Quality checks
    quality["STATUS"] = quality["VALUE"].map(lambda v: "PASS" if v == 0 else "CHECK")
    # Known source gap: NBA.com has no coordinates or zone for a few hundred shots (2013-14 to 2016-17).
    # They stay in fact_shot so totals tie, and the model excludes them. Fail only if the gap grows.
    total_shots = int(ts["FGA_pulled"].sum())
    missing = quality["CHECK"] == "shots with missing location"
    share = quality.loc[missing, "VALUE"].iloc[0] / total_shots
    if 0 < share <= 0.0005:
        quality.loc[missing, "STATUS"] = f"KNOWN GAP ({share:.3%}, excluded from model)"
    quality.to_csv(CHECKS / "league_quality_checks.csv", index=False)

    print(season[["SEASON", "TEAMS", "FGA", "FGA_pulled", "FGM", "FGM_pulled",
                  "FG3A", "FG3A_pulled", "FG3M", "FG3M_pulled", "STATUS"]].to_string(index=False))
    print()
    print(quality.to_string(index=False))
    print()
    if len(bad):
        print(f"{len(bad)} team-season(s) don't tie - see {mismatch_path.name}")
    ok = len(bad) == 0 and quality["STATUS"].str.match("PASS|KNOWN GAP").all()
    print("ALL CHECKS PASS" if ok else "SOME CHECKS NEED A LOOK")


if __name__ == "__main__":
    main()
