"""LightGBM regressor with fixed settings so results are reproducible."""

import lightgbm as lgb
import pandas as pd


def train(X: pd.DataFrame, y: pd.Series) -> lgb.LGBMRegressor:
    m = lgb.LGBMRegressor(n_estimators=500, learning_rate=0.05, random_state=42,
                          deterministic=True, force_row_wise=True, verbose=-1)
    return m.fit(X, y)


def predict(m: lgb.LGBMRegressor, X: pd.DataFrame) -> pd.Series:
    return pd.Series(m.predict(X), index=X.index)
