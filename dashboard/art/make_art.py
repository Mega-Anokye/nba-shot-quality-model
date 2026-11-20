"""Draw the dashboard artwork from scratch (no third-party images or logos).

  court.png    half court in NBA shot-chart coordinates (tenths of a foot, basket at 0,0):
               x from -250 to 250, y from -47.5 (baseline) to 422.5 (half-court line).
               The image edges ARE those limits, so it can sit behind a scatter chart whose
               axes are fixed to the same range.
  ball.png     basketball icon, transparent background
  banner.png   header strip: navy with gold stripe, court arcs and a ball
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Arc, Circle, Rectangle

HERE = Path(__file__).resolve().parent
NAVY, ROYAL, GOLD = "#1D428A", "#2b62c4", "#FFC72C"
WOOD, WOOD_DARK, PAINT = "#f3e3c6", "#e9d3ad", "#dce7f7"
LINE = NAVY
X0, X1, Y0, Y1 = -250, 250, -47.5, 422.5


def court(ax, lw=2.2, colour=LINE):
    # wood planks
    for i, x in enumerate(np.arange(X0, X1, 25)):
        ax.add_patch(Rectangle((x, Y0), 25, Y1 - Y0, color=WOOD if i % 2 else WOOD_DARK, zorder=0))
    ax.add_patch(Rectangle((-80, Y0), 160, 190, facecolor=PAINT, edgecolor=colour, lw=lw, zorder=1))  # paint
    ax.add_patch(Rectangle((-60, Y0), 120, 190, fill=False, edgecolor=colour, lw=lw * 0.6, zorder=2))
    ax.add_patch(Arc((0, 142.5), 120, 120, theta1=0, theta2=180, edgecolor=colour, lw=lw, zorder=2))  # FT top
    ax.add_patch(Arc((0, 142.5), 120, 120, theta1=180, theta2=0, edgecolor=colour, lw=lw * 0.6,
                     linestyle=(0, (5, 5)), zorder=2))
    ax.add_patch(Arc((0, 0), 80, 80, theta1=0, theta2=180, edgecolor=colour, lw=lw, zorder=2))  # restricted
    ax.plot([-30, 30], [-7.5, -7.5], color=colour, lw=lw * 1.4, zorder=3)  # backboard
    ax.add_patch(Circle((0, 0), 7.5, fill=False, edgecolor="#eb6834", lw=lw, zorder=3))  # rim
    # three-point line: corners at x = +/-220 up to y = 92.5, then the 23.75 ft arc
    ax.plot([-220, -220], [Y0, 92.5], color=colour, lw=lw, zorder=2)
    ax.plot([220, 220], [Y0, 92.5], color=colour, lw=lw, zorder=2)
    a = np.degrees(np.arcsin(92.5 / 237.5))
    ax.add_patch(Arc((0, 0), 475, 475, theta1=a, theta2=180 - a, edgecolor=colour, lw=lw, zorder=2))
    # half-court circle
    ax.add_patch(Circle((0, Y1), 60, facecolor=GOLD, alpha=0.35, edgecolor=colour, lw=lw, zorder=1))
    ax.add_patch(Arc((0, Y1), 20, 20, theta1=180, theta2=360, edgecolor=colour, lw=lw, zorder=2))
    ax.add_patch(Rectangle((X0, Y0), X1 - X0, Y1 - Y0, fill=False, edgecolor=colour, lw=lw * 2, zorder=3))


def make_court():
    fig = plt.figure(figsize=(10, 9.4), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1])
    court(ax)
    ax.set_xlim(X0, X1)
    ax.set_ylim(Y0, Y1)
    ax.axis("off")
    fig.savefig(HERE / "court.png", dpi=100)
    plt.close(fig)


def draw_ball(ax, cx, cy, r, lw):
    ax.add_patch(Circle((cx, cy), r, facecolor="#e8772e", edgecolor="#3b1f0e", lw=lw, zorder=5))
    ax.add_patch(Circle((cx - r * 0.3, cy + r * 0.3), r * 0.35, facecolor="#f39a55", alpha=0.6, lw=0, zorder=5))
    t = np.linspace(0, 2 * np.pi, 200)
    ax.plot([cx - r, cx + r], [cy, cy], color="#3b1f0e", lw=lw, zorder=6)
    ax.plot([cx, cx], [cy - r, cy + r], color="#3b1f0e", lw=lw, zorder=6)
    for side in (-1, 1):  # curved seams
        x = cx + side * (r * 0.62 - r * 0.45 * np.cos(t[:100] - np.pi / 2) * 0)  # anchor
        yy = np.linspace(-r * 0.93, r * 0.93, 100)
        xx = cx + side * (r * 0.95 - np.sqrt(np.clip((r * 1.25) ** 2 - yy ** 2, 0, None)) + r * 0.3)
        ax.plot(xx, cy + yy, color="#3b1f0e", lw=lw, zorder=6)


def make_ball():
    fig = plt.figure(figsize=(2.56, 2.56), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1])
    draw_ball(ax, 0, 0, 1, 3.2)
    ax.set_xlim(-1.08, 1.08)
    ax.set_ylim(-1.08, 1.08)
    ax.set_aspect("equal")
    ax.axis("off")
    fig.savefig(HERE / "ball.png", dpi=100, transparent=True)
    plt.close(fig)


def make_banner():
    w, h = 1280, 120
    fig = plt.figure(figsize=(w / 100, h / 100), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, w)
    ax.set_ylim(0, h)
    ax.add_patch(Rectangle((0, 0), w, h, color=NAVY))
    ax.add_patch(Rectangle((0, 0), w, 8, color=GOLD))
    for r, a in [(300, 0.10), (240, 0.08), (140, 0.10)]:   # faint court arcs on the right
        ax.add_patch(Arc((w - 60, -40), r * 2, r * 2, theta1=90, theta2=180, edgecolor="white", alpha=a, lw=3))
    ax.add_patch(Circle((w - 60, -40), 40, fill=False, edgecolor="white", alpha=0.12, lw=3))
    ax.set_aspect("equal")
    draw_ball(ax, 62, 64, 40, 2.2)
    ax.axis("off")
    fig.savefig(HERE / "banner.png", dpi=100)
    plt.close(fig)


if __name__ == "__main__":
    make_court()
    make_ball()
    make_banner()
    print("Saved court.png, ball.png, banner.png to", HERE)
