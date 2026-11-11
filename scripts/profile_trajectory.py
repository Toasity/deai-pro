"""Run run_trajectory.py <trajectory> with every pipeline profiled by Scalene.

Usage (from the project root):
    uv run python scripts/profile_trajectory.py <trajectory> [extra `scalene run` options, e.g. --cpu-only]

Writes profiling/profiles/<trajectory>/<pipeline>.json.
"""

from pathlib import Path
import runpy
import subprocess
import sys

from paths import PROFILES_DIR, trajectory_dir

if len(sys.argv) < 2:
    sys.exit(f"usage: {sys.argv[0]} <trajectory> [scalene run options]")

TRAJECTORY_DIR = trajectory_dir(sys.argv[1])
RUNNER = Path(__file__).resolve().parent / "run_trajectory.py"
PROFILE_DIR = PROFILES_DIR / TRAJECTORY_DIR.name
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
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    # The runner launches each pipeline with cwd=<trajectory>, so input/ resolves there.
    sys.argv = [str(RUNNER), str(TRAJECTORY_DIR)]
    subprocess.Popen = ScalenePopen
    runpy.run_path(str(RUNNER), run_name="__main__")


if __name__ == "__main__":
    main()
