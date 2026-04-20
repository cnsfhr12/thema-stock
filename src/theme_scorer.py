"""Theme scoring module."""

from __future__ import annotations

import json
from datetime import datetime

import numpy as np
import pandas as pd

from .utils import db_connection


class ThemeScorer:
    """Computes weighted theme scores (0~100) and extracts Top-N themes."""

    def __init__(self, config: dict, db_path: str):
        self.config = config
        self.db_path = db_path
        self.weights = config["weights"]

    def score_themes(self, clusters: dict[str, dict], top_n: int = 5) -> pd.DataFrame:
        """Score themes with configured component weights.

        Args:
            clusters: Theme clusters from ThemeMapper.
            top_n: Number of top themes to keep.

        Returns:
            Ranked DataFrame.
        """
        rows = []
        for theme, c in clusters.items():
            if not c.get("active", False):
                continue

            news_surge = np.clip(np.mean(c["news_growth"]) / 500, 0, 1) if c["news_growth"] else 0
            vol_count = np.clip(len(c["volume_spikes"]) / 5, 0, 1)
            avg_return = np.clip(np.mean(c["returns_5d"]) / 0.2, 0, 1) if c["returns_5d"] else 0
            policy_rel = np.clip(c.get("policy_disclosure", 0), 0, 1)
            comm_surge = np.clip(c.get("community_growth", 0) / 300, 0, 1)

            total = (
                news_surge * self.weights["news_surge"]
                + vol_count * self.weights["volume_spike_count"]
                + avg_return * self.weights["avg_return_5d"]
                + policy_rel * self.weights["policy_disclosure"]
                + comm_surge * self.weights["community_surge"]
            )

            rows.append(
                {
                    "theme": theme,
                    "score": round(float(total), 2),
                    "stocks": c["stocks"],
                    "news_growth_avg": round(float(np.mean(c["news_growth"])), 2) if c["news_growth"] else 0,
                    "volume_spike_count": len(c["volume_spikes"]),
                    "avg_return_5d": round(float(np.mean(c["returns_5d"])), 4) if c["returns_5d"] else 0,
                    "policy_disclosure": c.get("policy_disclosure", 0),
                    "community_growth": c.get("community_growth", 0),
                }
            )

        df = pd.DataFrame(rows).sort_values("score", ascending=False).head(top_n) if rows else pd.DataFrame(columns=["theme", "score", "stocks"])
        self._save(df)
        return df

    def _save(self, df: pd.DataFrame) -> None:
        """Save theme scores into SQLite."""
        if df.empty:
            return
        snapshot = datetime.utcnow().date().isoformat()
        records = []
        for row in df.itertuples(index=False):
            components = {
                "news_growth_avg": row.news_growth_avg,
                "volume_spike_count": row.volume_spike_count,
                "avg_return_5d": row.avg_return_5d,
                "policy_disclosure": row.policy_disclosure,
                "community_growth": row.community_growth,
            }
            rationale = f"뉴스 급증률 평균 {row.news_growth_avg}%, 거래량 급증 종목 {row.volume_spike_count}개"
            records.append((snapshot, row.theme, float(row.score), json.dumps(components, ensure_ascii=False), json.dumps(row.stocks, ensure_ascii=False), rationale))

        with db_connection(self.db_path) as conn:
            conn.executemany(
                """
                INSERT INTO theme_scores (snapshot_date, theme, score, components, stocks, rationale)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                records,
            )
