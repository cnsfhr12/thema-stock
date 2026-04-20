"""Theme mapping and clustering module."""

from __future__ import annotations

import json
import logging
from collections import defaultdict

import pandas as pd

LOGGER = logging.getLogger(__name__)


DEFAULT_THEME_MAP = {
    "삼성바이오로직스": ["바이오", "CMO"],
    "셀트리온": ["바이오", "바이오시밀러"],
    "한화에어로스페이스": ["방산", "우주"],
    "현대로템": ["방산", "철도"],
    "에코프로": ["2차전지", "소재"],
    "LG에너지솔루션": ["2차전지", "배터리"],
    "두산에너빌리티": ["원전", "전력"],
    "한전기술": ["원전", "전력"],
    "NAVER": ["AI", "플랫폼"],
    "카카오": ["AI", "플랫폼"],
}


class ThemeMapper:
    """Maps stocks and keywords into theme clusters."""

    def __init__(self, config: dict, stock_to_theme: dict[str, list[str]] | None = None):
        self.config = config
        self.stock_to_theme = stock_to_theme or DEFAULT_THEME_MAP

    def build_clusters(self, keyword_stats: dict, anomalies_df: pd.DataFrame) -> dict[str, dict]:
        """Create theme clusters by linking keywords and anomaly stocks.

        Args:
            keyword_stats: Output from NewsCrawler.extract_keyword_stats.
            anomalies_df: Output from VolumeDetector.detect.

        Returns:
            Theme cluster dictionary.
        """
        theme_clusters: dict[str, dict] = defaultdict(lambda: {
            "stocks": set(),
            "keywords": set(),
            "news_growth": [],
            "volume_spikes": [],
            "returns_5d": [],
            "policy_disclosure": 0,
            "community_growth": 0,
            "active": False,
        })

        for stock_name, themes in self.stock_to_theme.items():
            for theme in themes:
                theme_clusters[theme]["stocks"].add(stock_name)

        if not anomalies_df.empty:
            for row in anomalies_df.itertuples(index=False):
                mapped = self.stock_to_theme.get(row.name, [])
                for theme in mapped:
                    theme_clusters[theme]["stocks"].add(row.name)
                    theme_clusters[theme]["volume_spikes"].append(float(row.volume_ratio))
                    theme_clusters[theme]["returns_5d"].append(float(row.return_5d))

        for keyword, stat in keyword_stats.items():
            mentioned_stocks = stat.get("related_stocks", [])
            for stock_name in mentioned_stocks:
                themes = self.stock_to_theme.get(stock_name, [])
                for theme in themes:
                    theme_clusters[theme]["keywords"].add(keyword)
                    theme_clusters[theme]["news_growth"].append(float(stat.get("growth_rate", 0)))

            for theme in theme_clusters.keys():
                if theme in keyword:
                    theme_clusters[theme]["keywords"].add(keyword)
                    theme_clusters[theme]["news_growth"].append(float(stat.get("growth_rate", 0)))

        min_count = self.config["thresholds"]["theme_activation_min_stocks"]
        for theme, cluster in theme_clusters.items():
            cluster["active"] = len(cluster["stocks"]) >= min_count
            cluster["stocks"] = sorted(cluster["stocks"])
            cluster["keywords"] = sorted(cluster["keywords"])

        return dict(theme_clusters)

    @staticmethod
    def to_json(theme_clusters: dict[str, dict]) -> str:
        """Serialize clusters for logging/reporting."""
        return json.dumps(theme_clusters, ensure_ascii=False, default=list, indent=2)
