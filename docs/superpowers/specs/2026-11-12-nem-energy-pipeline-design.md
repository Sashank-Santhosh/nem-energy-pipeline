# NEM Energy Pipeline — Design Spec

**Date:** 2026-11-12 · **Status:** Draft for review · **Build window:** 13 Nov – 3 Dec 2026

## 1. Purpose

A flagship portfolio project that proves one person can do all three jobs on a real, live dataset:

| Role | What proves it |
|---|---|
| Data engineer | A scheduled, idempotent pipeline with raw → clean layers, data-quality tests, and a Spark backfill of the large historical archive |
| Data / BI analyst | A public dashboard telling one clear story: how rooftop solar is changing Australia's grid |
| Data scientist | A day-ahead demand forecast per region, backtested properly and scored live against AEMO's own forecast |

**Audience:** recruiters and hiring managers for graduate/junior data roles in Melbourne. They will spend 2 minutes on it, so the live link, README and demo video must make the point fast.

**Success criteria (definition of done):**
1. Public live dashboard URL, refreshing on its own at least hourly.
2. Forecast accuracy table (MAE and MAPE per region) for my model, a naive baseline and AEMO's forecast, from a rolling backtest **and** from live scoring.
3. README with an architecture diagram, a "decisions and trade-offs" section, and how to run it locally.
4. Automated tests pass in CI (unit tests + dbt tests).
5. A 2-minute demo video linked from the README.
6. Costs nothing, ever: no paid plan, no payment method on any account, no service that can bill overage (see §9 "Zero-payment rule").

## 2. Scope

**In:** all 5 NEM regions (NSW1, QLD1, VIC1, SA1, TAS1); 5-minute dispatch price and demand; half-hourly rooftop PV estimates; generator-level output aggregated to fuel mix; AEMO's day-ahead demand forecast; temperature (actual and forecast) for one capital city per region; 13 months of history.

**Out (deliberately):** Kafka (data arrives as 5-minute batch files, so a scheduler is the right tool); Airflow (GitHub Actions is enough at this scale); price forecasting; user accounts; mobile app.

**Stretch (only after done criteria are met):** a "price spike risk" indicator (high/low chance of a spike in the next few hours).

## 3. Architecture

```
AEMO NEMWeb ──┐   collect (GitHub Actions, hourly):
Open-Meteo  ──┼─>  1. download latest nem.duckdb from GitHub Release "data-latest"
              │    2. append new files to raw.*  3. dbt build → marts.*
              │    4. upload nem.duckdb back to the release ──────┐
13-month ─────┘   (backfill: Spark on laptop → Parquet → raw.*)   │
archive                                                           ├──> Streamlit dashboard (downloads the file, read-only)
                  forecast (GitHub Actions, daily) ── same file ──┘    writes forecasts.* then re-uploads
```

**Decision: the database is a single DuckDB file stored as a GitHub Release asset.** No database service at all, so nothing can bill. The file stays small (§9), a release asset is replaced in place (no git-history growth), and everything lives in one free GitHub account. Workflows share a `concurrency` group so two runs never edit the file at the same time.

**Decision: hourly refresh, not every 30 minutes.** Each run picks up the twelve 5-minute files since the last run. Data stays "near-live" (≤ ~1 hour old), and GitHub's scheduler starting a few minutes late doesn't matter.

**Principle: raw is append-only.** Raw tables store source files untouched, plus `source_file` and `loaded_at` columns. Every clean table can be rebuilt from raw, so a bug fix never needs a re-download.

## 4. Data sources

| Data | Source | Grain | Notes |
|---|---|---|---|
| Regional price (RRP) and demand (TOTALDEMAND) | NEMWeb dispatch reports (DISPATCHREGIONSUM / DISPATCHPRICE tables) | 5 min × region | TOTALDEMAND is operational demand; it excludes rooftop PV, which is why demand dips at midday |
| Rooftop PV estimate | NEMWeb ROOFTOP_PV_ACTUAL | 30 min × region | An AEMO estimate, not metered; labelled as such on the dashboard |
| Generator output | NEMWeb Dispatch_SCADA (DISPATCH_UNIT_SCADA) | 5 min × unit | Large: hundreds of units; this is the Spark job's input |
| Generator fuel type | AEMO NEM Registration and Exemption List | per unit | Maps unit → fuel (solar, wind, coal, gas, hydro, battery, other) |
| AEMO demand forecast | NEMWeb pre-dispatch reports (PREDISPATCHREGIONSUM) | 30 min × region | The benchmark for my forecast |
| Temperature (actual + forecast) | Open-Meteo (free, non-commercial, CC BY 4.0) | hourly × city | Sydney, Brisbane, Melbourne, Adelaide, Hobart |

