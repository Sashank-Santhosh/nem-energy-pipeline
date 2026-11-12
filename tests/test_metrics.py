import pytest

from forecast.metrics import mae, mape


def test_mae_mape_hand_values():
    assert mae([100, 200], [110, 180]) == pytest.approx(15.0)
    assert mape([100, 200], [110, 180]) == pytest.approx(10.0)


def test_mape_ignores_near_zero_actuals():
    assert mape([0.5, 100], [10, 110]) == pytest.approx(10.0)
