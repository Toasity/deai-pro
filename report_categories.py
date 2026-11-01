"""Aggregate Scalene profiles into setup / data handling / models per pipeline.

Usage (from the project root, after profile_trajectory.py and trace_libraries.py):
    uv run python report_categories.py <trajectory> [--show]

Reads profiles/<trajectory>/<pipeline>.json and libraries/<trajectory>/<pipeline>.json and writes
results/<trajectory>/categories.csv and results/<trajectory>/categories.png.
"""

from collections import defaultdict
import json
from pathlib import Path
import sys

import matplotlib
import pandas as pd

ROOT = Path(__file__).resolve().parent

# Checked in order: a line that calls a model library is "models" even if it also touches pandas,
# e.g. classifier.fit(X.iloc[rows]). builtins carry no category.
CATEGORY_PREFIXES = {
    "models": (
        "sklearn.linear_model", "sklearn.ensemble",
        "sklearn.base",  # estimator .fit()
        "sklearn.model_selection",  # CV splitting
        "sklearn.utils._param_validation",  # wraps metrics such as accuracy_score
        "lightgbm", "xgboost", "catboost",
    ),
    "data handling": (
        "pandas", "numpy",
        "sklearn.compose", "sklearn.pipeline", "sklearn.impute", "sklearn.preprocessing",
        "sklearn.utils._set_output",  # wraps transformer fit_transform / transform
    ),
    "setup": ("importlib", "pathlib"),
}
# Time Scalene attributes to code outside the pipeline file, e.g. <exec@...> run during numpy's import.
OTHER = "other"
CATEGORIES = ["setup", "data handling", "models", OTHER]
COLORS = {"setup": "#2a78d6", "data handling": "#eb6834", "models": "#1baf7a", OTHER: "#b5b4ae"}
SURFACE, TEXT_PRIMARY, TEXT_SECONDARY, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"


def categorize_line(line, modules):
    for category, prefixes in CATEGORY_PREFIXES.items():
        if any(module.startswith(prefixes) for module in modules):
            return category
    # Untraced lines: imports of already-loaded modules, or plain Python inside helpers
    # such as split_cabin that pandas calls via apply.
    if line.lstrip().startswith(("import ", "from ")):
        return "setup"
    return "data handling"


def compute_total(category, lines, elapsed_time_sec):
    """Aggregate Scalene line records of one category into absolute totals.

    CPU percentages are shares of the sampled run time (~ elapsed_time_sec),
    so they are additive across lines and convert to seconds.
    """
    active = [
        l for l in lines
        if l["n_cpu_percent_python"] + l["n_cpu_percent_c"] + l["n_sys_percent"] > 0
        or l["n_malloc_mb"] > 0
    ]
    to_sec = elapsed_time_sec / 100
    python_s = sum(l["n_cpu_percent_python"] for l in active) * to_sec
    native_s = sum(l["n_cpu_percent_c"] for l in active) * to_sec
    system_s = sum(l["n_sys_percent"] for l in active) * to_sec
    total_s = python_s + native_s + system_s
    cpu_pct = sum(l["n_cpu_percent_python"] + l["n_cpu_percent_c"] for l in active)
    malloc_mb = sum(l["n_malloc_mb"] for l in active)
    return {
        "category": category,
        "n_relevant_lines": len(active),
        "total_s": total_s,
        "share_of_runtime": total_s / elapsed_time_sec if elapsed_time_sec else 0.0,
        "python_s": python_s,
        "native_s": native_s,
        "system_s": system_s,
        # Time-weighted: lines that ran longer count more.
        "core_utilization": (
            sum(l["n_core_utilization"] * (l["n_cpu_percent_python"] + l["n_cpu_percent_c"]) for l in active) / cpu_pct
            if cpu_pct else 0.0
        ),
        "malloc_mb": malloc_mb,
        "n_mallocs": sum(l["n_mallocs"] for l in active),
        # Allocation-weighted share of memory allocated by Python (vs. native) code.
        "python_alloc_fraction": (
            sum(l["n_python_fraction"] * l["n_malloc_mb"] for l in active) / malloc_mb
            if malloc_mb else 0.0
        ),
        # Peaks are not additive: the category's peak is the largest line peak.
        "peak_mb": max((l["n_peak_mb"] for l in active), default=0.0),
        "copy_mb": sum(l["n_copy_mb_s"] for l in active) * elapsed_time_sec,
    }


