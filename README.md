# Spaceship Titanic

Download the data from the [Kaggle competition data page](https://www.kaggle.com/competitions/spaceship-titanic/data): sign in, accept the competition rules, and click **Download All**.

From the repository root, unzip the downloaded archive into the competition's `input/` folder:

```bash
mkdir -p spaceship_titanic_students/input
unzip ~/Downloads/spaceship-titanic.zip -d spaceship_titanic_students/input
```

Adjust the archive path if needed. The CSV files should sit directly inside `spaceship_titanic_students/input/` (`train.csv`, `test.csv`, and `sample_submission.csv`). Run pipelines from `spaceship_titanic_students/` so they can find `input/`.

To analyze existing profiling data without replaying pipelines, open
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

To record new profiling evidence, run one indexed repetition at a time:

```bash
uv run python profile_trajectory.py spaceship_titanic_students --run-index 11
```

This writes `profiles/spaceship_titanic_students/run_11/`, so repeated runs of the
same trajectory accumulate instead of overwriting each other.
