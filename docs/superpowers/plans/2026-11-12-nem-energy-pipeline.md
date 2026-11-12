# NEM Energy Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A free, self-running pipeline that collects AEMO NEM data hourly, models it with dbt, forecasts next-day demand per region against AEMO's own forecast, and serves a public two-page Streamlit dashboard.

**Architecture:** Python loaders append untouched source files into `raw.*` tables of one DuckDB file; dbt builds `staging` → `marts`; a forecast package writes `forecasts.*`; the file lives as a GitHub Release asset that hourly/daily GitHub Actions download, update and re-upload, and that the dashboard downloads read-only. A one-off PySpark job turns the 13-month generator archive into a fuel-mix Parquet.

**Tech Stack:** Python 3.12, uv, DuckDB, dbt-duckdb, pandas, PySpark (local), LightGBM, `holidays`, Streamlit + Plotly, pytest, ruff, GitHub Actions + Releases, `gh` CLI.

**Spec:** `docs/superpowers/specs/2026-11-12-nem-energy-pipeline-design.md`

## Global Constraints

- **Zero payment:** only GitHub (public repo, GitHub-hosted runners, Releases), Streamlit Community Cloud, AEMO NEMWeb, Open-Meteo free API (no key). No payment method on any account; no MotherDuck/AWS/GCP/Azure/Databricks/Snowflake/paid APIs/custom domains/Claude API. If anything asks for a card, stop and ask the user.
- **Regions:** `NSW1, QLD1, VIC1, SA1, TAS1`. Cities: Sydney, Brisbane, Melbourne, Adelaide, Hobart. Holiday subdivisions: NSW, QLD, VIC, SA, TAS.
- **Time:** every timestamp is NEM time (AEST, UTC+10, no daylight saving), stored as naive `TIMESTAMP`. Open-Meteo is always requested with `timezone=Australia/Brisbane` (UTC+10, no DST).
- **Raw is append-only:** raw columns stored as VARCHAR exactly as parsed, plus `source_file VARCHAR` and `loaded_at TIMESTAMP`. Casting and deduplication happen in dbt staging.
- **Politeness:** sequential downloads, one request per file, 3 attempts with exponential backoff (2 s base), User-Agent `nem-energy-pipeline/0.1 (student portfolio project)` — no personal details.
- **Refresh:** collect hourly; forecast daily at 12:00 NEM time for 00:00–23:30 tomorrow (48 half-hours per region).
- **Data quality:** demand plausible range 0–20,000 MW (dbt test, severity `warn`); stale warning when latest data > 3 hours old; DB file < 500 MB.
- **Copy (verbatim on every dashboard page):**
  - `Data: Australian Energy Market Operator (AEMO), NEMWeb; weather: Open-Meteo (CC BY 4.0)`
  - `Independent student project, not affiliated with or endorsed by AEMO. Forecasts are for learning only, not trading or financial advice.`
- **Cut order if behind:** fuel-mix chart → TAS region → page 1 extra charts. Never cut tests, attribution or the accuracy table.
- **Outward-facing steps need the user's yes:** creating the public GitHub repo, the first release, deploying to Streamlit Cloud.

## Review Focus

1. **The same interval arrives in two files** (AEMO re-publishes or the archive and current folders overlap) → marts still have exactly one row per region × interval. Test: Task 6 `test_staging_dedupes_repeated_interval`.
2. **Daylight saving in temperatures:** Open-Meteo in local time would shift Sydney/Melbourne/Adelaide/Hobart temps by an hour from October to April. Test: Task 4 `test_request_uses_brisbane_timezone` and `test_temperatures_align_to_nem_time`.
3. **First run or a failed download produces a near-empty DB** that would then overwrite months of history on upload. Test: Task 5 `test_upload_refused_when_rows_shrink` and `test_collect_without_db_requires_init`.
4. **Missing inputs on forecast day** (no temperature forecast, or demand gaps) → no crash; the region is skipped and logged, and scoring ignores days with incomplete actuals. Test: Task 10 `test_daily_skips_region_with_missing_temps` and `test_score_excludes_incomplete_days`.
5. **Extreme but real values:** price at the market floor (−1000 $/MWh) or cap, and very low SA midday demand → kept, and the pipeline does not fail. Test: Task 6 `test_extreme_values_kept` (demand bounds test is `warn`, not `error`).

