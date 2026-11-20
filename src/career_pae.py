"""Score every shot since 2009-10 with a model that never saw that season, then measure
Curry's points above expected (PAE) across his whole career.

Leave-one-season-out: for each of the 17 seasons, train XGBoost on the other 16 and
predict the held-out one. Every expected-points value is therefore out-of-sample.
The number of trees is fixed from the tuned model in train_models.py, so no held-out
season is ever used for tuning.

Season recalibration: a model trained on other seasons can be off for a whole season
(NBA.com relabelled shot descriptions around 2015-16; shooting rose in the no-crowd
2020-21 season). "Expected" should mean "an average shooter that same season", so each
season's predictions get one logit shift that makes expected makes equal actual makes.
Differences between shots are untouched; league-average PAE becomes zero every season.

Use --reuse to skip the 17 model fits and recompute everything from saved predictions.

Features: by default the model uses only location, game clock and season. Shot descriptions
("Pullup Jump Shot", "Step Back Jump Shot", ...) LEAK THE OUTCOME before 2017-18: in 2009-10,
threes labelled "pull-up" went in 71% of the time against a league 3P% of 35.5%, i.e. the
detailed label was mostly recorded on makes. From 2017-18 the labels look clean.
--features full adds the descriptions back (outputs get a _with_labels suffix), and
reports/curry_robustness.csv compares Curry's seasons under both models.

Writes:
  reports/crossfit_check_by_season.csv   expected vs actual points per season (sanity check)
  reports/curry_career_pae.csv           Curry season by season, with league rank
  reports/curry_pae_by_zone.csv          Curry by court zone, whole career
  reports/pae_career_leaderboard.csv     every player, 2009-10 to 2025-26
  reports/figures/curry_career_pae.png
  <data dir>/models/crossfit_predictions.csv.gz
"""

import argparse
import time

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.optimize import brentq
from scipy.special import expit, logit
from sklearn.metrics import log_loss, roc_auc_score
from xgboost import XGBClassifier

from features import CATEGORICAL, NUMERIC, add_features, load_shots
from nba_common import DATA_DIR, ROOT
from train_models import BLUE, GRID, INK, INK_2, MUTED, SURFACE, points_above_expected

REPORTS = ROOT / "reports"
FIGURES = REPORTS / "figures"
MODELS = DATA_DIR / "models"
CURRY_ID = 201939
N_TREES = 300            # best iteration in train_models.py was 288
MIN_SHOTS_SEASON = 500   # to be ranked in a season
MIN_SHOTS_CAREER = 5000  # to appear on the career leaderboard


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def new_model() -> XGBClassifier:
    return XGBClassifier(
        n_estimators=N_TREES, learning_rate=0.05, max_depth=7, min_child_weight=50,
        subsample=0.8, colsample_bytree=0.8, tree_method="hist", enable_categorical=True,
        max_cat_to_onehot=1, n_jobs=-1, random_state=42,
    )


def crossfit(shots: pd.DataFrame, cols: list[str]) -> np.ndarray:
    p = np.full(len(shots), np.nan)
    seasons = sorted(shots["SEASON"].unique())
    for i, season in enumerate(seasons, start=1):
        held = (shots["SEASON"] == season).to_numpy()
        model = new_model()
        model.fit(shots.loc[~held, cols], shots.loc[~held, "SHOT_MADE_FLAG"])
        p[held] = model.predict_proba(shots.loc[held, cols])[:, 1]
        log(f"{i:>2}/{len(seasons)} {season}: scored {held.sum():,} shots")
    return p


def recalibrate(shots: pd.DataFrame) -> tuple[np.ndarray, dict[str, float]]:
    """One logit shift per season so that expected makes = actual makes."""
    p_cal = np.empty(len(shots))
    shifts = {}
    for season, idx in shots.groupby("SEASON").indices.items():
        z = logit(np.clip(shots["p_raw"].to_numpy()[idx], 1e-6, 1 - 1e-6))
        made = shots["SHOT_MADE_FLAG"].to_numpy()[idx].sum()
        shift = brentq(lambda d: expit(z + d).sum() - made, -2, 2)
        p_cal[idx] = expit(z + shift)
        shifts[season] = shift
    return p_cal, shifts


