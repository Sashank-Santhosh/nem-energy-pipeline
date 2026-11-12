"""Forecast error metrics."""

import numpy as np


def mae(actual, pred) -> float:
    a, p = np.asarray(actual, float), np.asarray(pred, float)
    return float(np.nanmean(np.abs(a - p)))


def mape(actual, pred) -> float:
    """Mean absolute percentage error, ignoring near-zero actuals (|actual| < 1 MW)."""
    a, p = np.asarray(actual, float), np.asarray(pred, float)
    ok = np.abs(a) >= 1
    return float(np.nanmean(np.abs(a[ok] - p[ok]) / np.abs(a[ok])) * 100)
