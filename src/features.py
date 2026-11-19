"""Load shots from the database and turn them into model features.

Only information known *before* the ball leaves the shooter's hand is used:
where the shot is taken, what kind of shot it is, and the game clock.
"""

import sqlite3

import numpy as np
import pandas as pd

from nba_common import DB_PATH

# Time-based split: learn from the past, judge on seasons the model has never seen.
TRAIN_SEASONS = [f"{y}-{str(y + 1)[-2:]}" for y in range(2013, 2023)]   # 2013-14 .. 2022-23
VALID_SEASONS = ["2023-24"]                                              # early stopping / tuning
TEST_SEASONS = ["2024-25", "2025-26"]                                    # final, untouched

NUMERIC = ["dist_ft", "abs_angle", "is_three", "is_corner3", "secs_left_period",
           "last_2_secs", "is_ot", "season_num"]
CATEGORICAL = ["action_type", "shot_family"]
MIN_ACTION_COUNT = 500   # rarer shot descriptions are grouped into "Other"

LOAD_SQL = """
SELECT s.SHOT_ID, s.SEASON, s.GAME_ID, s.PLAYER_ID, p.PLAYER_NAME, s.TEAM_ID,
       s.PERIOD, s.MINUTES_REMAINING, s.SECONDS_REMAINING, s.ACTION_TYPE, s.SHOT_TYPE,
       s.SHOT_ZONE_BASIC, s.SHOT_ZONE_AREA, s.SHOT_ZONE_RANGE,
       s.LOC_X, s.LOC_Y, s.SHOT_MADE_FLAG
FROM fact_shot s
JOIN dim_player p USING (PLAYER_ID)
WHERE s.LOC_X IS NOT NULL AND s.LOC_Y IS NOT NULL   -- excludes the 407 shots with no location
"""


def load_shots() -> pd.DataFrame:
    with sqlite3.connect(DB_PATH) as conn:
        return pd.read_sql(LOAD_SQL, conn)


def shot_family(action: pd.Series) -> pd.Series:
    """Collapse ~70 shot descriptions into a few broad families."""
    a = action.str.lower()
    conditions = [
        a.str.contains("dunk"),
        a.str.contains("tip") | a.str.contains("putback"),
        a.str.contains("layup") | a.str.contains("finger roll"),
        a.str.contains("hook"),
        a.str.contains("floating") | a.str.contains("floater"),
        a.str.contains("fadeaway") | a.str.contains("turnaround"),
        a.str.contains("step back"),
        a.str.contains("pullup") | a.str.contains("pull-up"),
        a.str.contains("jump"),
    ]
    return pd.Series(np.select(conditions, SHOT_FAMILIES[:-1], default="other"), index=action.index)


SHOT_FAMILIES = ["dunk", "tip", "layup", "hook", "floater", "fadeaway", "step_back", "pull_up",
                 "jump_shot", "other"]


def add_features(df: pd.DataFrame, action_levels: list[str] | None = None) -> tuple[pd.DataFrame, list[str]]:
    """Add model features. Pass the training set's action levels when transforming other seasons."""
    out = df.copy()
    out["dist_ft"] = np.hypot(out["LOC_X"], out["LOC_Y"]) / 10.0          # LOC units are tenths of a foot
    out["abs_angle"] = np.degrees(np.abs(np.arctan2(out["LOC_X"], out["LOC_Y"])))
    out["is_three"] = (out["SHOT_TYPE"] == "3PT Field Goal").astype(int)
    out["is_corner3"] = out["SHOT_ZONE_BASIC"].isin(["Left Corner 3", "Right Corner 3"]).astype(int)
    out["secs_left_period"] = out["MINUTES_REMAINING"] * 60 + out["SECONDS_REMAINING"]
    out["last_2_secs"] = (out["secs_left_period"] <= 2).astype(int)
    out["is_ot"] = (out["PERIOD"] > 4).astype(int)
    out["season_num"] = out["SEASON"].str[:4].astype(int)
    out["shot_family"] = shot_family(out["ACTION_TYPE"])

    if action_levels is None:
        counts = out["ACTION_TYPE"].value_counts()
        action_levels = sorted(counts[counts >= MIN_ACTION_COUNT].index.tolist()) + ["Other"]
    out["action_type"] = out["ACTION_TYPE"].where(out["ACTION_TYPE"].isin(action_levels), "Other")
    out["action_type"] = pd.Categorical(out["action_type"], categories=action_levels)
    # Fixed category order, so every season is encoded the same way.
    out["shot_family"] = pd.Categorical(out["shot_family"], categories=SHOT_FAMILIES)

    out["points_value"] = np.where(out["is_three"] == 1, 3, 2)
    out["points"] = out["points_value"] * out["SHOT_MADE_FLAG"]
    return out, action_levels
