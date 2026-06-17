"""
data_loader.py — Multi-source financial data loader
Supports: yfinance (real), synthetic correlated (Cholesky), sector-based simulation
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta

# ---------------------------------------------------------------------------
# Real-data loader (yfinance)
# ---------------------------------------------------------------------------

ASSET_UNIVERSE = {
    "Banks": ["JPM", "BAC", "C", "WFC", "GS"],
    "Insurance": ["AIG", "MET", "PRU", "ALL", "TRV"],
    "Asset Managers": ["BLK", "SCHW", "MS", "TROW", "IVZ"],
    "FinTech": ["V", "MA", "PYPL", "XYZ", "COIN"],   # SQ → XYZ (Block Inc)
}

SECTOR_COLORS = {
    "Banks": "#FF4B4B",
    "Insurance": "#00C4FF",
    "Asset Managers": "#FFB700",
    "FinTech": "#00FF88",
}


def load_real_data(tickers: list[str], period_days: int = 500) -> tuple[np.ndarray, list[str], dict]:
    """Fetch daily log-returns from yfinance. Falls back to synthetic on failure."""
    try:
        import yfinance as yf  # type: ignore
        import warnings, logging
        # Suppress yfinance noise about delisted tickers
        logging.getLogger("yfinance").setLevel(logging.CRITICAL)
        warnings.filterwarnings("ignore")

        end = datetime.today()
        start = end - timedelta(days=period_days + 60)

        raw = yf.download(
            tickers, start=start, end=end,
            progress=False, auto_adjust=True,
            actions=False,
        )["Close"]

        # Drop columns that are entirely NaN (delisted / bad tickers)
        raw = raw.dropna(axis=1, how="all")
        raw = raw.dropna(axis=1, thresh=int(period_days * 0.7))
        raw = raw.dropna()

        if len(raw) < 100 or raw.shape[1] < 3:
            raise ValueError("Not enough valid tickers from yfinance")

        returns = np.log(raw / raw.shift(1)).dropna().values
        asset_names = list(raw.columns)
        meta = _build_meta(asset_names)
        return returns, asset_names, meta
    except Exception:
        return None, None, None


def load_data(
    mode: str = "synthetic",
    n_assets: int = 20,
    n_days: int = 500,
    sector_structure: bool = True,
    seed: int = 42,
) -> tuple[np.ndarray, list[str], dict]:
    """
    Returns (returns, asset_names, meta).
    meta = {name: {sector, color, ticker}}
    mode: 'real' | 'synthetic' | 'sector'
    """
    if mode == "real":
        all_tickers = [t for tickers in ASSET_UNIVERSE.values() for t in tickers]
        returns, names, meta = load_real_data(all_tickers[:n_assets])
        if returns is not None:
            return returns, names, meta
        # Fall through to synthetic

    if sector_structure or mode == "sector":
        return _synthetic_sector(n_assets, n_days, seed)
    else:
        return _synthetic_random(n_assets, n_days, seed)


# ---------------------------------------------------------------------------
# Synthetic generators
# ---------------------------------------------------------------------------

def _synthetic_sector(n_assets: int, n_days: int, seed: int):
    rng = np.random.default_rng(seed)
    sectors = list(ASSET_UNIVERSE.keys())
    per_sector = max(1, n_assets // len(sectors))
    remainder = n_assets - per_sector * len(sectors)

    meta: dict = {}
    asset_names: list[str] = []
    sector_map: list[str] = []

    for i, (sec, tickers) in enumerate(ASSET_UNIVERSE.items()):
        count = per_sector + (1 if i < remainder else 0)
        for j in range(count):
            ticker = tickers[j % len(tickers)]
            name = f"{ticker}" if j == 0 else f"{sec[:3]}{j+1}"
            asset_names.append(name)
            sector_map.append(sec)
            meta[name] = {"sector": sec, "color": SECTOR_COLORS[sec], "ticker": ticker}

    n = len(asset_names)

    # Build block-correlated covariance
    # Global market factor + sector factor + idiosyncratic
    market_factor = rng.normal(0, 1, n_days)
    sector_factors = {sec: rng.normal(0, 1, n_days) for sec in sectors}

    returns = np.zeros((n_days, n))
    for i, (name, sec) in enumerate(zip(asset_names, sector_map)):
        beta_market = rng.uniform(0.4, 1.2)
        beta_sector = rng.uniform(0.3, 0.9)
        idio_vol = rng.uniform(0.005, 0.015)
        returns[:, i] = (
            beta_market * market_factor * 0.01
            + beta_sector * sector_factors[sec] * 0.008
            + rng.normal(0, idio_vol, n_days)
        )

    return returns, asset_names, meta


def _synthetic_random(n_assets: int, n_days: int, seed: int):
    rng = np.random.default_rng(seed)
    asset_names = [f"Asset_{i+1}" for i in range(n_assets)]
    base = rng.normal(0, 1, (n_days, 1))
    returns = base * 0.01 + rng.normal(0, 0.008, (n_days, n_assets))
    meta = {name: {"sector": "Unknown", "color": "#888", "ticker": name} for name in asset_names}
    return returns, asset_names, meta


def _build_meta(asset_names: list[str]) -> dict:
    """Build meta for real tickers by matching to known sectors."""
    reverse = {t: (sec, SECTOR_COLORS[sec]) for sec, tickers in ASSET_UNIVERSE.items() for t in tickers}
    meta = {}
    for name in asset_names:
        sec, col = reverse.get(name, ("Other", "#888"))
        meta[name] = {"sector": sec, "color": col, "ticker": name}
    return meta


# ---------------------------------------------------------------------------
# Rolling statistics
# ---------------------------------------------------------------------------

def rolling_correlation(returns: np.ndarray, window: int = 60) -> list[np.ndarray]:
    """Return list of correlation matrices over rolling windows."""
    n_days, n = returns.shape
    matrices = []
    for t in range(window, n_days):
        chunk = returns[t - window : t]
        matrices.append(np.corrcoef(chunk, rowvar=False))
    return matrices


def compute_var(returns: np.ndarray, confidence: float = 0.95) -> np.ndarray:
    """Value-at-Risk per asset (negative quantile)."""
    return -np.quantile(returns, 1 - confidence, axis=0)


def compute_es(returns: np.ndarray, confidence: float = 0.95) -> np.ndarray:
    """Expected Shortfall (CVaR) per asset."""
    threshold = np.quantile(returns, 1 - confidence, axis=0)
    es = np.array([
        -returns[returns[:, i] <= threshold[i], i].mean()
        for i in range(returns.shape[1])
    ])
    return np.nan_to_num(es, nan=0.0)
