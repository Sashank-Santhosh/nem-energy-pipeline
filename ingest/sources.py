"""Confirmed source constants (see docs/sources.md, checked 2026-11-12)."""

REGIONS: tuple[str, ...] = ("NSW1", "QLD1", "VIC1", "SA1", "TAS1")

CITY_COORDS: dict[str, tuple[float, float]] = {
    "NSW1": (-33.87, 151.21),  # Sydney
    "QLD1": (-27.47, 153.03),  # Brisbane
    "VIC1": (-37.81, 144.96),  # Melbourne
    "SA1": (-34.93, 138.60),  # Adelaide
    "TAS1": (-42.88, 147.33),  # Hobart
}

HOLIDAY_SUBDIV: dict[str, str] = {
    "NSW1": "NSW", "QLD1": "QLD", "VIC1": "VIC", "SA1": "SA", "TAS1": "TAS",
}

NEMWEB_BASE = "https://nemweb.com.au"

FOLDERS: dict[str, str] = {
    "dispatch": "/Reports/CURRENT/DispatchIS_Reports/",
    "scada": "/Reports/CURRENT/Dispatch_SCADA/",
    "rooftop_pv": "/Reports/CURRENT/ROOFTOP_PV/ACTUAL/",
    "predispatch": "/Reports/CURRENT/PredispatchIS_Reports/",
}

ARCHIVE_FOLDERS: dict[str, str] = {
    "dispatch": "/Reports/ARCHIVE/DispatchIS_Reports/",
    "scada": "/Reports/ARCHIVE/Dispatch_SCADA/",
    "rooftop_pv": "/Reports/ARCHIVE/ROOFTOP_PV/ACTUAL/",
    "predispatch": "/Reports/ARCHIVE/PredispatchIS_Reports/",
}

REGISTRATION_LIST_URL = (
    "https://www.aemo.com.au/-/media/files/electricity/nem/participant_information/"
    "nem-registration-and-exemption-list.xlsx"
)
REGISTRATION_SHEET = "PU and Scheduled Loads"

USER_AGENT = "nem-energy-pipeline/0.1 (student portfolio project)"

# source -> {MMS table key -> raw table}. "scada" is aggregated before storage.
TABLES: dict[str, dict[str, str]] = {
    "dispatch": {
        "DISPATCH.REGIONSUM": "raw.dispatch_regionsum",
        "DISPATCH.PRICE": "raw.dispatch_price",
    },
    "rooftop_pv": {"ROOFTOP.ACTUAL": "raw.rooftop_pv_actual"},
    "predispatch": {"PREDISPATCH.REGION_SOLUTION": "raw.predispatch_regionsum"},
    "scada": {"DISPATCH.UNIT_SCADA": "raw.fuel_mix"},
}

# Column positions in UNIT_SCADA "D" rows (0-based), for Spark's headerless read.
SCADA_POS = {"settlementdate": 4, "duid": 5, "scadavalue": 6}

OPEN_METEO = {
    "archive": "https://archive-api.open-meteo.com/v1/archive",
    "forecast": "https://api.open-meteo.com/v1/forecast",
    "historical_forecast": "https://historical-forecast-api.open-meteo.com/v1/forecast",
}
