"""Draw the portfolio card image: Steph's 2015-16 shots on our court, plus the headline number.

Output: dashboard/art/portfolio-card.jpg (1600 x 900)
"""

from pathlib import Path

import matplotlib.image as mpimg
import matplotlib.pyplot as plt
import pandas as pd

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data" / "fact_curry_shot.csv"
NAVY, ROYAL, GOLD, ORANGE = "#1D428A", "#2b62c4", "#FFC72C", "#eb6834"


def main() -> None:
    shots = pd.read_csv(DATA)
    s = shots[(shots["SEASON"] == "2015-16") & (shots["LOC_Y"] <= 422.5)]

    fig = plt.figure(figsize=(16, 9), dpi=100)
    fig.patch.set_facecolor(NAVY)

    # Court with shots (left)
    ax = fig.add_axes([0.03, 0.06, 0.47, 0.88])
    ax.imshow(mpimg.imread(HERE / "court.png"), extent=[-250, 250, -47.5, 422.5], zorder=0)
    miss, made = s[s["SHOT_MADE_FLAG"] == 0], s[s["SHOT_MADE_FLAG"] == 1]
    ax.scatter(miss["LOC_X"], miss["LOC_Y"], marker="x", s=22, c=ORANGE, linewidths=1.3, alpha=0.75, zorder=2)
    ax.scatter(made["LOC_X"], made["LOC_Y"], marker="o", s=24, c=ROYAL, edgecolors="white", linewidths=0.5, zorder=3)
    ax.set_xlim(-250, 250)
    ax.set_ylim(-47.5, 422.5)
    ax.axis("off")

    # Text (right)
    fig.text(0.55, 0.80, "“The greatest shooter\nGod ever created.”", color="white", fontsize=34,
             fontweight="bold", fontstyle="italic", va="top", linespacing=1.15)
    fig.text(0.55, 0.53, "+3,188", color=GOLD, fontsize=88, fontweight="bold", va="top")
    fig.text(0.55, 0.33, "extra points vs an average NBA shooter\ntaking the exact same shots", color="white",
             fontsize=21, va="top", linespacing=1.35)
    fig.text(0.55, 0.17, "No. 1 in the NBA since 2009  ·  3.5 million shots checked", color=GOLD, fontsize=17,
             va="top")
    fig.savefig(HERE / "portfolio-card.jpg", dpi=100, facecolor=NAVY, pil_kwargs={"quality": 88})
    plt.close(fig)
    print(f"Saved portfolio-card.jpg ({len(s):,} shots: {len(made):,} made, {len(miss):,} missed)")


if __name__ == "__main__":
    main()
