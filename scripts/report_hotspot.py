"""Rank the most expensive pipeline operations across a trajectory's Scalene profiles.

Usage (from the project root, after profile_trajectory.py and trace_libraries.py):
    uv run python scripts/report_hotspot.py <trajectory> [<trajectory> ...] [--top N] [--show]

Reads profiling/profiles/<trajectory>/<pipeline>.json and profiling/libraries/<trajectory>/<pipeline>.json,
attributes every profiled source line to its statement, and ranks statements by cumulative
estimated seconds. Writes results/<trajectory>/hotspots.csv, results/<trajectory>/hotspots_details.csv
and results/hotspots.png.

The functions are importable so explore.ipynb can reuse them without redefining the analysis.
"""

import argparse
import json
from dataclasses import dataclass
from numbers import Integral
from pathlib import Path
import re
import sys
import textwrap

import matplotlib
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
TRAJECTORIES_DIR = ROOT / "trajectories"
HOTSPOT_DIR = ROOT / "results"

DEFAULT_TRAJECTORIES = ["spaceship_titanic_students", "house_price_students"]
DEFAULT_TOP_N = 10
COLUMNS = [
    ("python_s", "Python", "#4c78a8"),
    ("native_s", "Native", "#f58518"),
    ("system_s", "System / wait estimate", "#a5a5a5"),
]


def decode_source(text):
    """Undo the \\uXXXX escaping Scalene applies to recorded source lines."""
    return re.sub(r"\\u([0-9a-fA-F]{4})", lambda match: chr(int(match[1], 16)), text)


def operation_label(source):
    """Shorten a display label at the first opening parenthesis.

    Keep assignment targets and subscripts; omit arguments and chained calls.
    Statements without an opening parenthesis are left intact.
    """
    text = source.strip()
    return text.split("(", 1)[0] + "(...)" if "(" in text else text


@dataclass
class TrajectoryAnalysis:
    trajectory: str
    line_details: pd.DataFrame
    runs: pd.DataFrame
    operation_summary: pd.DataFrame
    top10: pd.DataFrame
    profile_s: float


def _validate_top_n(top_n):
    if isinstance(top_n, bool) or not isinstance(top_n, Integral) or top_n <= 0:
        raise ValueError("top_n must be a positive integer")


def analyze_trajectory(trajectory, top_n=DEFAULT_TOP_N):
    """Aggregate Scalene line timings and library traces for one trajectory.

    Reads profiling/profiles/<trajectory>/ and profiling/libraries/<trajectory>/,
    attributes every profiled source line to its statement, and ranks statements
    by cumulative estimated seconds across the trajectory's pipelines.
    """
    _validate_top_n(top_n)

    profile_dir = ROOT / "profiling/profiles" / trajectory
    library_dir = ROOT / "profiling/libraries" / trajectory
    profiles = sorted(profile_dir.glob("pipeline_*.json"))
    if not profiles:
        raise FileNotFoundError(f"no profiles in {profile_dir}; run profile_trajectory.py first")
    missing = [p.stem for p in profiles if not (library_dir / p.name).is_file()]
    if missing:
        raise FileNotFoundError(f"no library traces for {missing}; run trace_libraries.py first")

    records, run_records = [], []
    for profile_path in profiles:
        profile = json.loads(profile_path.read_text())
        libraries = json.loads((library_dir / profile_path.name).read_text())["lines"]
        pipeline = profile_path.stem
        source_path = TRAJECTORIES_DIR / trajectory / f"{pipeline}.py"
        source_lines = source_path.read_text().splitlines()
        elapsed = profile["elapsed_time_sec"]
        run_records.append({"pipeline": pipeline, "elapsed_s": elapsed})
        for row in profile["files"][profile["program"]]["lines"]:
            lineno = row["lineno"]
            source = decode_source(row["line"]).rstrip("\n")
            assert source == source_lines[lineno - 1], f"Source mismatch: {pipeline}:{lineno}"
            python_s = row["n_cpu_percent_python"] * elapsed / 100
            native_s = row["n_cpu_percent_c"] * elapsed / 100
            system_s = row["n_sys_percent"] * elapsed / 100
            records.append({
                "pipeline": pipeline, "source_file": str(source_path), "lineno": lineno,
                "location": f"{source_path.relative_to(ROOT)}:{lineno}",
                "operation": source.strip(), "source": source,
                "modules": ", ".join(sorted(libraries.get(str(lineno), {}))),
                "python_s": python_s, "native_s": native_s, "system_s": system_s,
                "total_s": python_s + native_s + system_s,
            })

    line_details = pd.DataFrame(records)
    runs = pd.DataFrame(run_records)
    profile_s = runs["elapsed_s"].sum()
    operation_summary = (
        line_details.groupby("operation", as_index=False)
        .agg(python_s=("python_s", "sum"), native_s=("native_s", "sum"),
             system_s=("system_s", "sum"), total_s=("total_s", "sum"),
             n_pipelines=("pipeline", "nunique"), n_source_locations=("lineno", "size"),
             n_timed_locations=("total_s", lambda values: int((values > 0).sum())))
        .query("total_s > 0")
        .sort_values(["total_s", "operation"], ascending=[False, True])
        .reset_index(drop=True)
    )
    operation_summary.insert(0, "rank", operation_summary.index + 1)
    operation_summary["share_of_runs_pct"] = operation_summary["total_s"] / profile_s * 100
    operation_summary["cumulative_share_pct"] = operation_summary["share_of_runs_pct"].cumsum()
    return TrajectoryAnalysis(trajectory, line_details, runs, operation_summary,
                              operation_summary.head(top_n).copy(), profile_s)


