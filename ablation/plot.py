"""Generate the hallucination-rate vs. parameter-count bar chart from the
ablation results CSV.

Usage (from repo root):
    python ablation/plot.py
    python ablation/plot.py --results ablation/results.csv --out ablation/hallucination_vs_params.png

Produces a grouped bar chart with one pair of bars per model size:
  - red  bar  = closed-book hallucination rate
  - blue bar  = KG-grounded hallucination rate
  - 95% CI error bars
  - double-headed arrow showing the grounding benefit (Δ)
"""

import argparse
import csv
import math
from collections import defaultdict
from pathlib import Path


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--results", default="ablation/results.csv")
    p.add_argument("--out", default="ablation/hallucination_vs_params.png")
    p.add_argument("--min-claims", type=int, default=1,
                   help="Skip rows where n_claims < this (avoids empty-answer noise)")
    return p.parse_args()


def _load(path: Path, min_claims: int) -> list[dict]:
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if int(row["n_claims"]) >= min_claims:
                rows.append({
                    "model_params": float(row["model_params"]),
                    "model": row["model"],
                    "setting": row["setting"],
                    "hallucination_rate": float(row["hallucination_rate"]),
                    "n_claims": int(row["n_claims"]),
                })
    return rows


def _aggregate(rows: list[dict]) -> dict[tuple, list[float]]:
    """(params, setting) → list of per-question hallucination rates."""
    groups: dict[tuple, list[float]] = defaultdict(list)
    for r in rows:
        groups[(r["model_params"], r["setting"])].append(r["hallucination_rate"])
    return groups


def _ci95(values: list[float]) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    var = sum((v - mean) ** 2 for v in values) / (n - 1)
    return 1.96 * math.sqrt(var / n)


def main() -> None:
    args = _parse_args()

    import matplotlib.pyplot as plt
    import numpy as np

    rows = _load(Path(args.results), args.min_claims)
    if not rows:
        raise SystemExit(f"No rows found in {args.results}")

    groups = _aggregate(rows)
    param_counts = sorted({r["model_params"] for r in rows})
    n_models = len(param_counts)

    settings  = ["closed", "grounded"]
    colors    = {"closed": "#d94f4f", "grounded": "#3a7fd5"}
    bar_label = {"closed": "Closed-book", "grounded": "KG-grounded"}

    x = np.arange(n_models)
    width = 0.32

    fig, ax = plt.subplots(figsize=(max(8, n_models * 1.6), 6))

    for si, setting in enumerate(settings):
        means, errs = [], []
        for params in param_counts:
            vals = groups.get((params, setting), [])
            mean = sum(vals) / len(vals) if vals else 0.0
            err  = _ci95(vals)
            means.append(mean)
            errs.append(err)

        offset = (si - 0.5) * width
        bars = ax.bar(
            x + offset, means, width,
            label=bar_label[setting],
            color=colors[setting],
            alpha=0.88,
            yerr=errs,
            capsize=5,
            error_kw={"elinewidth": 1.5, "ecolor": "#555"},
        )

        for bar, mean in zip(bars, means):
            if mean > 0.01:
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + max(errs) * 0.5 + 0.01,
                    f"{mean:.2f}",
                    ha="center", va="bottom", fontsize=8, color="#333",
                )

    # Double-headed arrows showing grounding benefit (Δ closed − grounded)
    for i, params in enumerate(param_counts):
        c_vals = groups.get((params, "closed"), [])
        g_vals = groups.get((params, "grounded"), [])
        if not c_vals or not g_vals:
            continue
        c_mean = sum(c_vals) / len(c_vals)
        g_mean = sum(g_vals) / len(g_vals)
        delta = c_mean - g_mean
        if delta > 0.03:
            x_arrow = x[i] + width * 0.9
            ax.annotate(
                "",
                xy=(x_arrow, g_mean),
                xytext=(x_arrow, c_mean),
                arrowprops=dict(arrowstyle="<->", color="#777", lw=1.4),
            )
            ax.text(
                x_arrow + 0.05,
                (c_mean + g_mean) / 2,
                f"−{delta:.2f}",
                color="#555", fontsize=8, va="center",
            )

    ax.set_xticks(x)
    ax.set_xticklabels(
        [f"{int(p) if p == int(p) else p}B" for p in param_counts],
        fontsize=11,
    )
    ax.set_xlabel("Model size (billions of parameters)", fontsize=12)
    ax.set_ylabel("Hallucination rate  (fraction unverifiable)", fontsize=12)
    ax.set_title(
        "Hallucination rate vs. model size\n"
        "Closed-book vs. KG-grounded  (Qwen3-VL-Instruct, NLI verifier)",
        fontsize=13,
    )
    ax.set_ylim(0, min(1.05, ax.get_ylim()[1] + 0.08))
    ax.legend(fontsize=11, loc="upper right")
    ax.grid(axis="y", alpha=0.3, linestyle="--")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    # Summary table below the plot
    col_labels = ["Model", "N", "Closed HR", "Grounded HR", "Δ (benefit)"]
    table_data = []
    for params in param_counts:
        c_vals = groups.get((params, "closed"), [])
        g_vals = groups.get((params, "grounded"), [])
        c_mean = sum(c_vals) / len(c_vals) if c_vals else float("nan")
        g_mean = sum(g_vals) / len(g_vals) if g_vals else float("nan")
        delta  = c_mean - g_mean
        label  = f"{int(params) if params == int(params) else params}B"
        table_data.append([label, len(c_vals),
                           f"{c_mean:.3f}", f"{g_mean:.3f}", f"{delta:+.3f}"])

    tbl = ax.table(
        cellText=table_data,
        colLabels=col_labels,
        loc="bottom",
        bbox=[0, -0.38, 1, 0.28],
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(9)
    for (r, c), cell in tbl.get_celld().items():
        cell.set_edgecolor("#ccc")
        if r == 0:
            cell.set_facecolor("#e8e8e8")

    plt.tight_layout()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out, dpi=150, bbox_inches="tight")
    print(f"Plot saved to {out}")

    # Print summary to stdout as well
    print(f"\n{'Model':<8}  {'N':>5}  {'Closed HR':>10}  {'Grounded HR':>12}  {'Δ':>8}")
    print("─" * 52)
    for row in table_data:
        print(f"{row[0]:<8}  {row[1]:>5}  {row[2]:>10}  {row[3]:>12}  {row[4]:>8}")


if __name__ == "__main__":
    main()
