"""Render the README results chart from the two ablation JSONs.

GPU-free, depends only on json + matplotlib (anaconda python3, not the uv venv).
Shows the headline: vision's lift over the DOM-only baseline, by category, for
gpt-4o-mini vs gpt-4o — making "icon-heavy 0/4 -> 3/4" and "+25% overall" legible.

Usage:
  python3 scripts/make_results_chart.py
"""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "output" / "benchmark_results"


def load(fname):
    d = json.load(open(RES / fname))
    by_cat = d["summary"]["by_category"]
    by_cond = d["summary"]["by_condition"]
    cats = ["icon-heavy", "mixed", "dom-rich"]
    base = [by_cat[c]["A_baseline"]["success_rate"] * 100 for c in cats]
    full = [by_cat[c]["C_full_always"]["success_rate"] * 100 for c in cats]
    # overall from by_condition
    base.append(by_cond["A_baseline"]["success_rate"] * 100)
    full.append(by_cond["C_full_always"]["success_rate"] * 100)
    return base, full


def main():
    labels = ["icon-heavy", "mixed", "dom-rich", "Overall"]
    panels = [
        ("gpt-4o-mini  (cost default)", "ablation_results.json"),
        ("gpt-4o  (best result)", "ablation_results_gpt-4o.json"),
    ]

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.6), sharey=True)
    x = range(len(labels))
    w = 0.38
    c_base, c_full = "#9ca3af", "#10b981"

    for ax, (title, fname) in zip(axes, panels):
        base, full = load(fname)
        b1 = ax.bar([i - w / 2 for i in x], base, w, label="DOM-only baseline", color=c_base)
        b2 = ax.bar([i + w / 2 for i in x], full, w, label="+ Full Vision", color=c_full)
        for bars in (b1, b2):
            for r in bars:
                ax.text(r.get_x() + r.get_width() / 2, r.get_height() + 1.5,
                        f"{r.get_height():.0f}", ha="center", va="bottom", fontsize=9)
        ax.set_title(title, fontsize=12, fontweight="bold")
        ax.set_xticks(list(x))
        ax.set_xticklabels(labels, fontsize=10)
        ax.set_ylim(0, 108)
        ax.spines[["top", "right"]].set_visible(False)

    axes[0].set_ylabel("Objective success rate (%)")
    axes[0].legend(loc="upper left", frameon=False, fontsize=9)
    fig.suptitle("Vision's value scales with VLM capability  —  objective verification, 16-task ablation",
                 fontsize=13, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.95])

    out = ROOT / "docs" / "assets" / "results.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=140)
    print(f"saved {out}")


if __name__ == "__main__":
    main()
