# Data sources (confirmed 2026-11-12)

## AEMO NEMWeb
Folder names are case-sensitive. Listings are plain HTML with `HREF="/Reports/..."` links.

| Source | Current folder (≈2 days, 5-min files) | Archive folder | Table(s) used |
|---|---|---|---|
| dispatch | `/Reports/CURRENT/DispatchIS_Reports/` | `/Reports/ARCHIVE/DispatchIS_Reports/` (daily zips from 2025-11-01) | `DISPATCH.REGIONSUM` (TOTALDEMAND), `DISPATCH.PRICE` (RRP) |
| scada | `/Reports/CURRENT/Dispatch_SCADA/` | `/Reports/ARCHIVE/Dispatch_SCADA/` (daily) | `DISPATCH.UNIT_SCADA` (SETTLEMENTDATE, DUID, SCADAVALUE at positions 4, 5, 6) |
| rooftop_pv | `/Reports/CURRENT/ROOFTOP_PV/ACTUAL/` (MEASUREMENT and SATELLITE files, 30-min) | `/Reports/ARCHIVE/ROOFTOP_PV/ACTUAL/` | `ROOFTOP.ACTUAL` (INTERVAL_DATETIME, REGIONID, POWER, QI, TYPE) |
| predispatch | `/Reports/CURRENT/PredispatchIS_Reports/` (one run per half-hour, ~12 MB each) | `/Reports/ARCHIVE/PredispatchIS_Reports/` (weekly zips) | `PREDISPATCH.REGION_SOLUTION` (TOTALDEMAND per DATETIME); run time = timestamp in file name |

Findings that shape the code:
- `DISPATCH.*` rows carry an `INTERVENTION` flag: use `INTERVENTION = 0` only (the market-price run).
- Rooftop PV has two estimate types per interval; prefer `MEASUREMENT` (QI 1), fall back to `SATELLITE`.
- Pre-dispatch files are large: keep only `REGION_SOLUTION` from runs issued at 11:30 and 12:00.
- Fixtures in `tests/fixtures/nemweb/` are real files from 2026-11-12 (pre-dispatch trimmed to `REGION_SOLUTION`).

## Generator fuel types
AEMO NEM Registration and Exemption List (xlsx), sheet `PU and Scheduled Loads`, columns `DUID`, `Region`,
`Fuel Source - Primary`, `Fuel Source - Descriptor`. Coal vs gas is in the descriptor ("Coal Seam Methane" and
"Waste Coal Mine Gas" are gas). 483 of 520 units in a SCADA file matched; unmatched → `other`. 8 duplicate DUIDs → keep first.

## Open-Meteo (free, non-commercial, no key, CC BY 4.0)
- `archive-api.open-meteo.com/v1/archive` — observed/reanalysis temperatures.
- `api.open-meteo.com/v1/forecast` — live forecast.
- `historical-forecast-api.open-meteo.com/v1/forecast` — archive of past forecasts; worked for 2025-11-01 without a key.
  It stitches the first hours of each model run, so it is a *short-lead* forecast, closer to the truth than a true
  day-ahead forecast. The backtest is therefore labelled optimistic; live scoring is the honest number.
- Always `timezone=Australia/Brisbane` (UTC+10, no DST) so times line up with NEM time.

## Free hosting (no payment method)
- GitHub Actions: free on public repositories with GitHub-hosted runners. Release assets: up to 2 GiB each.
- Streamlit Community Cloud: sign in with GitHub, free public apps; apps sleep when idle.
- Confirm at sign-up (Tasks 7 and 12) that no card is requested; if one is, stop.
