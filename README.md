# Spaceship Titanic

Download the data from the [Kaggle competition data page](https://www.kaggle.com/competitions/spaceship-titanic/data): sign in, accept the competition rules, and click **Download All**.

From the repository root, unzip the downloaded archive into the competition's `input/` folder:

```bash
mkdir -p spaceship_titanic_students/input
unzip ~/Downloads/spaceship-titanic.zip -d spaceship_titanic_students/input
```

Adjust the archive path if needed. The CSV files should sit directly inside `spaceship_titanic_students/input/` (`train.csv`, `test.csv`, and `sample_submission.csv`). Run pipelines from `spaceship_titanic_students/` so they can find `input/`.

To analyze existing profiling data without replaying pipelines:

Open `analyze_bottlenecks.ipynb` with the project's `.venv` Python kernel and run
all cells from the repository root. Its 11 modules explain the analysis goals,
data and methods before the code, then display computed results and English
interpretations written by the assistant after reviewing the tables, code and images.
Executed tables and 12 charts are included. Input/code changes trigger a stale-review
notice; rerunning cells does not automatically regenerate the reviewed prose.
The notebook exports 21 tables and its figures to
`results/spaceship_titanic_students/bottleneck_analysis/notebook/`, separate from
the command-line report. No LLM API configuration is required.
The notebook contains the analysis helpers and does not require importing the
script or loading previously generated analysis tables.

The command-line version remains available:

```bash
uv run python analyze_bottlenecks.py spaceship_titanic_students
```

This requires the existing profiles, traces, category CSV and execution summary. It writes
`docs/performance_analysis.md` and independent tables/plots under
`results/spaceship_titanic_students/bottleneck_analysis/`. Predictions are read only as
artifact clues. See `docs/analysis_plan.md` for scope and interpretation limits.

Run analysis checks with `.venv/bin/python -m unittest discover -s tests -v`.

For descriptive statistics of the recorded profiling evidence, open
`descriptive_statistics.ipynb` with the project's `.venv` Python kernel and run all
cells from the repository root. Module 1 covers the pipeline runtime distribution:
per-candidate elapsed-time statistics, run-to-run variability, within-run cost
concentration and step-level cost. It reads only `elapsed_time_sec` and
`start_time_absolute` from the existing profile JSON files; no pipeline or profiler
is replayed.

The profiles are not stored in this workspace, so the configuration cell points at
an explicit absolute path (`/Users/tue/Documents/10_Projects/deai-pro/profiles`) and
prints the resolved directories. Set `PROFILES_ROOT_OVERRIDE` in that cell to analyse
a different copy deliberately; the notebook stops rather than searching for another
source on its own.

Module 1 exports 10 tables and five figures (PNG and SVG) to
`results/spaceship_titanic_students/descriptive_statistics/runtime_distribution/`,
together with `input_fingerprints.csv` covering the trajectory manifest and every
profile file. The English interpretation was reviewed against the executed results;
a fingerprint stored in the notebook metadata warns when the evidence or the code
changes and the prose needs re-review. No LLM API configuration is required.
