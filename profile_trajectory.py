"""Run <trajectory>/run_trajectory.py with every pipeline profiled by Scalene.

Usage (from the project root):
    uv run python profile_trajectory.py <trajectory> [extra `scalene run` options, e.g. --cpu-only]

Writes profiles/<trajectory>/<pipeline>.json.
"""

import os
from pathlib import Path
import runpy
import subprocess
import sys

if len(sys.argv) < 2:
    sys.exit(f"usage: {sys.argv[0]} <trajectory> [scalene run options]")

ROOT = Path(__file__).resolve().parent
TRAJECTORY = sys.argv[1]
TRAJECTORY_DIR = ROOT / TRAJECTORY
RUNNER = TRAJECTORY_DIR / "run_trajectory.py"
PROFILE_DIR = ROOT / "profiles" / TRAJECTORY
SCALENE_OPTIONS = sys.argv[2:]

_Popen = subprocess.Popen


class ScalenePopen(_Popen):
    """Rewrites `python pipeline_x_y.py` launches into `python -m scalene run ... pipeline_x_y.py`."""

    def __init__(self, args, *popen_args, **popen_kwargs):
        if (
            isinstance(args, list)
            and len(args) == 2
            and args[0] == sys.executable
            and Path(args[1]).name.startswith("pipeline_")
        ):
            outfile = PROFILE_DIR / f"{Path(args[1]).stem}.json"
            args = [
                sys.executable,
                "-m",
                "scalene",
                "run",
                "-o",
                str(outfile),
                *SCALENE_OPTIONS,
                args[1],
            ]
        super().__init__(args, *popen_args, **popen_kwargs)


def main():
    if not RUNNER.is_file():
        sys.exit(f"{RUNNER} not found")
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    # Pipelines read input/ and the runner writes results/ relative to the working directory.
    os.chdir(TRAJECTORY_DIR)
    sys.argv = [str(RUNNER)]
    subprocess.Popen = ScalenePopen
    runpy.run_path(str(RUNNER), run_name="__main__")


if __name__ == "__main__":
    main()
