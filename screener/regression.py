"""AUM prediction model: OLS regression with GradientBoosting fallback."""
from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)


@dataclass
class ModelResult:
    """Container for trained model and diagnostics."""
    model: object
    r_squared: float
    feature_importances: dict[str, float]
    model_type: str
    n_training: int


def build_training_set(
    etp_df: pd.DataFrame,
    stock_df: pd.DataFrame,
) -> pd.DataFrame | None:
    """Build training set from existing leveraged single-stock ETFs with AUM > 0.

    Joins ETF data with underlying stock characteristics.
    Target: current AUM (t_w4.aum).
    """
    underlier_col = "q_category_attributes.map_li_underlier"
    aum_col = "t_w4.aum"

    if underlier_col not in etp_df.columns or aum_col not in etp_df.columns:
        log.error("Missing columns for training set")
        return None

    # Filter to leveraged single-stock ETFs with AUM > 0
    lev = etp_df[
        (etp_df.get("uses_leverage") == True)
        & (etp_df[underlier_col].notna())
        & (etp_df[underlier_col] != "")
        & (pd.to_numeric(etp_df[aum_col], errors="coerce").fillna(0) > 0)
    ].copy()

    if len(lev) < 10:
        log.warning("Only %d training samples (need at least 10)", len(lev))
        return None

    # Compute competitor count per underlier
    underlier_counts = lev[underlier_col].value_counts().to_dict()
    lev["competitor_count"] = lev[underlier_col].map(underlier_counts).fillna(1).astype(int)

    # Compute fund age in days
    if "inception_date" in lev.columns:
        lev["inception_date"] = pd.to_datetime(lev["inception_date"], errors="coerce")
        lev["fund_age_days"] = (pd.Timestamp.now() - lev["inception_date"]).dt.days.fillna(365)
    else:
        lev["fund_age_days"] = 365

    # Join with stock_data on underlier
    stock_features = stock_df[["ticker_raw", "Mkt Cap", "Total Call OI", "Total OI",
                                "Avg Volume 30D", "Volatility 30D", "Short Interest Ratio",
                                "Institutional Owner % Shares Outstanding",
                                "Turnover / Traded Value"]].copy()
    stock_features = stock_features.rename(columns={"ticker_raw": underlier_col})

    training = lev.merge(stock_features, on=underlier_col, how="inner", suffixes=("", "_stock"))

    if len(training) < 10:
        log.warning("After merge: only %d training samples", len(training))
        return None

    log.info("Training set built: %d samples", len(training))
    return training


def _prepare_features(training_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """Extract feature matrix X and target y from training set."""
    feature_cols = [
        "Mkt Cap", "Total Call OI", "Total OI", "Avg Volume 30D",
        "Volatility 30D", "Short Interest Ratio",
        "Institutional Owner % Shares Outstanding",
        "Turnover / Traded Value", "competitor_count", "fund_age_days",
    ]

    available = [c for c in feature_cols if c in training_df.columns]
    X = training_df[available].copy()

    # Log-transform skewed features
    log_cols = ["Mkt Cap", "Total Call OI", "Total OI", "Avg Volume 30D", "Turnover / Traded Value"]
    for col in log_cols:
        if col in X.columns:
            X[col] = np.log1p(pd.to_numeric(X[col], errors="coerce").fillna(0))

    X = X.apply(pd.to_numeric, errors="coerce").fillna(0)
    y = pd.to_numeric(training_df["t_w4.aum"], errors="coerce").fillna(0)

    return X, y


def train_model(training_df: pd.DataFrame) -> ModelResult | None:
    """Train AUM prediction model. OLS first, GradientBoosting if R^2 < 0.5."""
    X, y = _prepare_features(training_df)

    if len(X) < 10 or y.sum() == 0:
        log.warning("Insufficient training data")
        return None

    # Try OLS first
    from sklearn.linear_model import LinearRegression
    from sklearn.model_selection import cross_val_score

    ols = LinearRegression()
    scores = cross_val_score(ols, X, y, cv=min(5, len(X)), scoring="r2")
    ols_r2 = max(scores.mean(), 0)

    log.info("OLS R-squared (CV): %.3f", ols_r2)

    if ols_r2 >= 0.5:
        ols.fit(X, y)
        importances = dict(zip(X.columns, np.abs(ols.coef_) / max(np.abs(ols.coef_).sum(), 1e-10)))
        return ModelResult(
            model=ols, r_squared=ols_r2,
            feature_importances=importances, model_type="OLS",
            n_training=len(X),
        )

    # Fallback to GradientBoosting
    from sklearn.ensemble import GradientBoostingRegressor

    gb = GradientBoostingRegressor(n_estimators=100, max_depth=3, random_state=42)
    scores = cross_val_score(gb, X, y, cv=min(5, len(X)), scoring="r2")
    gb_r2 = max(scores.mean(), 0)

    log.info("GradientBoosting R-squared (CV): %.3f", gb_r2)

    gb.fit(X, y)
    importances = dict(zip(X.columns, gb.feature_importances_))

    return ModelResult(
        model=gb, r_squared=gb_r2,
        feature_importances=importances, model_type="GradientBoosting",
        n_training=len(X),
    )


def predict_aum(
    model_result: ModelResult,
    stock_df: pd.DataFrame,
) -> pd.DataFrame:
    """Predict AUM for all candidate stocks. Adds predicted_aum columns."""
    feature_cols = [
        "Mkt Cap", "Total Call OI", "Total OI", "Avg Volume 30D",
        "Volatility 30D", "Short Interest Ratio",
        "Institutional Owner % Shares Outstanding",
        "Turnover / Traded Value",
    ]

    df = stock_df.copy()

    # Add placeholder columns that training had
    df["competitor_count"] = 0  # New product = no existing competitors
    df["fund_age_days"] = 180   # Assume 6 months post-launch

    available = [c for c in feature_cols + ["competitor_count", "fund_age_days"] if c in df.columns]
    X = df[available].copy()

    # Log-transform same features as training
    log_cols = ["Mkt Cap", "Total Call OI", "Total OI", "Avg Volume 30D", "Turnover / Traded Value"]
    for col in log_cols:
        if col in X.columns:
            X[col] = np.log1p(pd.to_numeric(X[col], errors="coerce").fillna(0))

    X = X.apply(pd.to_numeric, errors="coerce").fillna(0)

    predictions = model_result.model.predict(X)
    predictions = np.maximum(predictions, 0)  # AUM can't be negative

    df["predicted_aum"] = predictions.round(2)

    # Confidence interval: rough estimate based on model R-squared
    uncertainty = 1 - model_result.r_squared
    df["predicted_aum_low"] = (predictions * (1 - uncertainty)).round(2)
    df["predicted_aum_high"] = (predictions * (1 + uncertainty)).round(2)
    df["predicted_aum_low"] = df["predicted_aum_low"].clip(lower=0)

    log.info("AUM predicted for %d stocks. Median: $%.1fM", len(df), df["predicted_aum"].median())

    return df
