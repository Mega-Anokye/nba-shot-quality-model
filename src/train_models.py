"""Train and compare three shot-make models, judged on seasons they have never seen.

  1. Zone baseline   league FG% for each of the NBA's court zones (what most dashboards use)
  2. Logistic        splines on distance and angle + shot type, game clock, season
  3. XGBoost         same features, gradient-boosted trees

Train 2013-14..2022-23, tune on 2023-24, test on 2024-25 and 2025-26.

Writes:
  reports/model_comparison.csv       log loss, Brier score, AUC, expected vs actual points
  reports/calibration.csv            predicted vs actual make rate by probability bin
  reports/figures/calibration.png
  reports/curry_first_look.csv       Curry's points above expected, test seasons
  reports/pae_leaderboard_test.csv   all players, test seasons
  <data dir>/models/                 fitted models + test-season predictions
"""

import json
import time

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, SplineTransformer, StandardScaler
from xgboost import XGBClassifier

from features import (CATEGORICAL, NUMERIC, TEST_SEASONS, TRAIN_SEASONS, VALID_SEASONS,
                      add_features, load_shots)
from nba_common import DATA_DIR, ROOT

REPORTS = ROOT / "reports"
FIGURES = REPORTS / "figures"
MODELS = DATA_DIR / "models"
CURRY_ID = 201939
ZONE = ["SHOT_ZONE_BASIC", "SHOT_ZONE_AREA", "SHOT_ZONE_RANGE"]

# Chart colours: validated default palette (categorical slots 1-3) and neutral inks.
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
SURFACE, INK, INK_2, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9"


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# ---------- models ----------

def fit_zone_baseline(train: pd.DataFrame):
    rates = train.groupby(ZONE, observed=True)["SHOT_MADE_FLAG"].mean().rename("p_zone")
    overall = train["SHOT_MADE_FLAG"].mean()

    def predict(df: pd.DataFrame) -> np.ndarray:
        return df.join(rates, on=ZONE)["p_zone"].fillna(overall).to_numpy()
    return predict


def fit_logistic(train: pd.DataFrame) -> Pipeline:
    prep = ColumnTransformer([
        ("dist", SplineTransformer(n_knots=14, degree=3, knots="quantile"), ["dist_ft"]),
        ("angle", SplineTransformer(n_knots=6, degree=3), ["abs_angle"]),
        ("clock", SplineTransformer(n_knots=5, degree=3), ["secs_left_period"]),
        ("flags", "passthrough", ["is_three", "is_corner3", "last_2_secs", "is_ot"]),
        ("season", StandardScaler(), ["season_num"]),
        ("cats", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL),
    ])
    model = Pipeline([("prep", prep), ("lr", LogisticRegression(max_iter=500, C=1.0))])
    model.fit(train[NUMERIC + CATEGORICAL], train["SHOT_MADE_FLAG"])
    return model


def fit_xgboost(train: pd.DataFrame, valid: pd.DataFrame) -> XGBClassifier:
    model = XGBClassifier(
        n_estimators=3000, learning_rate=0.05, max_depth=7, min_child_weight=50,
        subsample=0.8, colsample_bytree=0.8, tree_method="hist", enable_categorical=True,
        max_cat_to_onehot=1, eval_metric="logloss", early_stopping_rounds=100, n_jobs=-1,
    )
    cols = NUMERIC + CATEGORICAL
    model.fit(train[cols], train["SHOT_MADE_FLAG"],
              eval_set=[(valid[cols], valid["SHOT_MADE_FLAG"])], verbose=250)
    return model


# ---------- evaluation ----------

def score(name: str, split: str, df: pd.DataFrame, p: np.ndarray) -> dict:
    y = df["SHOT_MADE_FLAG"].to_numpy()
    xpts = (p * df["points_value"]).sum()
    return {
        "model": name, "split": split, "shots": len(df),
        "log_loss": log_loss(y, p), "brier": brier_score_loss(y, p), "auc": roc_auc_score(y, p),
        "actual_fg_pct": y.mean(), "predicted_fg_pct": p.mean(),
        "actual_points": int(df["points"].sum()), "expected_points": round(xpts),
        "points_gap_pct": (df["points"].sum() - xpts) / xpts * 100,
    }


def calibration_table(df: pd.DataFrame, preds: dict[str, np.ndarray], bins: int = 20) -> pd.DataFrame:
    rows = []
    edges = np.linspace(0, 1, bins + 1)
    for name, p in preds.items():
        b = np.clip(np.digitize(p, edges) - 1, 0, bins - 1)
        g = pd.DataFrame({"bin": b, "p": p, "y": df["SHOT_MADE_FLAG"].to_numpy()}).groupby("bin")
        t = g.agg(predicted=("p", "mean"), actual=("y", "mean"), shots=("y", "size")).reset_index()
        t["model"] = name
        rows.append(t[t["shots"] >= 200])
    return pd.concat(rows, ignore_index=True)


def plot_calibration(cal: pd.DataFrame, path) -> None:
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10})
    fig, ax = plt.subplots(figsize=(7, 6), dpi=160)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    ax.plot([0, 1], [0, 1], color=MUTED, lw=1, ls=(0, (4, 3)), zorder=1)
    ax.text(0.78, 0.64, "perfect calibration", color=MUTED, fontsize=8.5, ha="left")
    for name, colour in [("Zone baseline", ORANGE), ("Logistic", AQUA), ("XGBoost", BLUE)]:
        t = cal[cal["model"] == name]
        ax.plot(t["predicted"], t["actual"], color=colour, lw=2, marker="o", ms=5,
                markeredgecolor=SURFACE, markeredgewidth=1.2, label=name, zorder=3)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_xlabel("Predicted chance the shot goes in", color=INK_2)
    ax.set_ylabel("Share of shots that actually went in", color=INK_2)
    ax.set_title("Predicted vs actual make rate, 2024-25 and 2025-26 (unseen seasons)",
                 color=INK, fontsize=11, loc="left", pad=12)
    ax.grid(color=GRID, lw=0.6)
    for side in ["top", "right"]:
        ax.spines[side].set_visible(False)
    for side in ["left", "bottom"]:
        ax.spines[side].set_color("#c3c2b7")
    ax.tick_params(colors=MUTED)
    leg = ax.legend(loc="upper left", frameon=False)
    for txt in leg.get_texts():
        txt.set_color(INK_2)
    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


