# Shot Quality vs Shot Making: An Expected-Points Model for Stephen Curry

> **Status:** 🏗️ In progress. Data pipeline done (2.73 million shots, fully reconciled). First model done and tested on unseen seasons. Next: points above expected for Curry's whole career.

## The question

How much of Stephen Curry's scoring comes from **getting good shots** (shot quality), and how much from **making hard ones** (shot making)?

Raw field-goal percentage mixes the two together. A player who only takes layups can shoot 65% and still be an average scorer. This project builds an **expected-points (xPTS) model**: for every shot, it estimates how many points an average NBA player would score from the same spot and situation. Then it measures how far Curry (and every other shooter) beats that expectation.

## Method

| Step | What | Tools | Status |
|---|---|---|---|
| 1. Data | Pull every NBA regular-season shot, 2013-14 to 2025-26, plus all of Curry's since 2009-10 | Python, `nba_api` | ✅ |
| 2. Storage | Star schema: `fact_shot`, `dim_player`, `dim_team`, `official_team_totals` | SQLite, SQL | ✅ |
| 3. Checks | Reconcile every team-season against official totals; data quality checks | Python, SQL | ✅ |
| 4. Model | Predict make probability per shot: zone baseline vs logistic regression vs XGBoost | scikit-learn, XGBoost | ✅ |
| 5. Metric | **Points Above Expected (PAE)** = actual points − expected points | pandas | 🟡 test seasons done |
| 6. Dashboard | Shot charts, PAE leaderboard, Curry by zone and season | Power BI | ⏳ |
| 7. Automation | Nightly data refresh during the season | GitHub Actions | ⏳ |

## The data, and how it was checked

| | |
|---|---|
| League shots | **2,729,498** regular-season attempts, 13 seasons, 1,693 players, 30 teams |
| Curry shots | **19,155** regular-season attempts, 2009-10 to 2025-26 |
| Reconciliation | All **390 team-seasons** tie exactly to the NBA's official FGA, FGM, 3PA and 3PM |
| Duplicates | None (unique key: game ID + event ID) |
| Cross-check | Curry's shots in the league table match his separate pull, shot for shot |
| Known gap | **407 shots (0.015%)** from 2013-14 to 2016-17 have no coordinates or zone in NBA.com's own data. They stay in the table so totals tie, and are excluded from the model. |

Results: `data_checks/league_reconciliation_by_season.csv`, `league_quality_checks.csv`, `curry_reconciliation.csv`.

### Two things the API doesn't tell you

1. **NBA.com silently hangs** on requests that don't carry browser-style headers: no error, just a timeout. `src/nba_common.py` sends the headers a browser on nba.com would.
2. **A league-wide shot request is silently truncated.** Asking for all 2015-16 shots in one call returned 106,496 rows; the true total is 208,049. Pulling team by team (30 calls per season) returns every shot, and the reconciliation proves it.

## The model

**Features** (only what is known before the ball leaves the shooter's hand): distance and angle from the basket, two or three, corner three, shot description (55 types such as "Pullup Jump Shot" or "Driving Layup"), shot family, time left in the period, end-of-quarter heave, overtime, and season (to capture the league getting better at shooting).

**Validation:** time-based. Trained on 2013-14 to 2022-23 (2.07 million shots), tuned on 2023-24, and judged on **2024-25 and 2025-26 (438,687 shots the model never saw).**

| Model (unseen seasons) | Log loss ↓ | Brier ↓ | AUC ↑ | Predicted FG% | Expected vs actual points |
|---|---|---|---|---|---|
| Zone baseline (league FG% per court zone) | 0.659 | 0.233 | 0.635 | 45.0% | under by 3.7% |
| Logistic regression (splines) | 0.643 | 0.227 | 0.644 | 46.1% | under by 1.4% |
| **XGBoost** | **0.636** | **0.224** | **0.661** | **47.0%** | **within 0.4%** |

Actual FG% in those seasons: 46.9%. XGBoost is used from here on.

![Calibration chart](reports/figures/calibration.png)

**What this says:**
- The zone baseline, the method most dashboards use, **under-predicts by almost 4%**. It averages over the past, and the league keeps getting better at shooting. Adding season as a feature fixes most of that.
- An AUC of 0.66 is in line with public shot models. Without defender distance, no model can know whether a shot was contested, so most of what is left is genuine uncertainty.

## First look: Curry on unseen seasons

| Season | Shots | Points per shot | Expected per shot (shot quality) | Points above expected | Per 100 shots | Rank (min 500 shots) |
|---|---|---|---|---|---|---|
| 2024-25 | 1,258 | 1.144 | 1.025 | **+150** | +11.9 | 6th of 181 |
| 2025-26 | 799 | 1.174 | 1.039 | **+108** | +13.5 | 10th of 182 |

In his late 30s, Curry still turns an average-looking shot diet (about 1.03 expected points per shot, close to league average) into about 1.16. Almost all of his edge is **shot making**, not shot selection. Across both seasons combined (min 1,000 shots) he is 7th in the league, behind Jokić, Durant, Gilgeous-Alexander, Pritchard, Dončić and Murray. Full table: `reports/pae_leaderboard_test.csv`.

## Limitations (known up front)

- **Free throws aren't counted.** Expected points cover the field goal only, not and-ones or shooting fouls drawn.
- **No defender data.** Public shot data has location and shot type, but not how close the nearest defender was. Part of what the model calls "shot making" will really be "shot difficulty it can't see."
- **No player tracking.** Off-ball movement and gravity aren't in the public data.

## Repository layout

```
├── src/
│   ├── nba_common.py          shared settings: headers, retries, data location
│   ├── pull_curry_shots.py    Curry's shots + official totals, 2009-10 onwards
│   ├── pull_league_shots.py   every shot, team by team, resumable by season
│   ├── build_database.py      loads the season files into the SQLite star schema
│   ├── check_curry_shots.py   Curry reconciliation
│   ├── check_league_shots.py  league reconciliation + data quality checks
│   ├── features.py            loads shots and builds model features
│   └── train_models.py        trains, compares and calibrates the three models
├── reports/                   model comparison, calibration, leaderboards, figures
├── notebooks/                 exploration and modelling
├── data_checks/               check results (committed)
├── dashboard/                 Power BI file and screenshots
└── requirements.txt           pinned Python packages
```

The data itself (~700 MB) is **not** in the repo. It is saved to `~/nba-shot-quality-data/` (override with the `NBA_DATA_DIR` environment variable) and can be rebuilt from the scripts.

## How to run

> Tip: if the project sits in a OneDrive folder, create the virtual environment outside it (e.g. `%USERPROFILE%\.venvs\`) so OneDrive doesn't try to sync thousands of package files.

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

python src/pull_curry_shots.py     # ~1 minute
python src/pull_league_shots.py    # ~12 minutes
python src/build_database.py
python src/check_curry_shots.py
python src/check_league_shots.py
python src/train_models.py         # ~3 minutes
```

## Author

Mega Anokye, Data Analyst · [github.com/Mega-Anokye](https://github.com/Mega-Anokye)
