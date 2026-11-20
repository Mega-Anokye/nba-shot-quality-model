"""Export compact JSON for the interactive web dashboard (docs/, served by GitHub Pages).

Reads the same CSVs as the Power BI report (dashboard/data), so both show identical numbers.

  docs/data/curry_shots.json     column arrays, one entry per Curry shot
  docs/data/player_seasons.json  column arrays, one entry per player-season
"""

import json

import pandas as pd

from nba_common import ROOT

SRC = ROOT / "dashboard" / "data"
OUT = ROOT / "docs" / "data"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    shots = pd.read_csv(SRC / "fact_curry_shot.csv")
    ps = pd.read_csv(SRC / "fact_player_season.csv")
    players = pd.read_csv(SRC / "dim_player.csv")
    seasons = sorted(shots["SEASON"].unique().tolist() + [s for s in ps["SEASON"].unique() if s not in set(shots["SEASON"])])
    seasons = sorted(set(seasons))
    zones = sorted(shots["ZONE"].unique().tolist())
    s_idx = {s: i for i, s in enumerate(seasons)}
    z_idx = {z: i for i, z in enumerate(zones)}

    curry = {
        "seasons": seasons, "zones": zones,
        "x": shots["LOC_X"].tolist(), "y": shots["LOC_Y"].tolist(),
        "s": shots["SEASON"].map(s_idx).tolist(), "z": shots["ZONE"].map(z_idx).tolist(),
        "made": shots["SHOT_MADE_FLAG"].tolist(), "val": shots["SHOT_VALUE"].tolist(),
        "p": shots["MAKE_PROB"].round(4).tolist(), "d": shots["DIST_FT"].tolist(),
        "date": shots["GAME_DATE"].tolist(),
    }
    names = players.set_index("PLAYER_ID")["PLAYER_NAME"]
    pid = {p: i for i, p in enumerate(names.index)}
    league = {
        "seasons": seasons, "players": names.tolist(),
        "pl": ps["PLAYER_ID"].map(pid).tolist(), "s": ps["SEASON"].map(s_idx).tolist(),
        "shots": ps["SHOTS"].tolist(), "makes": ps["MAKES"].tolist(),
        "pts": ps["POINTS"].tolist(), "xpts": ps["XPTS"].round(3).tolist(),
    }
    for name, obj in [("curry_shots.json", curry), ("player_seasons.json", league)]:
        (OUT / name).write_text(json.dumps(obj, separators=(",", ":")), encoding="utf-8")

    # Reconciliation against the Power BI tables
    pae = (shots["POINTS"].sum() - shots["XPTS"].sum())
    print(f"curry shots {len(shots):,}, PAE {pae:.1f} | player-seasons {len(ps):,}, shots {ps['SHOTS'].sum():,}")
    for f in OUT.iterdir():
        print(f"  {f.name}: {f.stat().st_size / 1e3:,.0f} KB")


if __name__ == "__main__":
    main()