def pipeline_rows(profile_path, libraries_path):
    profile = json.loads(profile_path.read_text())
    libraries = {int(lineno): modules
                 for lineno, modules in json.loads(libraries_path.read_text())["lines"].items()}
    elapsed = profile["elapsed_time_sec"]
    lines_by_category = defaultdict(list)
    other_lines = []
    for filename, file_detail in profile["files"].items():
        if filename != profile["program"]:
            other_lines += file_detail["lines"]
            continue
        for l in file_detail["lines"]:
            lines_by_category[categorize_line(l["line"], libraries.get(l["lineno"], {}))].append(l)
    lines_by_category[OTHER] = other_lines
    rows = [compute_total(category, lines_by_category[category], elapsed) for category in CATEGORIES]
    for row in rows:
        row["pipeline"] = profile_path.stem
        row["elapsed_time_sec"] = elapsed
        row["max_footprint_mb"] = profile["max_footprint_mb"]
    return rows


def plot(totals, outfile):
    seconds = totals.pivot(index="pipeline", columns="category", values="total_s")[CATEGORIES]
    shares = seconds.div(seconds.sum(axis=1), axis=0) * 100

    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, sharey=True, figsize=(12, 0.32 * len(seconds) + 1.8),
                             facecolor=SURFACE, layout="constrained")
    for ax, data, xlabel in [(axes[0], seconds, "seconds"), (axes[1], shares, "share of runtime (%)")]:
        left = pd.Series(0.0, index=data.index)
        for category in CATEGORIES:
            ax.barh(data.index, data[category], left=left, height=0.72, label=category,
                    color=COLORS[category], edgecolor=SURFACE, linewidth=1.5)
            left += data[category]
        ax.set_facecolor(SURFACE)
        ax.set_xlabel(xlabel, color=TEXT_SECONDARY)
        ax.grid(axis="x", color=GRID, linewidth=0.8)
        ax.set_axisbelow(True)
        ax.tick_params(colors=TEXT_SECONDARY, length=0)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color(GRID)
    axes[0].margins(y=0.01)
    axes[0].invert_yaxis()
    axes[1].set_xlim(0, 100)
    axes[0].set_title("Time per category", loc="left", color=TEXT_PRIMARY)
    axes[1].set_title("Share of each pipeline's runtime", loc="left", color=TEXT_PRIMARY)
    fig.legend(*axes[0].get_legend_handles_labels(), loc="outside upper center", ncols=len(CATEGORIES),
               frameon=False, labelcolor=TEXT_PRIMARY)
    fig.savefig(outfile, dpi=150, facecolor=SURFACE)
    return fig


def main():
    args = [arg for arg in sys.argv[1:] if arg != "--show"]
    show = "--show" in sys.argv[1:]
    if len(args) != 1:
        sys.exit(f"usage: {sys.argv[0]} <trajectory> [--show]")
    trajectory = args[0]
    profile_dir = ROOT / "profiles" / trajectory
    libraries_dir = ROOT / "libraries" / trajectory
    output_dir = ROOT / "results" / trajectory

    profiles = sorted(profile_dir.glob("pipeline_*.json"))
    if not profiles:
        sys.exit(f"no profiles in {profile_dir}; run profile_trajectory.py first")
    missing = [p.stem for p in profiles if not (libraries_dir / p.name).is_file()]
    if missing:
        sys.exit(f"no library traces for {missing}; run trace_libraries.py first")

    if not show:
        matplotlib.use("Agg")
    totals = pd.DataFrame([row for p in profiles for row in pipeline_rows(p, libraries_dir / p.name)])
    totals = totals[["pipeline", *[c for c in totals.columns if c != "pipeline"]]]
    output_dir.mkdir(parents=True, exist_ok=True)
    totals.to_csv(output_dir / "categories.csv", index=False)
    plot(totals, output_dir / "categories.png")
    print(totals.pivot(index="pipeline", columns="category", values="total_s")[CATEGORIES].round(3))
    print(f"Wrote {output_dir / 'categories.csv'} and {output_dir / 'categories.png'}")
    if show:
        import matplotlib.pyplot as plt
        plt.show()


if __name__ == "__main__":
    main()
