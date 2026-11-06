"""Run run_trajectory.py on <trajectory> with every pipeline profiled by Scalene.

Usage (from the project root):
    uv run python profile_trajectory.py <trajectory> --run-index <n> [extra `scalene run` options]

Writes profiles/<trajectory>/run_<nn>/<pipeline>.json, so repeated runs of the same
trajectory accumulate instead of overwriting each other.
"""

import os
from pathlib import Path
import runpy
import subprocess
import sys

RUN_INDEX_FLAG = "--run-index"


def _split_run_index(argv):
    """Pull `--run-index <n>` out of argv, leaving the remaining `scalene run` options."""
    index, rest, position = None, [], 0
    while position < len(argv):
        argument = argv[position]
        if argument == RUN_INDEX_FLAG:
            if position + 1 >= len(argv):
                sys.exit(f"{RUN_INDEX_FLAG} requires a value")
            index = int(argv[position + 1])
            position += 2
            continue
        if argument.startswith(f"{RUN_INDEX_FLAG}="):
            index = int(argument.split("=", 1)[1])
            position += 1
            continue
        rest.append(argument)
        position += 1
    return index, rest


if len(sys.argv) < 2:
    sys.exit(f"usage: {sys.argv[0]} <trajectory> {RUN_INDEX_FLAG} <n> [scalene run options]")

ROOT = Path(__file__).resolve().parent
TRAJECTORY = sys.argv[1]
RUN_INDEX, SCALENE_OPTIONS = _split_run_index(sys.argv[2:])
if RUN_INDEX is None or RUN_INDEX < 1:
    sys.exit(f"{RUN_INDEX_FLAG} <n> is required and must be >= 1")
TRAJECTORY_DIR = (ROOT / TRAJECTORY).resolve()
RUNNER = ROOT / "run_trajectory.py"
PROFILE_DIR = ROOT / "profiles" / TRAJECTORY / f"run_{RUN_INDEX:02d}"

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
    if not TRAJECTORY_DIR.is_dir():
        sys.exit(f"{TRAJECTORY_DIR} not found")
    if not RUNNER.is_file():
        sys.exit(f"{RUNNER} not found")
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    # The runner takes the competition folder as its only argument and runs each
    # pipeline with that folder as the working directory.
    os.chdir(TRAJECTORY_DIR)
    sys.argv = [str(RUNNER), str(TRAJECTORY_DIR)]
    subprocess.Popen = ScalenePopen
    runpy.run_path(str(RUNNER), run_name="__main__")


if __name__ == "__main__":
    main()
