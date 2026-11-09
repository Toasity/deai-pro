"""Project layout shared by all scripts.

    trajectories/<trajectory>/      pipelines, trajectory.json, input/,
                                    results/ (run_trajectory.py), results_optimized/ (run_trajectory_optimized.py)
    profiling/profiles/<trajectory>/    raw Scalene profiles
    profiling/libraries/<trajectory>/   library call traces
    profiling/results/<trajectory>/     category report (CSV + plot)
"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
TRAJECTORIES_DIR = ROOT / "trajectories"
PROFILING_DIR = ROOT / "profiling"
PROFILES_DIR = PROFILING_DIR / "profiles"
LIBRARIES_DIR = PROFILING_DIR / "libraries"
REPORTS_DIR = PROFILING_DIR / "results"

# Scripts run as `python scripts/<name>.py`, so make top-level project packages (e.g. optimizer) importable.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def trajectory_dir(name_or_path):
    """Resolve a trajectory name (e.g. spaceship_titanic_students) or a path to its folder.

    A bare name is looked up in trajectories/; anything else is taken as a path.
    Exits if the folder has no trajectory.json.
    """
    candidate = TRAJECTORIES_DIR / name_or_path
    folder = (candidate if (candidate / "trajectory.json").is_file() else Path(name_or_path)).resolve()
    if not (folder / "trajectory.json").is_file():
        sys.exit(f"no trajectory.json for {name_or_path!r} "
                 f"(looked in {candidate} and {folder})")
    return folder
