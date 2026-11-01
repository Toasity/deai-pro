# Profiling analysis

Where does each pipeline actually spend its time? This splits every pipeline's runtime into
**setup**, **data handling** and **models**, using Scalene for the timings and a call tracer
to work out which library each line is calling.

Nothing inside the trajectory folder (e.g. `spaceship_titanic_students/`) is modified. All scripts
run from the project root and take the trajectory folder name as their first argument.

## Before you start

- Run `uv sync`.
- Put the Kaggle CSVs in `<trajectory>/input/` (see `README.md`).

## Run it

```bash
uv run python profile_trajectory.py spaceship_titanic_students   # 1. Scalene profile per pipeline
uv run python trace_libraries.py spaceship_titanic_students      # 2. which library each line calls
uv run python report_categories.py spaceship_titanic_students    # 3. CSV + plot (add --show for a window)
```

Steps 1 and 2 each replay the whole trajectory through the unchanged `run_trajectory.py`, about a
minute each for Spaceship Titanic. Step 3 only reads JSON and finishes in seconds. Any extra
arguments to step 1 go straight to `scalene run`, e.g. `--cpu-only`.

## What you get

```
profiles/<trajectory>/pipeline_x_y.json    raw Scalene profile
libraries/<trajectory>/pipeline_x_y.json   {lineno: {module: number of calls}}
results/<trajectory>/categories.csv        one row per pipeline x category, all metrics
results/<trajectory>/categories.png        seconds and share per category, per pipeline
```

All three folders are gitignored.

## How it works

**Step 1** runs every pipeline under `scalene run`. Scalene records time and memory per line of the
pipeline file. Time spent inside pandas/sklearn is charged to the line in your script that called
it, so `preprocessor.transform(X)` carries all of sklearn's work.

**Step 2** runs every pipeline again under `sys.setprofile` and notes which module each line
calls into *directly*. That catches pandas use that doesn't look like pandas: `df["a"]` calls
`DataFrame.__getitem__`, and `X.iloc[rows]` goes through `pandas.core.indexing`. What a library
does internally isn't counted, so sklearn using pandas internally still counts as sklearn.

**Step 3** joins the two on line number and sorts each line into a category:

| Category | A line goes here if it calls... |
|---|---|
| models | sklearn estimators, `.fit`, CV splitting, metrics, lightgbm, xgboost, catboost |
| data handling | pandas, numpy, sklearn preprocessing (`ColumnTransformer`, imputers, encoders) |
| setup | imports (`importlib`), `pathlib` |
| other | not a line of the pipeline: code Scalene finds in other files, e.g. while numpy is imported |

The categories are checked top to bottom, so `classifier.fit(X.iloc[rows])` counts as models.
Lines without any library call count as data handling, except `import` lines, which count as
setup. To change the mapping, edit `CATEGORY_PREFIXES` in `report_categories.py`.

## Metrics in the CSV

Scalene only stores CPU time as percentages of the run. The report converts them to seconds with
`percent / 100 * elapsed_time_sec`.

- `total_s`, `share_of_runtime`: time in the category, in seconds and as a share of the run.
- `python_s` / `native_s` / `system_s`: time running Python code, time inside C libraries, and
  time waiting (I/O, disk). A lot of Python time points to things like `apply` with a lambda.
- `core_utilization`: share of the machine's cores in use (0–1). Low during model training means
  it runs on one core.
- `malloc_mb`, `n_mallocs`: how much memory was allocated over the whole run (it's freed again, so
  this is not memory in use at once).
- `peak_mb`: the biggest peak of any single line. For the whole process's peak, use
  `max_footprint_mb`.
- `copy_mb`: data copied between Python and native code, e.g. pandas → numpy.

## Things to keep in mind

- **Short pipelines are noisy.** Scalene samples every 10 ms, so a 2 s run has about 200
  samples. Re-running changes the numbers by several percent. Average several runs before
  comparing close results.
- **Imports are a big fixed cost.** Every pipeline runs in its own process and pays about 1–2 s of
  setup before doing any work.
- **Import time lands on the first import of a library.** `from sklearn.compose import ...` pays
  for loading sklearn; the sklearn imports after it look free.
- **The call counts from step 2 aren't time.** They only decide the category; all time comes
  from Scalene.
- **Some numpy calls are missing from step 2.** numpy ufuncs like `np.log1p` aren't recorded, so
  a line like `np.log1p(df[col])` only shows pandas.
- **Re-run steps 1 and 2 together.** Both depend on the pipeline source. If a pipeline changes,
  the line numbers no longer match.