def analyze_all(trajectories=None, top_n=DEFAULT_TOP_N):
    """Analyze several trajectories, keyed by name."""
    _validate_top_n(top_n)
    names = DEFAULT_TRAJECTORIES if trajectories is None else trajectories
    return {name: analyze_trajectory(name, top_n=top_n) for name in names}


def report_trajectory(analysis):
    """Print the runtime attribution summary for one analysis."""
    top = analysis.top10
    prefix = f"[{analysis.trajectory}]"
    source_s = analysis.line_details.total_s.sum()
    print(f"{prefix} Profiles: {len(analysis.runs)}; "
          f"summed profiled runtime: {analysis.profile_s:.2f} s")
    print(f"{prefix} Pipeline source attribution: {source_s:.2f} s")
    print(f"{prefix} Other files + unattributed residual: "
          f"{analysis.profile_s - source_s:.2f} s")
    print(f"{prefix} Top {len(top)}: {top.total_s.sum():.2f} s "
          f"({top.share_of_runs_pct.sum():.1f}% of summed runtime)")


def top10_details(analysis):
    """Every pipeline/source location behind the top-N operations, with a reconciliation check."""
    details = (
        analysis.line_details
        .merge(analysis.top10[["operation", "rank"]], on="operation", how="inner", validate="many_to_one")
        .sort_values(["total_s", "pipeline", "lineno"], ascending=[False, True, True])
        [["rank", "pipeline", "location", "source_file", "lineno", "operation", "source", "modules",
          "python_s", "native_s", "system_s", "total_s"]]
        .reset_index(drop=True)
    )
    reconciled = details.groupby("operation")["total_s"].sum()
    assert (reconciled - analysis.top10.set_index("operation")["total_s"]).abs().max() < 1e-9
    assert (analysis.line_details.total_s
            - analysis.line_details[["python_s", "native_s", "system_s"]].sum(axis=1)).abs().max() < 1e-9
    return details


def plot_hotspots(analyses, outfile=None):
    """Draw one top-N hotspot panel per trajectory, side by side."""
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, len(analyses), figsize=(14 * len(analyses), 8),
                             layout="constrained", squeeze=False)
    for ax, analysis in zip(axes[0], analyses.values()):
        top = analysis.top10
        labels = [f"{row.rank}. " + textwrap.fill(operation_label(row.operation), 60)
                  for row in top.itertuples()]
        left = [0.0] * len(top)
        for column, label, color in COLUMNS:
            ax.barh(range(len(top)), top[column], left=left, label=label, color=color)
            left = [a + b for a, b in zip(left, top[column])]
        max_s = top.total_s.max()
        offset = max_s * 0.01
        for i, row in enumerate(top.itertuples()):
            ax.text(row.total_s + offset, i, f"{row.total_s:.2f}s / {row.share_of_runs_pct:.1f}%",
                    va="center", fontsize=14)
        ax.set_yticks(range(len(labels)), labels, fontsize=14)
        ax.invert_yaxis()
        ax.set_xlim(0, max_s * 1.25)
        ax.set_xlabel(f"Estimated seconds summed across {len(analysis.runs)} profiled pipelines")
        ax.set_title(f"{analysis.trajectory}: top {len(top)} hotspots", size=18)
        ax.legend(loc="lower right")
        ax.grid(axis="x", alpha=0.2)
        ax.set_axisbelow(True)
    if outfile is not None:
        fig.savefig(outfile, dpi=150)
    return fig


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0], allow_abbrev=False)
    parser.add_argument("trajectories", nargs="*", help="trajectory names or paths")
    parser.add_argument("--top", type=int, default=DEFAULT_TOP_N, metavar="N",
                        help="number of hotspots (positive integer, default: %(default)s)")
    parser.add_argument("--show", action="store_true", help="also display the saved plot")
    args = parser.parse_intermixed_args()
    try:
        _validate_top_n(args.top)
    except ValueError:
        parser.error("--top expects a positive integer")

    trajectories = [Path(name).name for name in args.trajectories] or DEFAULT_TRAJECTORIES
    if not args.show:
        matplotlib.use("Agg")
    try:
        analyses = analyze_all(trajectories, top_n=args.top)
    except FileNotFoundError as exc:
        sys.exit(str(exc))
    for analysis in analyses.values():
        report_trajectory(analysis)
        print(analysis.top10[["rank", "operation", "total_s", "share_of_runs_pct"]].round(3).to_string(index=False))
        output_dir = HOTSPOT_DIR / analysis.trajectory
        output_dir.mkdir(parents=True, exist_ok=True)
        analysis.operation_summary.to_csv(output_dir / "hotspots.csv", index=False)
        top10_details(analysis).to_csv(output_dir / "hotspots_details.csv", index=False)
        print(f"Wrote {output_dir / 'hotspots.csv'} and {output_dir / 'hotspots_details.csv'}")

    plot_hotspots(analyses, HOTSPOT_DIR / "hotspots.png")
    print(f"Wrote {HOTSPOT_DIR / 'hotspots.png'}")
    if args.show:
        import matplotlib.pyplot as plt
        plt.show()


if __name__ == "__main__":
    main()
