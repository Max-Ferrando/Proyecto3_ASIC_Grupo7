#!/usr/bin/env python3
"""plot_sweep.py - Grafica un barrido (CSV de sweep.py).

  python3 asic/scripts/plot_sweep.py asic/strategy_A/sweep_FP_CORE_UTIL.csv \
      --x util_% --y route_drc grt_overflow -o figuras/util_vs_drc.png
"""
import argparse
import csv

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

LABELS = {
    "util_%": "Utilizacion de celdas (%)", "FP_CORE_UTIL_%": "FP_CORE_UTIL (%)",
    "route_drc": "Violaciones DRC del ruteo detallado", "grt_overflow": "Overflow del ruteo global",
    "CLOCK_PERIOD_ns": "CLOCK_PERIOD (ns)", "setup_ws_ss": "Setup WS, corner lento (ns)",
    "setup_ws_tt": "Setup WS, corner tipico (ns)", "die_um2": "Area del die (um2)",
    "cell_area_um2": "Area de celdas (um2)",
}


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


ap = argparse.ArgumentParser()
ap.add_argument("csv")
ap.add_argument("--x", required=True)
ap.add_argument("--y", nargs="+", required=True)
ap.add_argument("-o", "--out", default="sweep.png")
ap.add_argument("--title", default="")
a = ap.parse_args()

rows = list(csv.DictReader(open(a.csv)))
rows = [r for r in rows if num(r.get(a.x)) is not None]
rows.sort(key=lambda r: num(r[a.x]))
fig, ax = plt.subplots(figsize=(6.4, 4))
axes = [ax]
for i, col in enumerate(a.y):
    axis = ax if i == 0 else ax.twinx()
    xs = [num(r[a.x]) for r in rows if num(r.get(col)) is not None]
    ys = [num(r[col]) for r in rows if num(r.get(col)) is not None]
    color = ["#2f6fd6", "#d65f2f", "#2a9d5c"][i % 3]
    axis.plot(xs, ys, "o-", color=color, label=LABELS.get(col, col))
    axis.set_ylabel(LABELS.get(col, col), color=color)
    if i:
        axes.append(axis)
ax.set_xlabel(LABELS.get(a.x, a.x))
ax.grid(alpha=0.3)
if a.title:
    ax.set_title(a.title)
fig.tight_layout()
fig.savefig(a.out, dpi=200)
print("Figura:", a.out)
