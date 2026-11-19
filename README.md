# Shot Quality vs Shot Making: An Expected-Points Model for Stephen Curry

> **Status:** 🏗️ In progress. Step 1 (data pipeline) is being built.

## The question

How much of Stephen Curry's scoring comes from **getting good shots** (shot quality), and how much from **making hard ones** (shot making)?

Raw field-goal percentage mixes the two together. A player who only takes layups can shoot 65% and still be an average scorer. This project builds an **expected-points (xPTS) model**: for every shot, it estimates how many points an average NBA player would score from the same spot and situation. Then it measures how far Curry (and every other shooter) beats that expectation.

## Method (planned)

| Step | What | Tools |
|---|---|---|
| 1. Data | Pull every NBA shot since 2013-14 from NBA.com's stats API | Python, `nba_api` |
| 2. Storage | Clean the data and store it in a relational schema | SQLite, SQL |
| 3. Checks | Reconcile shot counts against official season totals | Python, `data_checks/` |
| 4. Model | Predict make probability per shot: logistic regression baseline, then XGBoost | scikit-learn, XGBoost |
| 5. Metric | **Points Above Expected (PAE)** = actual points − expected points | pandas |
| 6. Dashboard | Shot charts, PAE leaderboard, Curry by zone and season | Power BI |
| 7. Automation | Nightly data refresh during the season | GitHub Actions |

## Repository layout

```
├── src/                  Python scripts (data pull, checks, model)
├── notebooks/            Exploration and modelling notebooks
├── data/
│   ├── raw/              Raw API pulls (not committed)
│   └── processed/        Cleaned data (not committed)
├── data_checks/          Reconciliation results against official totals
├── dashboard/            Power BI file and screenshots
└── requirements.txt      Pinned Python packages
```

## Data checks

Every pull is reconciled against the NBA's official season totals (field-goal attempts, makes, 3-point attempts and makes). Results are saved to `data_checks/`, and any mismatch is reported, not hidden.

## Limitations (known up front)

- **No defender data.** Public shot data has location and shot type, but not how close the nearest defender was. Part of what the model calls "shot making" will really be "shot difficulty it can't see."
- **No player tracking.** Off-ball movement and gravity aren't in the public data.

## Step 1 result: the data ties out

All 19,155 of Curry's regular-season shots from 2009-10 to 2025-26 were pulled. Every season matches the NBA's official totals exactly (attempts, makes, 3-point attempts, 3-point makes), and there are no duplicate shots. See `data_checks/curry_reconciliation.csv`.

## How to run

> Tip: if the project sits in a OneDrive folder, create the virtual environment outside it (e.g. `%USERPROFILE%\.venvs\`) so OneDrive doesn't try to sync thousands of package files.

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python src/pull_curry_shots.py
python src/check_curry_shots.py
```

## Author

Mega Anokye, Data Analyst · [github.com/Mega-Anokye](https://github.com/Mega-Anokye)