**To verify in milestone 1 (spike), before building on them:** exact NEMWeb folder names and file columns (AEMO moved to HTTPS with case-sensitive paths in April 2026 and is moving superseded reports to a `legacy` folder); whether Open-Meteo's free tier includes the historical *forecast* archive (needed for a leak-free backtest, see §6); that GitHub Actions, GitHub Releases and Streamlit Community Cloud can all be used with no payment method on file.

## 5. Components and repo layout

```
nem-energy-pipeline/
  ingest/            # Python: download, parse, load to raw.* (one module per source)
    nemweb.py        #   list folder → find unseen files → download → parse CSV → load
    openmeteo.py
    state.py         #   which files have been loaded (a raw.load_log table)
    fuel_map.py      #   unit → fuel type, shared by the hourly job and the Spark backfill
  spark/backfill.py  # PySpark: unit SCADA archive → 5-min fuel mix per region → Parquet
  dbt/               # dbt-duckdb project: staging → intermediate → marts, with tests
  forecast/          # train.py, predict.py, backtest.py, score.py
  dashboard/         # Streamlit app: app.py, pages/1_solar.py, pages/2_forecast.py
  tests/             # pytest
  .github/workflows/ # collect.yml (hourly), forecast.yml (daily), ci.yml (on push)
```

Each unit has one job and talks to others only through database tables:
- **ingest** knows sources, not models. Re-running it on the same files loads nothing new.
- **dbt** knows tables, not sources.
- **forecast** reads `marts.*` and writes `forecasts.*`.
- **dashboard** only reads `marts.*` and `forecasts.*`, never raw, and never writes.

**Key dbt models (marts):**
- `fct_region_interval` — 5-min price, demand, rooftop PV (interpolated from 30 min, flagged), fuel mix shares, `is_negative_price`.
- `fct_region_daily` — daily min/peak demand, midday dip depth, negative-price intervals, solar share.
- `fct_forecast_accuracy` — per region per target interval: actual, my forecast, AEMO forecast, naive baseline, errors.

**Tools (all free and open source, or free hosted with no card):** Python 3.12, `uv` for dependencies, DuckDB, dbt-duckdb, PySpark (local mode), LightGBM, Streamlit + Plotly, pytest, GitHub Actions + Releases, Streamlit Community Cloud.

**Decision: dbt-duckdb on a DuckDB file.** The same SQL runs identically on my laptop, in CI and in the scheduled job, so tests are free and there is no cloud database to pay for or migrate.

## 6. Forecast design

- **Target:** operational demand (TOTALDEMAND) per region, half-hourly, for the next calendar day (48 values per region).
- **Issue time:** daily at 12:00 NEM time (AEST, UTC+10, no daylight saving — all timestamps in the project use NEM time), forecasting 00:00–24:00 tomorrow. AEMO's benchmark is the pre-dispatch forecast **issued closest to 12:00 on the same day**, so both forecasts have the same information horizon.
- **Models:**
  1. Naive baseline: same half-hour one week earlier.
  2. Main model: LightGBM, one model per region. Features: half-hour of day, day of week, public holiday (per state, `holidays` package), month, forecast temperature (and squared, for heating and cooling load), demand from the same half-hour 1 and 7 days earlier. No feature uses information after the issue time.
- **Backtest:** rolling-origin over the last 6 months, refitting weekly; report MAE (MW) and MAPE (%) per region for all three forecasts.
- **Leakage rule:** the backtest uses the temperature *forecast* that existed at issue time (Open-Meteo historical forecast archive). If that is not available for free, the backtest uses actual temperatures and the results are labelled "optimistic (actual weather)"; live scoring is then the honest number.
- **Live scoring:** each day's forecast is scored once actuals arrive; the dashboard shows a rolling 30-day accuracy.

## 7. Dashboard

**Page 1 — "How is rooftop solar changing the grid?"** (main story)
- Headline cards: today's minimum demand vs a year ago; negative-price intervals this month; rooftop solar share at midday.
- The "duck curve": average demand by time of day, this month vs the same month a year earlier, per region.
- Negative prices: count per region per month over the 13 months.
- Fuel mix by time of day for a selected region.
- Short plain-English captions under each chart explaining what it shows.

**Page 2 — "How good is my forecast?"**
- Tomorrow's forecast vs AEMO's forecast, per region.
- Yesterday: my forecast, AEMO's, and actual, on one chart.
- Accuracy table: backtest and rolling live MAE/MAPE for mine, AEMO's and the baseline.

**Every page:** "Data: Australian Energy Market Operator (AEMO), NEMWeb; weather: Open-Meteo (CC BY 4.0)", a data-freshness timestamp, and "Independent student project, not affiliated with or endorsed by AEMO. Forecasts are for learning only, not trading or financial advice."

