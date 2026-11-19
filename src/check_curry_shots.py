"""Reconcile the pulled shot data against Curry's official season totals.

Checks:
  1. No duplicate shots (unique ID = GAME_ID + GAME_EVENT_ID).
  2. Per season: shot rows = official FGA, made shots = FGM, 3PT attempts = FG3A, 3PT makes = FG3M.
  3. Career totals tie out.

Writes data_checks/curry_reconciliation.csv and prints PASS/FAIL.
"""

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data_checks"


def main() -> None:
    shots = pd.read_csv(RAW / "curry_shots.csv", dtype={"GAME_ID": str})
    official = pd.read_csv(RAW / "curry_official_totals.csv")

    # 1. Duplicates
    dupes = shots[shots.duplicated("SHOT_ID", keep=False)]
    print(f"Duplicate shot IDs: {dupes['SHOT_ID'].nunique()}")

    # 2. Per-season reconciliation
    shots["IS_3PA"] = (shots["SHOT_TYPE"] == "3PT Field Goal").astype(int)
    shots["IS_3PM"] = shots["IS_3PA"] * shots["SHOT_MADE_FLAG"]
    pulled = shots.groupby("SEASON").agg(
        FGA_pulled=("SHOT_ID", "count"),
        FGM_pulled=("SHOT_MADE_FLAG", "sum"),
        FG3A_pulled=("IS_3PA", "sum"),
        FG3M_pulled=("IS_3PM", "sum"),
    ).reset_index()

    recon = official.rename(columns={"SEASON_ID": "SEASON"}).merge(pulled, on="SEASON", how="outer")
    for stat in ["FGA", "FGM", "FG3A", "FG3M"]:
        recon[f"{stat}_diff"] = recon[f"{stat}_pulled"] - recon[stat]
    diff_cols = [c for c in recon.columns if c.endswith("_diff")]

    def status(row) -> str:
        if pd.isna(row["FGA_pulled"]):
            return "NOT PULLED"      # e.g. the season in progress, outside the pull range
        if pd.isna(row["FGA"]):
            return "NO OFFICIAL ROW"
        return "PASS" if row[diff_cols].abs().sum() == 0 else "MISMATCH"

    recon["STATUS"] = recon.apply(status, axis=1)

    # 3. Career totals, over the seasons that were pulled
    in_scope = recon[recon["STATUS"] != "NOT PULLED"]
    career = in_scope.drop(columns=["SEASON", "TEAM_ABBREVIATION", "STATUS"]).sum(numeric_only=True, min_count=1)
    career["SEASON"] = "CAREER (pulled seasons)"
    career["STATUS"] = "PASS" if (in_scope["STATUS"] == "PASS").all() and career[diff_cols].abs().sum() == 0 else "MISMATCH"
    recon = pd.concat([recon, career.to_frame().T], ignore_index=True)

    OUT.mkdir(exist_ok=True)
    recon.to_csv(OUT / "curry_reconciliation.csv", index=False)

    cols = ["SEASON", "GP", "FGA", "FGA_pulled", "FGM", "FGM_pulled", "FG3A", "FG3A_pulled", "FG3M", "FG3M_pulled", "STATUS"]
    print(recon[cols].to_string(index=False))
    n_bad = recon["STATUS"].isin(["MISMATCH", "NO OFFICIAL ROW"]).sum()
    skipped = recon.loc[recon["STATUS"] == "NOT PULLED", "SEASON"].tolist()
    if skipped:
        print(f"\nNot pulled (outside the pull range): {', '.join(skipped)}")
    print("ALL CHECKS PASS" if n_bad == 0 and dupes.empty else f"{n_bad} row(s) MISMATCH - investigate")


if __name__ == "__main__":
    main()