def points_above_expected(df: pd.DataFrame, p: np.ndarray) -> pd.DataFrame:
    d = df.assign(xpts=p * df["points_value"])
    g = d.groupby(["PLAYER_ID", "PLAYER_NAME"]).agg(
        shots=("SHOT_ID", "size"), threes=("is_three", "sum"),
        fg_pct=("SHOT_MADE_FLAG", "mean"), points=("points", "sum"), xpts=("xpts", "sum"),
    ).reset_index()
    g["pts_per_shot"] = g["points"] / g["shots"]
    g["xpts_per_shot"] = g["xpts"] / g["shots"]          # shot quality
    g["pae"] = g["points"] - g["xpts"]                    # shot making, total
    g["pae_per_100"] = g["pae"] / g["shots"] * 100        # shot making, per 100 shots
    return g.sort_values("pae", ascending=False)


# ---------- main ----------

def main() -> None:
    for d in (REPORTS, FIGURES, MODELS):
        d.mkdir(parents=True, exist_ok=True)

    log("Loading shots ...")
    raw = load_shots()
    train_raw = raw[raw["SEASON"].isin(TRAIN_SEASONS)]
    train, levels = add_features(train_raw)
    valid, _ = add_features(raw[raw["SEASON"].isin(VALID_SEASONS)], levels)
    test, _ = add_features(raw[raw["SEASON"].isin(TEST_SEASONS)], levels)
    log(f"train {len(train):,} | valid {len(valid):,} | test {len(test):,} | {len(levels)} shot types")

    log("Fitting zone baseline ...")
    zone = fit_zone_baseline(train)
    log("Fitting logistic regression ...")
    logit = fit_logistic(train)
    log("Fitting XGBoost ...")
    xgb = fit_xgboost(train, valid)
    log(f"XGBoost best iteration: {xgb.best_iteration}")

    cols = NUMERIC + CATEGORICAL
    results, test_preds = [], {}
    for split, df in [("valid", valid), ("test", test)]:
        preds = {
            "Zone baseline": zone(df),
            "Logistic": logit.predict_proba(df[cols])[:, 1],
            "XGBoost": xgb.predict_proba(df[cols])[:, 1],
        }
        results += [score(name, split, df, p) for name, p in preds.items()]
        if split == "test":
            test_preds = preds

    comparison = pd.DataFrame(results)
    comparison.to_csv(REPORTS / "model_comparison.csv", index=False, float_format="%.4f")
    print(comparison.round(4).to_string(index=False))

    cal = calibration_table(test, test_preds)
    cal.to_csv(REPORTS / "calibration.csv", index=False, float_format="%.4f")
    plot_calibration(cal, FIGURES / "calibration.png")

    # Save models + test predictions for the next steps
    joblib.dump(logit, MODELS / "logistic.joblib")
    xgb.save_model(MODELS / "xgboost.json")
    (MODELS / "action_levels.json").write_text(json.dumps(levels))
    preds_out = test[["SHOT_ID", "SEASON", "PLAYER_ID", "SHOT_MADE_FLAG", "points_value"]].copy()
    preds_out["p_zone"] = test_preds["Zone baseline"]
    preds_out["p_logistic"] = test_preds["Logistic"]
    preds_out["p_xgboost"] = test_preds["XGBoost"]
    preds_out.to_csv(MODELS / "test_predictions.csv.gz", index=False, float_format="%.5f")

    # First look: points above expected on the unseen seasons, using XGBoost
    pae = points_above_expected(test, test_preds["XGBoost"])
    pae.to_csv(REPORTS / "pae_leaderboard_test.csv", index=False, float_format="%.3f")
    curry_rows = []
    for season in TEST_SEASONS:
        s = test["SEASON"] == season
        t = points_above_expected(test[s], test_preds["XGBoost"][s.to_numpy()])
        rank = t.loc[t["shots"] >= 500].reset_index(drop=True)
        c = t[t["PLAYER_ID"] == CURRY_ID].assign(SEASON=season)
        c["pae_rank_min500"] = int(rank.index[rank["PLAYER_ID"] == CURRY_ID][0]) + 1
        c["players_min500"] = len(rank)
        curry_rows.append(c)
    curry = pd.concat(curry_rows)
    curry.to_csv(REPORTS / "curry_first_look.csv", index=False, float_format="%.3f")

    print("\nCurry, unseen seasons (XGBoost):")
    print(curry[["SEASON", "shots", "fg_pct", "pts_per_shot", "xpts_per_shot", "pae",
                 "pae_per_100", "pae_rank_min500", "players_min500"]].round(3).to_string(index=False))
    print("\nTop 10 points above expected, 2024-25 + 2025-26 (min 1,000 shots):")
    print(pae[pae["shots"] >= 1000].head(10)[["PLAYER_NAME", "shots", "pts_per_shot", "xpts_per_shot",
                                              "pae", "pae_per_100"]].round(3).to_string(index=False))
    log("Done.")


if __name__ == "__main__":
    main()
