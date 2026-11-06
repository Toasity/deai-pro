# DEAI pro

Each `*_students/` folder holds one fixed trajectory of ML pipelines. `pipeline_X_y.py` is
variant `y` of step `X`. The variants of a step are independent of each other, and
`trajectory.json` lists the steps and the pipelines in each one.

Run a whole trajectory from the repository root:

```bash
python run_trajectory.py spaceship_titanic_students
python run_trajectory.py house_price_students
```

The runner runs each pipeline inside its competition folder, so the pipelines can find `input/`.
It writes the ranking to `<folder>/results/summary.json`. To run a single pipeline, run it
from its folder (e.g. `cd house_price_students && python pipeline_1_1.py`).

## Spaceship Titanic

Download the data from the [Kaggle competition data page](https://www.kaggle.com/competitions/spaceship-titanic/data): sign in, accept the competition rules, and click **Download All**.

From the repository root, unzip the downloaded archive into the competition's `input/` folder:

```bash
mkdir -p spaceship_titanic_students/input
unzip ~/Downloads/spaceship-titanic.zip -d spaceship_titanic_students/input
```

Adjust the archive path if needed. The CSV files should sit directly inside `spaceship_titanic_students/input/` (`train.csv`, `test.csv`, and `sample_submission.csv`).

## UK house prices

The pipelines read HM Land Registry Price Paid Data as a single file, `price_paid_records.csv`
(about 2.4 GB, 22.5M sales from 1995 to mid-2017), from the
[UK Housing Prices Paid](https://www.kaggle.com/datasets/hm-land-registry/uk-housing-prices-paid)
dataset on Kaggle. From the repository root, download it (a 731 MB zip, no Kaggle login needed)
and unzip it into the competition's `input/` folder:

```bash
curl -L -o uk-housing-prices-paid.zip \
  https://www.kaggle.com/api/v1/datasets/download/hm-land-registry/uk-housing-prices-paid
mkdir -p house_price_students/input
unzip uk-housing-prices-paid.zip -d house_price_students/input
rm uk-housing-prices-paid.zip
```

The file should then sit at `house_price_students/input/price_paid_records.csv`. Use this
Kaggle file, not the gov.uk `pp-complete.csv`: that one has no header row and different columns.

Each pipeline reads the whole file, takes a seeded random sample of 2,000,000 rows (the
same rows every time), keeps the sales up to the end of 2016, and reports its RMSE on
log10(price) for the 2016 sales. All pipelines run on CPU only and need about 7 GB of RAM.

## Pipeline runtime distribution (Module 1)

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