---

### Task 1: Repo skeleton, tooling and CI

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `.python-version`, `ingest/__init__.py`, `forecast/__init__.py`, `dashboard/__init__.py`, `tests/__init__.py`, `tests/test_smoke.py`, `.github/workflows/ci.yml`

**Interfaces:**
- Produces: importable packages `ingest`, `forecast`, `dashboard`; `uv run pytest` and `uv run ruff check .` as the standard commands.

- [ ] **Step 1:** `pyproject.toml` (Python 3.12) with dependencies `duckdb`, `pandas`, `pyarrow`, `requests`, `openpyxl`, `lightgbm`, `holidays`, `streamlit`, `plotly`, `dbt-duckdb`; dev group `pytest`, `ruff`, `pyspark`. `.gitignore`: `.venv/`, `*.duckdb`, `*.duckdb.wal`, `data/`, `dbt/target/`, `dbt/logs/`, `__pycache__/`, `.env`.
- [ ] **Step 2:** Write `tests/test_smoke.py::test_packages_import` asserting `import ingest, forecast, dashboard` succeeds.
- [ ] **Step 3:** Run `uv sync && uv run pytest -q` → `1 passed`.
- [ ] **Step 4:** `ci.yml`: on push and pull_request, ubuntu-latest, `astral-sh/setup-uv`, `actions/setup-java` (temurin 17, for Spark tests), `uv sync`, `uv run ruff check .`, `uv run pytest -q`. (dbt build is added in Task 6.)
- [ ] **Step 5:** Commit `chore: project skeleton and CI`.

### Task 2: Source spike (milestone 1) — confirm every source before building on it

Exploration whose **kept outputs** are fixtures and a facts file. No product code.

**Files:**
- Create: `docs/sources.md`, `ingest/sources.py`, `tests/fixtures/nemweb/` (one real file per source), `tests/fixtures/openmeteo/` (JSON responses), `tests/fixtures/registration_sample.xlsx` (≤ 50 rows cut from the real list)

**Interfaces:**
- Produces in `ingest/sources.py`: `REGIONS: tuple[str, ...]`, `CITY_COORDS: dict[str, tuple[float, float]]` (region → lat, lon), `HOLIDAY_SUBDIV: dict[str, str]`, `NEMWEB_BASE = "https://nemweb.com.au"`, `FOLDERS: dict[str, str]` with keys `dispatch`, `scada`, `rooftop_pv`, `predispatch` mapping to confirmed current-folder paths, `ARCHIVE_FOLDERS: dict[str, str]` with the same keys, `REGISTRATION_LIST_URL: str`, `USER_AGENT: str`, `TABLES: dict[str, dict[str, str]]` (source → {MMS key such as `"DISPATCH.REGIONSUM"` → raw table name}).

- [ ] **Step 1:** Open each NEMWeb current and archive folder in the browser; record exact case-sensitive paths (case-sensitive since April 2026; check for the `legacy` folder move). Download one file per source into `tests/fixtures/nemweb/`.
- [ ] **Step 2:** From each file's `I` rows record the table keys and column names for: dispatch region summary (`SETTLEMENTDATE, REGIONID, TOTALDEMAND`), dispatch price (`RRP`), unit SCADA (`SETTLEMENTDATE, DUID, SCADAVALUE`), rooftop PV actual (`INTERVAL_DATETIME, REGIONID, POWER`), pre-dispatch region summary (run time column, `DATETIME, REGIONID, TOTALDEMAND`). Note SCADA column positions (Spark reads by position).
- [ ] **Step 3:** Open-Meteo: call the archive, forecast and historical-forecast endpoints for Adelaide with `timezone=Australia/Brisbane` and `hourly=temperature_2m`; save the responses. Record in `docs/sources.md` whether historical-forecast covers the last 13 months on the free tier.
- [ ] **Step 4:** Confirm with no payment method on file: GitHub Actions for public repos, the GitHub Releases asset size limit, Streamlit Community Cloud sign-up. Record findings and URLs in `docs/sources.md`.
- [ ] **Step 5:** Fill `ingest/sources.py` with the confirmed values. If any spec assumption is false, stop and tell the user before Task 3.
- [ ] **Step 6:** Commit `docs: confirmed data sources and fixtures`.

