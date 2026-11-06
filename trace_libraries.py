"""Record which library modules each pipeline line calls into.

Usage (from the project root):
    uv run python trace_libraries.py <trajectory>

Runs <trajectory>/run_trajectory.py with every pipeline executed under a call tracer and
writes libraries/<trajectory>/<pipeline>.json:

    {"pipeline": "...", "lines": {"<lineno>": {"<module>": <direct calls>, ...}, ...}}

A call counts for a line when the line's own frame enters a function from another module,
including implicit calls such as df["a"] (DataFrame.__getitem__) or X.iloc[rows].
Calls made inside libraries are not counted, so sklearn using pandas internally stays sklearn.
Join with the Scalene line records on lineno.
"""

from collections import Counter, defaultdict
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
TRACE_FLAG = "--pipeline"


def callee_module(c_function):
    """Best-effort module name of a C function, falling back to the type of the bound object."""
    module = getattr(c_function, "__module__", None)
    if module is None:
        module = type(getattr(c_function, "__self__", None)).__module__
    return module or "?"


def trace_pipeline(pipeline, outfile):
    """Run one pipeline as __main__ and count direct calls per (line, module)."""
    pipeline = str(Path(pipeline).resolve())
    calls = defaultdict(Counter)

    def hook(frame, event, arg):
        if event == "call":
            # frame is the callee; skip calls between the pipeline's own functions.
            caller = frame.f_back
            if (caller is None or caller.f_code.co_filename != pipeline
                    or frame.f_code.co_filename == pipeline):
                return
            module = frame.f_globals.get("__name__", "?")
        elif event == "c_call":
            # frame is the caller; arg is the C function.
            caller = frame
            if caller.f_code.co_filename != pipeline:
                return
            module = callee_module(arg)
        else:
            return
        calls[caller.f_lineno][module] += 1

    sys.argv = [pipeline]
    sys.path[0] = str(Path(pipeline).parent)
    sys.setprofile(hook)
    try:
        runpy.run_path(pipeline, run_name="__main__")
    finally:
        sys.setprofile(None)
        Path(outfile).write_text(json.dumps({
            "pipeline": pipeline,
            "lines": {str(lineno): dict(counter.most_common())
                      for lineno, counter in sorted(calls.items())},
        }, indent=2) + "\n")


def trace_trajectory(trajectory):
    trajectory_dir = (ROOT / trajectory).resolve()
    runner = ROOT / "run_trajectory.py"
    output_dir = ROOT / "libraries" / trajectory
    if not runner.is_file():
        sys.exit(f"{runner} not found")
    output_dir.mkdir(parents=True, exist_ok=True)

    original_popen = subprocess.Popen

    class TracingPopen(original_popen):
        """Rewrites `python pipeline_x_y.py` launches into `python trace_libraries.py --pipeline ...`."""

        def __init__(self, args, *popen_args, **popen_kwargs):
            if (
                isinstance(args, list)
                and len(args) == 2
                and args[0] == sys.executable
                and Path(args[1]).name.startswith("pipeline_")
            ):
                outfile = output_dir / f"{Path(args[1]).stem}.json"
                args = [sys.executable, __file__, TRACE_FLAG, args[1], str(outfile)]
            super().__init__(args, *popen_args, **popen_kwargs)

    # Pipelines read input/ and the runner writes results/ relative to the working directory.
    os.chdir(trajectory_dir)
    sys.argv = [str(runner), str(trajectory_dir)]
    subprocess.Popen = TracingPopen
    runpy.run_path(str(runner), run_name="__main__")


def main():
    if len(sys.argv) == 4 and sys.argv[1] == TRACE_FLAG:
        trace_pipeline(sys.argv[2], sys.argv[3])
    elif len(sys.argv) == 2:
        trace_trajectory(sys.argv[1])
    else:
        sys.exit(f"usage: {sys.argv[0]} <trajectory>")


if __name__ == "__main__":
    main()
