"""Same trajectory as run_trajectory.py just withoit subprocesses

Usage: python run_trajectory_optimized.py <competition folder>, e.g. spaceship_titanic_students
"""

import json
from pathlib import Path
import sys
from time import perf_counter

import io
import os
from contextlib import redirect_stdout

BASELINE_DIR = Path(__file__).resolve().parent / "baselines"


def run_in_session(folder, name):
    """Run one pipeline in this process and return its output lines."""
    path = Path(folder) / name
    namespace = {"__name__": "__main__", "__file__": str(path)}
    # Idea: maybe we can later keep some stuff in global namespace to re-use but only very select things?
    output = io.StringIO()
    with redirect_stdout(output): # needed so we can read line by line, alternatively we have code_optimizer make it so that `score` is a global var or return to read out
        exec(compile(path.read_text(), str(path), "exec"), namespace, namespace)
    return output.getvalue().splitlines(keepends=True)


def main():
    if len(sys.argv) != 2:
        sys.exit(f"usage: python {Path(__file__).name} <competition folder>")
    folder = Path(sys.argv[1]).resolve()
    # Pipelines read ./input/ relative to their competition folder.
    os.chdir(folder) # move to trajectory folder
    manifest = json.loads((folder / "trajectory.json").read_text())
    maximize = manifest["evaluation"]["maximize"]
    results = []
    for step in manifest["steps"]:
        print(f"Step {step['step']}: {step['name']}", flush=True)
        for candidate in step["pipelines"]:
            pipeline_id = Path(candidate["file"]).stem
            started = perf_counter()
            score = None
            for line in run_in_session(folder, candidate["file"]):
                print(line, end="", flush=True)
                if line.startswith("Final Validation Score: "):
                    score = float(line.split(":", 1)[1])
            if score is None:
                raise RuntimeError(f"{pipeline_id} did not report a final validation score")
            results.append({"pipeline_id": pipeline_id,
                            "score": score,
                            "seconds": perf_counter() - started})
    # Stable display order for ties; equal scores still share rank.
    print("-"*60)
    print(f"Ranking by {manifest['evaluation']['metric']} "
          f"({'higher' if maximize else 'lower'} is better)")
    results.sort(key=lambda result: -result["score"] if maximize else result["score"])
    previous_score, rank = None, 0
    for position, result in enumerate(results, start=1):
        if result["score"] != previous_score:
            rank = position
        result["rank"] = rank
        previous_score = result["score"]
        print(f"{rank:2d}  {result['pipeline_id']}  {result['score']:.6f}")
    output_dir = folder / "results"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary_optimized.json").write_text(json.dumps(results, indent=2) + "\n")
    compare(folder, results)


def compare(folder, results):
    """Compare score and time against baselines/<trajectory>/summary.json."""
    baseline_path = BASELINE_DIR / folder.name / "summary.json"
    if not baseline_path.is_file():
        print(f"No baseline at {baseline_path}; skipping comparison")
        return
    baseline = {row["pipeline_id"]: row for row in json.loads(baseline_path.read_text())}
    current = {row["pipeline_id"]: row for row in results}
    if baseline.keys() != current.keys():
        print(f"Pipeline sets differ: {sorted(baseline.keys() ^ current.keys())}")
        return
    drift = max(abs(baseline[key]["score"] - current[key]["score"]) for key in baseline)
    baseline_seconds = sum(row["seconds"] for row in baseline.values())
    current_seconds = sum(row["seconds"] for row in current.values())
    print("-"*60)
    print(f"Baseline: {baseline_path}")
    print(f"Max |score diff|: {drift}")
    print(f"Total seconds: {current_seconds:.1f} vs baseline {baseline_seconds:.1f}"
          + (f" ({baseline_seconds / current_seconds:.2f}x)" if current_seconds else ""))


if __name__ == "__main__":
    main()