### Task 3: MMS file parser and HTTP fetch

**Files:**
- Create: `ingest/mms.py`, `ingest/http.py`, `tests/test_mms.py`, `tests/test_http.py`

**Interfaces:**
- Produces: `iter_csv_members(data: bytes) -> Iterator[tuple[str, bytes]]` (yields CSVs from a raw CSV, zip, or zip-of-zips, recursively); `parse_mms(data: bytes) -> dict[str, pd.DataFrame]` (key `"<I-row field 2>.<field 3>"` upper-cased, e.g. `"DISPATCH.REGIONSUM"`; columns lower-cased; all values `str`; tables from all members concatenated); `fetch(url: str, attempts: int = 3, backoff: float = 2.0, sleep=time.sleep) -> bytes` (raises `FetchError` after the last attempt).

- [ ] **Step 1:** Tests: `test_parse_dispatch_fixture` (keys include the region-summary and price keys; region summary has 5 rows, `set(regionid) == set(REGIONS)`, and a `totaldemand` column); `test_parse_zip_of_zips` (in-memory zip holding two zipped copies of the fixture → region summary has 10 rows); `test_ignores_comment_and_end_rows` (no `C` row appears as data); `test_fetch_retries_then_succeeds` (fake session fails twice then returns `b"ok"`; `sleep` called with 2 then 4); `test_fetch_raises_after_three_failures`; `test_fetch_sends_user_agent`.
- [ ] **Step 2:** Run `uv run pytest tests/test_mms.py tests/test_http.py -q` → fails (module missing).
- [ ] **Step 3:** Implement. MMS rows: `C` = comment, `I` = header for the following `D` rows (`I,<report>,<table>,<version>,<cols…>`), `D` = data. Use the `csv` module, not `pandas.read_csv` (rows differ in width).
- [ ] **Step 4:** Tests pass.
- [ ] **Step 5:** Commit `feat(ingest): MMS parser and polite fetch`.

### Task 4: Load state, NEMWeb loader, fuel map, Open-Meteo loader

**Files:**
- Create: `ingest/state.py`, `ingest/nemweb.py`, `ingest/fuel_map.py`, `ingest/openmeteo.py`, `tests/test_nemweb.py`, `tests/test_fuel_map.py`, `tests/test_openmeteo.py`

**Interfaces:**
- Consumes: Task 3 `fetch`, `parse_mms`; Task 2 `sources`.
- Produces:
  - `state.ensure_schema(con)` creates `raw.load_log(source, url, rows, loaded_at)` and `raw.load_errors(source, url, message, failed_at)`; `state.already_loaded(con, url) -> bool`; `state.mark_loaded(con, source, url, rows)`; `state.record_error(con, source, url, message)`.
  - `nemweb.list_files(folder_url: str, fetch=fetch) -> list[str]` (absolute URLs of `.zip` links in the directory page, sorted).
  - `nemweb.load_new_files(con, source: str, folder_url: str, fetch=fetch, max_files: int | None = None, keep=None) -> LoadResult`, `LoadResult(loaded: int, skipped: int, failed: int)`; `keep: Callable[[str, pd.DataFrame], pd.DataFrame] | None` filters a parsed table before insert. Appends each table in `TABLES[source]` with `INSERT … BY NAME`, creating the table on first use. Source `scada` is not stored raw: it is aggregated with `fuel_map.aggregate_scada` and appended to `raw.fuel_mix`.
  - `fuel_map.classify_fuel(fuel_source_primary: str, technology_type: str) -> str` returning one of `solar, wind, coal, gas, hydro, battery, other`; `fuel_map.load_fuel_map(xlsx: bytes) -> pd.DataFrame[duid, regionid, fuel]`; `fuel_map.aggregate_scada(scada: pd.DataFrame, fuel_map: pd.DataFrame) -> pd.DataFrame[settlementdate, regionid, fuel, mw]` (sum of `scadavalue` per group; unknown DUIDs → `other`).
  - `openmeteo.fetch_temperatures(region: str, start: date, end: date, kind: Literal["archive", "forecast", "historical_forecast"], fetch=fetch) -> pd.DataFrame[time, region, temperature_c, kind, fetched_at]`; `openmeteo.load_weather(con, df)` appends to `raw.weather`.

