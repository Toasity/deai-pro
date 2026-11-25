"""Simple sequential reference runner; scheduling optimizations are the exercise.

Usage (from the project root):
    python scripts/run_trajectory.py <trajectory>, e.g. spaceship_titanic_students

<trajectory> is a folder name in trajectories/ or a path to a trajectory folder.
"""

import json
from pathlib import Path
import sys
import io
import os
from stratum import StratumClient
from time import perf_counter

ROOT = Path(__file__).resolve().parent.parent


def main():
    if len(sys.argv) != 2:
        sys.exit(f"usage: python {Path(__file__).name} <trajectory>")
    candidate = ROOT / "trajectories" / sys.argv[1]
    folder = (candidate if (candidate / "trajectory.json").is_file() else Path(sys.argv[1])).resolve()
    if not (folder / "trajectory.json").is_file():
        sys.exit(f"no trajectory.json for {sys.argv[1]!r} (looked in {candidate} and {folder})")
    manifest = json.loads((folder / "trajectory.json").read_text())
    maximize = manifest["evaluation"]["maximize"]
    results = []
    server_dir = os.environ.get(
        "STRATUM_SERVER_DIR",
        "/tmp/deai-pro-stratum-import-test",
    )

    with StratumClient(server_dir=server_dir) as client:
        for step in manifest["steps"]:
            print(f"Step {step['step']}: {step['name']}", flush=True)
            for candidate in step["pipelines"]:
                pipeline_id = Path(candidate["file"]).stem
                started = perf_counter()
                score = None
                # Pipelines read ./input/ relative to their competition folder.
                output = io.StringIO()

                returncode = client.submit(
                    Path(candidate["file"]),
                    cwd=folder,
                    stdout=output,
                    stderr=sys.stderr,
                )

                captured = output.getvalue()
                print(captured, end="", flush=True)

                if returncode != 0:
                    raise RuntimeError(
                        f"{pipeline_id} failed with exit code {returncode}"
                    )

                for line in captured.splitlines():
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
    (output_dir / "summary.json").write_text(json.dumps(results, indent=2) + "\n")


if __name__ == "__main__":
    main()
