"""Volume and price anomaly detection module."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from pykrx import stock

from .utils import db_connection

LOGGER = logging.getLogger(__name__)


@dataclass
class StockAnomaly:
    """Data structure for anomaly output."""

    ticker: str
    name: str
    volume_ratio: float
    return_5d: float
    market_cap: float
    anomaly_score: float


class VolumeDetector:
    """Detects stocks with abnormal turnover and momentum."""

    def __init__(self, config: dict, db_path: str):
        self.config = config
        self.db_path = db_path
        self.th = config["thresholds"]

    def detect(self, market: str = "ALL") -> pd.DataFrame:
        """Run anomaly filters on KOSPI/KOSDAQ stocks.

        Args:
            market: pykrx market argument, default ALL.

        Returns:
            DataFrame of anomaly candidates.
        """
        today = datetime.today().strftime("%Y%m%d")
        from_30d = (datetime.today() - timedelta(days=40)).strftime("%Y%m%d")

        tickers = stock.get_market_ticker_list(date=today, market=market)
        rows = []
        for ticker in tickers:
            try:
                name = stock.get_market_ticker_name(ticker)
                ohlcv = stock.get_market_ohlcv_by_date(from_30d, today, ticker)
                if len(ohlcv) < 20:
                    continue

                volume = ohlcv["거래량"].astype(float)
                close = ohlcv["종가"].astype(float)
                avg20 = volume.iloc[-20:].mean()
                if avg20 <= 0:
                    continue
                volume_ratio = volume.iloc[-1] / avg20
                return_5d = (close.iloc[-1] / close.iloc[-6]) - 1 if len(close) >= 6 else 0

                cap_df = stock.get_market_cap_by_ticker(today)
                mcap = float(cap_df.loc[ticker, "시가총액"]) if ticker in cap_df.index else 0

                if not self._passes_filters(volume_ratio, return_5d, mcap):
                    continue

                score = self._score(volume_ratio, return_5d, mcap)
                rows.append(
                    {
                        "ticker": ticker,
                        "name": name,
                        "volume_ratio": round(volume_ratio, 2),
                        "return_5d": round(return_5d, 4),
                        "market_cap": mcap,
                        "anomaly_score": round(score, 2),
                    }
                )
            except Exception:
                LOGGER.exception("Failed processing ticker=%s", ticker)

        df = pd.DataFrame(rows).sort_values("anomaly_score", ascending=False) if rows else pd.DataFrame(columns=["ticker", "name", "volume_ratio", "return_5d", "market_cap", "anomaly_score"])
        self._save(df)
        return df

    def _passes_filters(self, volume_ratio: float, return_5d: float, market_cap: float) -> bool:
        """Apply required threshold filters."""
        return (
            volume_ratio >= self.th["volume_spike_ratio"]
            and return_5d >= self.th["price_rise_5d"]
            and self.th["market_cap_min"] <= market_cap <= self.th["market_cap_max"]
        )

    def _score(self, volume_ratio: float, return_5d: float, market_cap: float) -> float:
        """Compute anomaly score using normalized weighted factors."""
        vol_score = min(volume_ratio / 5, 1.0) * 50
        ret_score = min(return_5d / 0.3, 1.0) * 40
        size_score = 10 * (1 - abs(np.log10(max(market_cap, 1)) - 11.5) / 2)
        return max(vol_score + ret_score + size_score, 0)

    def _save(self, df: pd.DataFrame) -> None:
        """Persist anomaly snapshot."""
        if df.empty:
            return
        snapshot = datetime.utcnow().date().isoformat()
        records = [
            (
                snapshot,
                row.ticker,
                row.name,
                float(row.volume_ratio),
                float(row.return_5d),
                float(row.market_cap),
                float(row.anomaly_score),
            )
            for row in df.itertuples(index=False)
        ]
        with db_connection(self.db_path) as conn:
            conn.executemany(
                """
                INSERT INTO stock_anomalies (
                    snapshot_date, ticker, name, volume_ratio, return_5d, market_cap, anomaly_score
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                records,
            )