- [ ] **Step 1:** Tests:
  - `test_load_twice_loads_nothing_new` (fake fetch serves a directory page with 2 fixture links: first call `loaded=2`; second `loaded=0, skipped=2`; row counts unchanged).
  - `test_bad_file_recorded_and_run_continues` (one link returns garbage → `failed=1, loaded=1`, one row in `raw.load_errors`).
  - `test_max_files_limits_downloads`; `test_raw_has_source_file_and_loaded_at`.
  - `test_classify_fuel` parametrised over solar, wind, coal, gas, hydro, battery and other, using the exact strings found in `registration_sample.xlsx`.
  - `test_aggregate_scada_sums_by_region_and_fuel` (hand-built 4-row frame → 2 expected rows with exact sums); `test_unknown_duid_is_other`.
  - `test_request_uses_brisbane_timezone` (captured URL contains `timezone=Australia%2FBrisbane`); `test_temperatures_align_to_nem_time` (24 rows per day, first `time` is the start date at 00:00, no duplicate or missing hour across the first Sunday of October).
- [ ] **Step 2:** Run → fail.
- [ ] **Step 3:** Implement. Directory pages are plain HTML listings: extract `href`s ending `.zip` with a regex and join them to `NEMWEB_BASE`.
- [ ] **Step 4:** Tests pass.
- [ ] **Step 5:** Commit `feat(ingest): idempotent NEMWeb and weather loaders`.

### Task 5: Collect CLI, upload guard and sample database