def season_check(shots: pd.DataFrame, shifts: dict[str, float]) -> pd.DataFrame:
    rows = []
    for season, g in shots.groupby("SEASON"):
        xpts_raw = (g["p_raw"] * g["points_value"]).sum()
        rows.append({
            "SEASON": season, "shots": len(g), "actual_points": int(g["points"].sum()),
            "expected_points_raw": round(xpts_raw),
            "gap_pct_raw": (g["points"].sum() - xpts_raw) / xpts_raw * 100,
            "logit_shift": shifts[season],
            "expected_points_recal": round(g["xpts"].sum()),
            "gap_pct_recal": (g["points"].sum() - g["xpts"].sum()) / g["xpts"].sum() * 100,
            "log_loss_raw": log_loss(g["SHOT_MADE_FLAG"], g["p_raw"]),
            "log_loss_recal": log_loss(g["SHOT_MADE_FLAG"], g["p"]),
            "auc": roc_auc_score(g["SHOT_MADE_FLAG"], g["p"]),
        })
    return pd.DataFrame(rows)


def curry_by_season(shots: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for season, g in shots.groupby("SEASON"):
        t = points_above_expected(g, g["p"].to_numpy())
        ranked = t[t["shots"] >= MIN_SHOTS_SEASON].reset_index(drop=True)
        c = t[t["PLAYER_ID"] == CURRY_ID]
        if c.empty:
            continue
        c = c.assign(SEASON=season, players_ranked=len(ranked))
        hit = ranked.index[ranked["PLAYER_ID"] == CURRY_ID]
        c["pae_rank"] = int(hit[0]) + 1 if len(hit) else pd.NA   # NA when under the shot minimum
        rows.append(c)
    cols = ["SEASON", "shots", "threes", "fg_pct", "pts_per_shot", "xpts_per_shot", "pae",
            "pae_per_100", "pae_rank", "players_ranked"]
    return pd.concat(rows)[cols]


def curry_by_zone(shots: pd.DataFrame) -> pd.DataFrame:
    c = shots[shots["PLAYER_ID"] == CURRY_ID]
    g = c.groupby("SHOT_ZONE_BASIC").agg(
        shots=("SHOT_ID", "size"), fg_pct=("SHOT_MADE_FLAG", "mean"),
        points=("points", "sum"), xpts=("xpts", "sum"),
    ).reset_index()
    g["share_of_shots"] = g["shots"] / g["shots"].sum()
    g["expected_fg_pct"] = c.groupby("SHOT_ZONE_BASIC")["p"].mean().values
    g["pae"] = g["points"] - g["xpts"]
    g["pae_per_100"] = g["pae"] / g["shots"] * 100
    return g.sort_values("shots", ascending=False)


def plot_curry(curry: pd.DataFrame, path) -> None:
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10})
    fig, ax = plt.subplots(figsize=(10, 5.2), dpi=160)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)

    x = np.arange(len(curry))
    small = curry["shots"] < MIN_SHOTS_SEASON
    colours = np.where(small, "#c3c2b7", BLUE)
    ax.bar(x, curry["pae_per_100"], width=0.62, color=colours, zorder=3)
    ax.axhline(0, color="#c3c2b7", lw=1, zorder=2)

    # Selective labels: seasons ranked 1st in the NBA, the latest season, and small-sample seasons
    vals = curry["pae_per_100"].to_numpy()
    ranks = curry["pae_rank"].to_numpy()
    first = {i for i, r in enumerate(ranks) if not pd.isna(r) and int(r) == 1}
    for i in sorted({len(curry) - 1} | first):
        v = vals[i]
        text = f"#1\n{v:+.1f}" if i in first else f"{v:+.1f}"
        ax.text(i, v + 0.5, text, ha="center", va="bottom", color=INK, fontsize=8.5,
                fontweight="bold", linespacing=1.1)
    for i in np.where(small)[0]:
        v = vals[i]
        ax.text(i, (v if v > 0 else 0) + 0.6, f"{int(curry['shots'].iloc[i])} shots",
                ha="center", va="bottom", color=MUTED, fontsize=7.5)

    ax.set_xticks(x)
    ax.set_xticklabels(curry["SEASON"], rotation=45, ha="right", color=MUTED, fontsize=8.5)
    ax.set_ylabel("Points above expected per 100 shots", color=INK_2)
    ax.set_title("Stephen Curry: points above an average shooter that season, taking the same shots",
                 color=INK, fontsize=11.5, loc="left", pad=22)
    ax.text(0, 1.02, "Every shot scored by a model that never saw that season. "
                     "#1 = best in the NBA that season (min 500 shots). Grey = fewer than 500 shots.",
            transform=ax.transAxes, color=MUTED, fontsize=8.5)
    ax.set_ylim(min(-9, np.nanmin(vals) - 1.5), np.nanmax(vals) + 4)
    ax.grid(axis="y", color=GRID, lw=0.6, zorder=0)
    ax.tick_params(axis="y", colors=MUTED)
    ax.tick_params(axis="x", length=0)
    for side in ["top", "right", "bottom"]:
        ax.spines[side].set_visible(False)
    ax.spines["left"].set_color("#c3c2b7")
    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reuse", action="store_true", help="reuse saved predictions instead of refitting")
    parser.add_argument("--features", choices=["location", "full"], default="location",
                        help="'full' adds shot descriptions, which leak the outcome before 2017-18")
    args = parser.parse_args()
    sfx = "" if args.features == "location" else "_with_labels"
    cols = NUMERIC if args.features == "location" else NUMERIC + CATEGORICAL
    for d in (REPORTS, FIGURES, MODELS):
        d.mkdir(parents=True, exist_ok=True)

    log(f"Loading shots ... (features: {args.features})")
    shots, _ = add_features(load_shots())   # category levels from all seasons, so encoding is identical
    log(f"{len(shots):,} shots, {shots['SEASON'].nunique()} seasons")

    pred_path = MODELS / f"crossfit_predictions{sfx}.csv.gz"
    if args.reuse:
        saved = pd.read_csv(pred_path, usecols=["SHOT_ID", "p"]).rename(columns={"p": "p_raw"})
        shots = shots.merge(saved, on="SHOT_ID", how="left", validate="one_to_one")
    else:
        shots["p_raw"] = crossfit(shots, cols)
        shots[["SHOT_ID", "SEASON", "PLAYER_ID", "SHOT_MADE_FLAG", "points_value", "p_raw"]].rename(
            columns={"p_raw": "p"}).to_csv(pred_path, index=False, float_format="%.5f")
    assert shots["p_raw"].notna().all(), "some shots were not scored"

    shots["p"], shifts = recalibrate(shots)
    shots["xpts"] = shots["p"] * shots["points_value"]

    check = season_check(shots, shifts)
    check.to_csv(REPORTS / f"crossfit_check_by_season{sfx}.csv", index=False, float_format="%.4f")
    print("\nSanity check, expected vs actual points by season (raw model, then recalibrated):")
    print(check.round(3).to_string(index=False))

    curry = curry_by_season(shots)
    curry.to_csv(REPORTS / f"curry_career_pae{sfx}.csv", index=False, float_format="%.3f")
    print("\nCurry, season by season:")
    print(curry.round(3).to_string(index=False))

    zone = curry_by_zone(shots)
    zone.to_csv(REPORTS / f"curry_pae_by_zone{sfx}.csv", index=False, float_format="%.3f")
    print("\nCurry by zone, career:")
    print(zone.round(3).to_string(index=False))

    board = points_above_expected(shots, shots["p"].to_numpy())
    board = board[board["shots"] >= MIN_SHOTS_CAREER].reset_index(drop=True)
    board.index += 1
    board.to_csv(REPORTS / f"pae_career_leaderboard{sfx}.csv", index_label="rank", float_format="%.3f")
    print(f"\nCareer leaderboard, 2009-10 to 2025-26 (min {MIN_SHOTS_CAREER:,} shots), top 15:")
    print(board.head(15)[["PLAYER_NAME", "shots", "pts_per_shot", "xpts_per_shot", "pae",
                          "pae_per_100"]].round(3).to_string())

    plot_curry(curry, FIGURES / f"curry_career_pae{sfx}.png")

    # Robustness: compare Curry under both models once both exist
    loc_p, lab_p = REPORTS / "curry_career_pae.csv", REPORTS / "curry_career_pae_with_labels.csv"
    if loc_p.exists() and lab_p.exists():
        keep = ["SEASON", "shots", "xpts_per_shot", "pae_per_100", "pae_rank"]
        both = pd.read_csv(loc_p)[keep].merge(pd.read_csv(lab_p)[keep], on=["SEASON", "shots"],
                                              suffixes=("_location", "_with_labels"))
        both.to_csv(REPORTS / "curry_robustness.csv", index=False, float_format="%.3f")
        print("\nRobustness, Curry under location-only (main) vs with-labels model:")
        print(both.round(3).to_string(index=False))
    log("Done.")


if __name__ == "__main__":
    main()
