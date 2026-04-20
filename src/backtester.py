"""Simple historical backtest for detected themes."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

import pandas as pd
from pykrx import stock

LOGGER = logging.getLogger(__name__)


class Backtester:
    """Compares detected themes against forward returns."""

    def __init__(self, config: dict):
        self.config = config

    def evaluate(self, scored_df: pd.DataFrame, detection_date: str) -> pd.DataFrame:
        """Evaluate forward returns after detection date.

        Args:
            scored_df: Theme scoring output with stock list.
            detection_date: Date string (YYYY-MM-DD).

        Returns:
            Theme-level forward return evaluation.
        """
        if scored_df.empty:
            return pd.DataFrame(columns=["theme", "forward_return_mean", "num_stocks"])

        d = datetime.strptime(detection_date, "%Y-%m-%d")
        start = d.strftime("%Y%m%d")
        end = (d + timedelta(days=self.config["backtest"]["forward_days"] + 3)).strftime("%Y%m%d")

        rows = []
        for row in scored_df.itertuples(index=False):
            stock_names = row.stocks if isinstance(row.stocks, list) else []
            rets = []
            for name in stock_names:
                ticker = self._name_to_ticker(name, start)
                if not ticker:
                    continue
                try:
                    ohlcv = stock.get_market_ohlcv_by_date(start, end, ticker)
                    if len(ohlcv) < 2:
                        continue
                    ret = (ohlcv["종가"].iloc[-1] / ohlcv["종가"].iloc[0]) - 1
                    rets.append(float(ret))
                except Exception:
                    LOGGER.exception("Backtest failed for %s", name)
            rows.append(
                {
                    "theme": row.theme,
                    "forward_return_mean": round(sum(rets) / len(rets), 4) if rets else 0,
                    "num_stocks": len(rets),
                }
            )

        return pd.DataFrame(rows).sort_values("forward_return_mean", ascending=False)

    def _name_to_ticker(self, name: str, date: str) -> str | None:
        """Resolve stock name to ticker using pykrx market lists."""
        for market in ["KOSPI", "KOSDAQ"]:
            for ticker in stock.get_market_ticker_list(date=date, market=market):
                if stock.get_market_ticker_name(ticker) == name:
                    return ticker
        return None