**Performance:** queries are cached for 1 hour; pages read only pre-aggregated marts.

## 8. Error handling and data quality

- **Downloads:** retry with backoff (3 attempts); a missing or late file is skipped and picked up next run, because state is tracked per file, not per run.
- **Politeness:** one request per file, a descriptive User-Agent, no parallel hammering.
- **Bad files:** files that fail parsing are recorded in `raw.load_errors` and skipped; the run continues.
- **dbt tests:** unique and not-null keys (region + interval); accepted region values; demand within plausible bounds (0–20,000 MW); no gaps longer than 1 hour in the last 7 days (freshness test).
- **Failure alerts:** a failed scheduled run fails the GitHub Action, which emails the repo owner by default.
- **Dashboard:** if data is stale (> 3 hours), show a visible warning rather than silently presenting old numbers.

## 9. Operations and budget

- **Zero-payment rule (hard requirement):**
  - Only services usable with **no payment method on file**: GitHub (public repo: Actions on GitHub-hosted runners, Releases), Streamlit Community Cloud, AEMO NEMWeb, Open-Meteo free non-commercial API (no key).
  - **Never add a credit/debit card or PayPal to any account used by this project.** With no payment method, a service cannot charge; at worst it stops working, which the fallbacks below cover.
  - **No paid-capable services:** no MotherDuck, AWS, GCP, Azure, Databricks, Snowflake, paid APIs, custom domains, or paid video tools. The Claude API is not used; development uses the existing Claude subscription only.
  - If any step ever asks for a card, stop and pick a free alternative; never "start a free trial".
  - Demo video: free tools only (OBS Studio or Windows' built-in Clipchamp free tier), uploaded to YouTube as unlisted.
- **Free-tier behaviour to expect:** Streamlit Community Cloud puts apps to sleep after a period without visitors; the first visitor clicks "wake up" and waits under a minute. The README says so.
- **Storage estimate:** region-level data is ~0.5M rows/region/year. Unit-level SCADA is aggregated to fuel mix per region before upload (by Spark for the backfill; by the hourly collect job, in DuckDB, for new files — both using the same unit→fuel mapping in `ingest/fuel_map.py`), so raw unit data never goes to the cloud. Well under 1 GB.
- **File-size budget:** keep `nem.duckdb` under 500 MB (GitHub release assets allow up to 2 GB each). Measured in milestone 2; if it grows, older 5-minute data is rolled up to 30-minute.
- **Fallback if GitHub Releases ever becomes unsuitable:** publish the same file as a free public Hugging Face dataset (no card needed). Models and dashboard don't change, only the download URL.
- **Secrets:** none needed for data sources. Workflows use GitHub's built-in `GITHUB_TOKEN` to update the release; nothing is stored in code.

## 10. Testing

- **Unit (pytest):** NEMWeb CSV parsing against saved sample files; the "already loaded" check (load twice → no duplicates); feature engineering (no feature uses data after issue time — an explicit leakage test); metric calculations against hand-computed values.
- **Data (dbt tests):** see §8.
- **CI:** on every push, run pytest and `dbt build` against a small local DuckDB built from sample files.
- **Manual check before calling it done:** the dashboard loads from a clean browser, both pages render, and the freshness timestamp is under 2 hours old.

## 11. Milestones

| # | Dates | Outcome |
|---|---|---|
| M1 | 13–15 Nov | Spike: confirm every source in §4 (files, columns, licences, free limits). Repo skeleton, CI, first data loaded locally |
| M2 | 16–20 Nov | Hourly collection running in GitHub Actions; dbt models + tests; Spark backfill of 13 months |
| M3 | 21–26 Nov | Backtest done; daily forecast job live; accuracy table |
| M4 | 27 Nov – 1 Dec | Both dashboard pages deployed publicly |
| M5 | 2–3 Dec | README, diagram, decisions section, demo video, CV/LinkedIn entry |

**If behind schedule:** cut in this order: fuel mix chart → TAS region → page 1 extra charts. Never cut tests, attribution or the accuracy table.

## 12. Risks

| Risk | Mitigation |
|---|---|
| NEMWeb file layout differs from documentation | M1 spike reads real files first; parsers tested on saved samples |
| A free service changes its terms | No payment method anywhere, so it can only stop, not charge; Hugging Face fallback (§9) |
| Two scheduled runs overwrite each other's file | Shared `concurrency` group; upload only after a successful `dbt build` |
| Leak-free backtest not possible on free weather data | Label backtest as optimistic; rely on live scoring |
| Recruiters see "built with AI" as shallow | README decisions section and demo explain every choice in my own words; I can rebuild any part from memory |
| Time lost to holidays / Henkel prep | Hard cut order in §11 |