**Files:**
- Create: `ingest/cli.py`, `scripts/build_sample_db.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: Task 4 loaders.
- Produces:
  - `python -m ingest.cli collect --db PATH [--init] [--max-files N]`: runs `load_new_files` for `dispatch`, `rooftop_pv`, `scada`, `predispatch` (keeping only runs issued at 11:30 and 12:00 NEM time), and loads Open-Meteo `archive` (last 3 days) and `forecast` (next 2 days) for every region. Without `--init`, exits with code 2 if `PATH` does not exist.
  - `python -m ingest.cli counts --db PATH` prints JSON `{table_name: row_count}` for every `raw.*` table.
  - `python -m ingest.cli load-parquet --db PATH --table raw.fuel_mix --path FILE.parquet`.
  - `ingest.cli.safe_to_upload(old: dict[str, int], new: dict[str, int]) -> bool`: True only if every table in `old` exists in `new` with `new[t] >= old[t]`.
  - `scripts/build_sample_db.py OUT` builds a DuckDB from the fixtures through a fake `fetch` (used by CI, dbt and dashboard tests).
- [ ] **Step 1:** Tests: `test_collect_without_db_requires_init` (exit code 2, no file created); `test_upload_refused_when_rows_shrink` (`safe_to_upload({"raw.x": 10}, {"raw.x": 9}) is False`; missing table → False; equal or larger → True); `test_sample_db_has_all_raw_tables` (sample DB in `tmp_path`; `counts` includes `raw.dispatch_regionsum`, `raw.dispatch_price`, `raw.rooftop_pv_actual`, `raw.fuel_mix`, `raw.predispatch_regionsum`, `raw.weather`, each > 0).
- [ ] **Step 2:** Run → fail. **Step 3:** Implement with `argparse`. **Step 4:** Tests pass.
- [ ] **Step 5:** Commit `feat(ingest): collect CLI with upload guard`.

### Task 6: dbt project with data tests

**Files:**
- Create: `dbt/dbt_project.yml`, `dbt/profiles.yml` (duckdb, `path: "{{ env_var('NEM_DB') }}"`), `dbt/models/sources.yml`, `dbt/models/staging/stg_dispatch.sql`, `stg_rooftop_pv.sql`, `stg_fuel_mix.sql`, `stg_weather.sql`, `stg_aemo_forecast.sql`, `dbt/models/marts/fct_region_interval.sql`, `fct_region_daily.sql`, `fct_demand_half_hourly.sql`, `fct_aemo_forecast.sql`, `fct_forecast_accuracy.sql`, `dbt/models/schema.yml`, `dbt/tests/*.sql`, `tests/test_dbt_models.py`
- Modify: `.github/workflows/ci.yml` (build sample DB, then `uv run dbt build --project-dir dbt --profiles-dir dbt` with `NEM_DB` set)

**Interfaces:**
- Consumes: raw tables from Task 5; `forecasts.daily` / `forecasts.backtest` from Task 10 (declared as sources; `fct_forecast_accuracy` is enabled only when `var('forecasts_ready', false)` is true).
- Produces (schema `marts`):
  - `fct_region_interval(regionid, interval_end TIMESTAMP, price_rrp DOUBLE, demand_mw DOUBLE, rooftop_pv_mw DOUBLE, rooftop_pv_interpolated BOOLEAN, solar_mw, wind_mw, coal_mw, gas_mw, hydro_mw, battery_mw, other_mw DOUBLE, is_negative_price BOOLEAN)`, unique on (regionid, interval_end).
  - `fct_region_daily(regionid, trading_date DATE, min_demand_mw, peak_demand_mw, midday_dip_mw, negative_price_intervals INT, solar_share DOUBLE)`: `midday_dip_mw` = mean demand 18:00–20:00 minus mean 11:00–14:00; `solar_share` = daily mean of (solar_mw + rooftop_pv_mw) / (demand_mw + rooftop_pv_mw).
  - `fct_demand_half_hourly(regionid, period_end TIMESTAMP, demand_mw)`: mean of the six 5-min intervals, emitted only when all six exist.
  - `fct_aemo_forecast(regionid, issue_time, target_time, aemo_mw)`.
  - `fct_forecast_accuracy(regionid, target_time, issue_time, period, actual_mw, model_mw, naive_mw, aemo_mw, model_abs_err, naive_abs_err, aemo_abs_err)`, `period ∈ {backtest, live}`; excludes target dates with fewer than 48 actual half-hours.
- [ ] **Step 1:** Tests. In `schema.yml`: `unique` on a key column `regionid || '|' || interval_end`, `not_null`, `accepted_values` on regionid. Singular tests: demand range 0–20,000 with `config(severity='warn')`; no gap > 60 min in the last 7 days with `config(severity='warn')`. Pytest: `test_staging_dedupes_repeated_interval` (same fixture loaded under two `source_file` names → mart row count equals a single load; latest `loaded_at` wins); `test_extreme_values_kept` (raw price `-1000` and demand `5` MW present in the mart, `is_negative_price` true); `test_daily_negative_price_count` (3 hand-built intervals, 2 negative → 2).
- [ ] **Step 2:** Run `uv run pytest tests/test_dbt_models.py -q` → fail.
- [ ] **Step 3:** Write the models. Staging casts VARCHAR → typed columns and dedupes with `qualify row_number() over (partition by <key> order by loaded_at desc) = 1`. Rooftop PV (30 min) is forward-filled onto 5-min intervals with `rooftop_pv_interpolated = true` on filled rows.
- [ ] **Step 4:** `uv run pytest tests/test_dbt_models.py -q` and the CI `dbt build` both pass.
- [ ] **Step 5:** Commit `feat(dbt): staging and marts with data tests`.

### Task 7: Public repo, release-backed DB and hourly collection

**Files:**
- Create: `.github/workflows/collect.yml`, `scripts/release_db.sh`

**Interfaces:**
- Consumes: Task 5 CLI, Task 6 dbt.
- Produces: GitHub Release tag `data-latest` with asset `nem.duckdb`; download URL `https://github.com/<owner>/nem-energy-pipeline/releases/download/data-latest/nem.duckdb` (used by Tasks 10–11); `scripts/release_db.sh download|upload` wrapping `gh release download` / `gh release upload --clobber`.
- [ ] **Step 1:** **Ask the user** before creating the public repo. On yes, the user signs in (`gh auth login`, their own action), then `gh repo create nem-energy-pipeline --public --source . --push`.
- [ ] **Step 2:** Locally: `uv run python -m ingest.cli collect --db nem.duckdb --init --max-files 24`, then `dbt build`; `counts` all > 0. **Ask the user**, then `gh release create data-latest nem.duckdb --title "Data (latest)" --notes "Auto-updated hourly. Source: AEMO NEMWeb; Open-Meteo (CC BY 4.0)."`.
- [ ] **Step 3:** `collect.yml`: `schedule: cron '7 * * * *'` + `workflow_dispatch`; `concurrency: {group: nem-db, cancel-in-progress: false}`; `permissions: contents: write`; steps: setup-uv → `uv sync --no-dev` → download asset → `counts > old.json` → `collect` → `dbt build` → `counts > new.json` → `python -c` calling `safe_to_upload` (non-zero exit blocks the upload) → upload → log `ls -l nem.duckdb` for the 500 MB budget.
- [ ] **Step 4:** Verify: `gh workflow run collect.yml`, `gh run watch` → success; `gh release view data-latest` shows a newer asset time. After 3 scheduled runs, `counts` has grown each time.
- [ ] **Step 5:** Commit `ci: hourly collection to release-backed DuckDB`.

### Task 8: Spark backfill of 13 months

**Files:**
- Create: `scripts/download_archive.py`, `spark/__init__.py`, `spark/backfill.py`, `tests/test_backfill.py`, `docs/backfill.md`

**Interfaces:**
- Consumes: `ARCHIVE_FOLDERS`, `fetch`, `iter_csv_members`, `fuel_map.load_fuel_map`, `fuel_map.aggregate_scada`, `nemweb.load_new_files`.
- Produces:
  - `scripts/download_archive.py SOURCE OUT_DIR [--since YYYY-MM-DD]`: downloads each archive daily zip sequentially (skips files already present) and extracts inner CSVs into `OUT_DIR` (under gitignored `data/archive/`).
  - `spark.backfill.build_fuel_mix(spark, csv_glob: str, fuel_map: pd.DataFrame) -> pyspark.sql.DataFrame[settlementdate, regionid, fuel, mw]`: reads CSVs without a header, keeps rows where `_c0 == 'D'` and the table column is `UNIT_SCADA`, selects columns by the positions from Task 2, broadcast-joins the fuel map, groups and sums.
  - CLI `uv run python -m spark.backfill --scada-dir DIR --registration FILE --out data/fuel_mix.parquet`: collects with `toArrow()` and writes Parquet with pyarrow (avoids Hadoop's Windows writer, which needs winutils).
  - Region-level, rooftop PV and pre-dispatch history: `load_new_files` pointed at `ARCHIVE_FOLDERS` (pre-dispatch with the same `keep` filter as Task 5).
- [ ] **Step 1:** Test `test_build_fuel_mix_matches_pandas` (local SparkSession; the SCADA fixture through `build_fuel_mix` and through `aggregate_scada` → identical rows), skipped when `shutil.which("java") is None`.
- [ ] **Step 2:** Run → fail. **Step 3:** Implement. **Step 4:** Test passes locally and in CI.
- [ ] **Step 5:** Real backfill on the laptop (Java 17 Temurin, free). Record download size, run time and row counts in `docs/backfill.md`. `load-parquet`, `dbt build`, check `safe_to_upload`, then upload with `scripts/release_db.sh upload` only while `gh run list --workflow collect.yml --status in_progress` is empty.
- [ ] **Step 6:** Commit `feat(spark): 13-month fuel-mix backfill`.

### Task 9: Forecast features, baselines and metrics

**Files:**
- Create: `forecast/features.py`, `forecast/benchmarks.py`, `forecast/metrics.py`, `tests/test_features.py`, `tests/test_metrics.py`

**Interfaces:**
- Produces:
  - `features.issue_time_for(target_date: date) -> pd.Timestamp` = previous day 12:00.
  - `features.target_times(target_date: date) -> pd.DatetimeIndex` = 48 half-hour period ends, 00:30 to 24:00.
  - `features.build_features(demand: pd.Series, temps: pd.Series, region: str, target_times: pd.DatetimeIndex, issue_time: pd.Timestamp) -> pd.DataFrame` with columns `half_hour, dow, month, is_holiday, temp_c, temp_c_sq, lag_2d_mw, lag_7d_mw`; `demand` indexed by period end, `temps` hourly (interpolated to half-hours). Internal `_lag(demand, target_times, days, issue_time)` raises `LeakageError` if any looked-up timestamp is after `issue_time`.
  - `benchmarks.naive_forecast(demand: pd.Series, target_times) -> pd.Series` (same half-hour 7 days earlier).
  - `benchmarks.aemo_benchmark(aemo: pd.DataFrame, target_times, issue_time) -> pd.Series` (run with the latest `issue_time <= issue_time`).
  - `metrics.mae(actual, pred) -> float`; `metrics.mape(actual, pred) -> float` in percent, ignoring rows where `abs(actual) < 1` MW.
- [ ] **Step 1:** Tests: `test_lags_never_after_issue_time` (every target of a day: `lag_2d` source time < issue time); `test_one_day_lag_raises_leakage` (`_lag(..., days=1, ...)` for a target at 18:00 raises `LeakageError`); `test_holiday_flag_uses_state` (26 Jan → True for all regions; a VIC-only holiday → True only for VIC1); `test_naive_is_seven_days_earlier`; `test_aemo_benchmark_picks_latest_run_before_issue` (runs 11:30, 12:00, 12:30 → 12:00); `test_mae_mape_hand_values` (`actual=[100, 200]`, `pred=[110, 180]` → MAE 15.0, MAPE 10.0).
- [ ] **Step 2:** Run → fail. **Step 3:** Implement. **Step 4:** Pass.
- [ ] **Step 5:** Commit `feat(forecast): leak-safe features, baselines, metrics`.

### Task 10: Model, backtest, daily forecast and scoring

**Files:**
- Create: `forecast/model.py`, `forecast/backtest.py`, `forecast/daily.py`, `forecast/cli.py`, `.github/workflows/forecast.yml`, `tests/test_model.py`, `tests/test_daily.py`

**Interfaces:**
- Consumes: Task 9; marts `fct_demand_half_hourly`, `fct_aemo_forecast`, staging `stg_weather` (kind `forecast` for live; `historical_forecast` for the backtest if Task 2 confirmed it, else `archive` with `optimistic = true`).
- Produces:
  - `model.train(X: pd.DataFrame, y: pd.Series) -> lightgbm.LGBMRegressor` (`random_state=42`, `n_estimators=500`, `learning_rate=0.05`); `model.predict(m, X) -> pd.Series`.
  - `backtest.rolling_backtest(con, region: str, start: date, end: date, refit_days: int = 7) -> pd.DataFrame[regionid, issue_time, target_time, actual_mw, model_mw, naive_mw, aemo_mw]`; each fit uses only targets with period end ≤ the issue time of the first day in its block. Writes `forecasts.backtest` and one `forecasts.backtest_meta(optimistic BOOLEAN, run_at TIMESTAMP)` row.
  - `daily.run_daily(con, now: pd.Timestamp) -> pd.DataFrame`, writing 48 rows per region to `forecasts.daily(regionid, issue_time, target_time, model_mw, naive_mw)`; a region with missing temps or lags is skipped and logged.
  - `python -m forecast.cli backtest --db PATH --months 6`; `python -m forecast.cli daily --db PATH`.
- [ ] **Step 1:** Tests: `test_backtest_never_trains_on_future` (synthetic 60-day series; a spy on `train` records max training target time < each block's issue time); `test_model_beats_naive_on_synthetic` (demand = 1000 + 300·sin(2π·hour/24) + 20·temp + noise → model MAE < naive MAE); `test_daily_writes_48_rows_per_region`; `test_daily_skips_region_with_missing_temps`; `test_score_excludes_incomplete_days` (a date with 47 actuals → no `fct_forecast_accuracy` rows for that date after `dbt build --vars '{forecasts_ready: true}'`).
- [ ] **Step 2:** Run → fail. **Step 3:** Implement. **Step 4:** Pass.
- [ ] **Step 5:** Run `backtest` on the real DB (6 months); write the per-region MAE/MAPE table for model, naive and AEMO into `docs/results.md`, labelled "optimistic (actual weather)" when `optimistic` is true.
- [ ] **Step 6:** `forecast.yml`: `cron '5 2 * * *'` (12:05 NEM time) + `workflow_dispatch`, `nem-db` concurrency group, steps: download → `forecast.cli daily` → `dbt build --vars '{forecasts_ready: true}'` → guarded upload. Verify with `gh workflow run forecast.yml` → success and 240 new `forecasts.daily` rows.
- [ ] **Step 7:** Commit `feat(forecast): backtest, daily forecast and scoring`.

### Task 11: Dashboard

**Files:**
- Create: `dashboard/app.py`, `dashboard/pages/1_Solar_and_the_grid.py`, `dashboard/pages/2_Forecast_accuracy.py`, `dashboard/data.py`, `dashboard/copy.py`, `tests/test_dashboard.py`, `requirements.txt` (`uv export --no-dev --no-hashes > requirements.txt`, for Streamlit Cloud)

**Interfaces:**
- Consumes: marts and forecasts tables; release URL from Task 7.
- Produces:
  - `copy.ATTRIBUTION`, `copy.DISCLAIMER` (exact text from Global Constraints).
  - `data.DB_URL: str`; `data.get_connection(path: str | None = None) -> duckdb.DuckDBPyConnection` (downloads `DB_URL` to a temp file when `path` is None, else uses `path`; also honours env `NEM_DB_PATH`; opened `read_only=True`; pages wrap it in `st.cache_resource(ttl=3600)`).
  - `latest_interval(con) -> pd.Timestamp`; `is_stale(latest: pd.Timestamp, now: pd.Timestamp, max_age_hours: int = 3) -> bool`; `headline_cards(con, region) -> dict` with keys `min_demand_today`, `min_demand_year_ago`, `negative_intervals_month`, `midday_solar_share`; `duck_curve(con, region, month: date) -> DataFrame[time_of_day, this_year_mw, last_year_mw]`; `negative_price_counts(con) -> DataFrame[month, regionid, intervals]`; `fuel_mix_by_hour(con, region) -> DataFrame[hour, fuel, mw]`; `forecast_vs_aemo(con, region, target_date) -> DataFrame[target_time, model_mw, aemo_mw, actual_mw]`; `accuracy_table(con) -> DataFrame[regionid, source, period, mae_mw, mape_pct]` (`period ∈ {backtest, live_30d}`).
  - Every page shows `ATTRIBUTION`, `DISCLAIMER`, the freshness timestamp, and `st.warning` when `is_stale`.
- [ ] **Step 1:** Tests on the sample DB (Task 5) after a dbt build: `test_is_stale_boundaries` (2 h 59 m → False; 3 h 01 m → True); `test_duck_curve_has_288_points`; `test_accuracy_table_columns`; `test_pages_render_without_error` (Streamlit `AppTest.from_file` per page with `NEM_DB_PATH` set to the sample DB → no exceptions; page text contains `ATTRIBUTION` and `DISCLAIMER`); `test_connection_is_read_only` (an INSERT raises).
- [ ] **Step 2:** Run → fail. **Step 3:** Implement with Plotly charts and a one-sentence plain-English caption under each chart. **Step 4:** Pass.
- [ ] **Step 5:** Run locally (`uv run streamlit run dashboard/app.py` with `NEM_DB_PATH` set to a downloaded copy) and check both pages in the browser pane.
- [ ] **Step 6:** Commit `feat(dashboard): solar story and forecast accuracy pages`.

### Task 12: Deploy, README, demo and done check

**Files:**
- Create: `README.md`, `docs/architecture.mmd` (Mermaid, rendered by GitHub)

**Interfaces:**
- Consumes: everything above.

- [ ] **Step 1:** **Ask the user**, then they sign in to Streamlit Community Cloud with GitHub (no card) and deploy `dashboard/app.py` from `main`. Record the public URL.
- [ ] **Step 2:** README: summary with the live link and the accuracy headline from `docs/results.md`; architecture diagram; "Decisions and trade-offs" (no Kafka, no Airflow, DuckDB file on Releases instead of a database service, hourly refresh, 2-day lag leakage rule, Spark only for the archive); how to run locally (`uv sync`, sample DB, `streamlit run`); data credits and disclaimer verbatim; "the free host sleeps, click wake up" note.
- [ ] **Step 3:** The user records the 2-minute demo (OBS or Clipchamp free) and uploads it to YouTube as unlisted; link it in the README.
- [ ] **Step 4:** Done check against spec §1, with evidence for each: the live URL opens in a clean browser with freshness < 2 h; the accuracy table has backtest and live rows for every region; README sections present; latest CI run green (`gh run list --workflow ci.yml -L 1`); video link works; no payment method on the GitHub or Streamlit accounts (the user checks each billing page).
- [ ] **Step 5:** Commit `docs: README, architecture and results`. Build the graphify map (`/graphify .`). Offer to add the project to `cv.md` through career-ops `add` mode (confirm before writing).
