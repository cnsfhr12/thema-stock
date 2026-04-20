"""News crawling and keyword surge detection module."""

from __future__ import annotations

import logging
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Any

import feedparser
import pandas as pd
import requests
from bs4 import BeautifulSoup
from konlpy.tag import Okt
from sklearn.feature_extraction.text import TfidfVectorizer

from .utils import db_connection, now_iso, sleep_with_jitter

LOGGER = logging.getLogger(__name__)
STOPWORDS = {
    "시장",
    "증시",
    "관련",
    "기자",
    "투자",
    "상승",
    "하락",
    "오늘",
    "한국",
    "기업",
}


class NewsCrawler:
    """Collects finance news and computes keyword-level surge metrics."""

    def __init__(self, config: dict, db_path: str):
        self.config = config
        self.db_path = db_path
        self.okt = Okt()

    def fetch_recent_news(self, lookback_hours: int | None = None) -> pd.DataFrame:
        """Fetch recent news from RSS feeds.

        Args:
            lookback_hours: Hours to look back from now. Uses config if None.

        Returns:
            DataFrame with columns [source, title, link, published_at, fetched_at].
        """
        feeds = self.config["sources"]["news_rss"]
        lookback_hours = lookback_hours or self.config["app"]["lookback_hours"]
        since = datetime.utcnow() - timedelta(hours=lookback_hours)
        rows: list[dict[str, Any]] = []

        for feed_url in feeds:
            try:
                sleep_with_jitter(self.config["app"]["request_delay_sec"])
                parsed = feedparser.parse(feed_url)
                for entry in parsed.entries:
                    published_dt = self._parse_published(entry)
                    if published_dt and published_dt < since:
                        continue
                    rows.append(
                        {
                            "source": feed_url,
                            "title": BeautifulSoup(entry.get("title", ""), "html.parser").get_text(strip=True),
                            "link": entry.get("link", ""),
                            "published_at": (published_dt.isoformat() if published_dt else now_iso()),
                            "fetched_at": now_iso(),
                        }
                    )
            except Exception as exc:
                LOGGER.exception("Feed fetch failed: %s", feed_url)
                LOGGER.debug("Error detail: %s", exc)

        df = pd.DataFrame(rows).drop_duplicates(subset=["link"]) if rows else pd.DataFrame(columns=["source", "title", "link", "published_at", "fetched_at"])
        self._save_news(df)
        return df

    def extract_keyword_stats(self, news_df: pd.DataFrame) -> dict:
        """Extract keyword frequencies and detect day-over-day surge.

        Args:
            news_df: News DataFrame.

        Returns:
            Mapping {keyword: {mentions, related_stocks, growth_rate}}.
        """
        if news_df.empty:
            return {}

        titles = news_df["title"].fillna("").tolist()
        tokenized_docs = [self._extract_nouns(t) for t in titles]

        counter = Counter()
        for doc in tokenized_docs:
            counter.update(doc)

        tfidf = TfidfVectorizer(tokenizer=lambda x: x, preprocessor=lambda x: x, token_pattern=None)
        tfidf_matrix = tfidf.fit_transform(tokenized_docs)
        tfidf_means = tfidf_matrix.mean(axis=0).A1
        tfidf_dict = dict(zip(tfidf.get_feature_names_out(), tfidf_means))

        prev_mentions = self._load_previous_mentions()
        keyword_to_stocks = self._heuristic_stock_mapping(news_df)

        stats = {}
        snapshot_date = datetime.utcnow().date().isoformat()
        records = []
        for kw, mentions in counter.items():
            base = prev_mentions.get(kw, 1)
            growth = ((mentions - base) / base) * 100
            weighted_mentions = mentions + tfidf_dict.get(kw, 0)
            stats[kw] = {
                "mentions": int(round(weighted_mentions)),
                "related_stocks": sorted(keyword_to_stocks.get(kw, [])),
                "growth_rate": round(growth, 2),
            }
            records.append((snapshot_date, kw, int(round(weighted_mentions)), float(growth)))

        self._save_keyword_stats(records)
        return stats

    def _parse_published(self, entry: Any) -> datetime | None:
        """Parse published timestamp from feed entry."""
        if "published_parsed" in entry and entry.published_parsed:
            return datetime(*entry.published_parsed[:6])
        if "updated_parsed" in entry and entry.updated_parsed:
            return datetime(*entry.updated_parsed[:6])
        return None

    def _extract_nouns(self, text: str) -> list[str]:
        """Extract meaningful Korean nouns from text."""
        cleaned = re.sub(r"[^0-9A-Za-z가-힣\s]", " ", text)
        nouns = self.okt.nouns(cleaned)
        return [n for n in nouns if len(n) >= 2 and n not in STOPWORDS]

    def _heuristic_stock_mapping(self, news_df: pd.DataFrame) -> dict[str, set[str]]:
        """Simple heuristic mapping of keyword to stock-like terms in titles."""
        keyword_map: dict[str, set[str]] = defaultdict(set)
        pattern = re.compile(r"[A-Za-z가-힣]{2,15}")
        for title in news_df["title"].fillna(""):
            terms = pattern.findall(title)
            nouns = self._extract_nouns(title)
            stocks_like = [t for t in terms if t.endswith(("전자", "바이오", "화학", "로직스", "스페이스", "홀딩스", "금융"))]
            for n in nouns:
                for s in stocks_like:
                    keyword_map[n].add(s)
        return keyword_map

    def _save_news(self, df: pd.DataFrame) -> None:
        """Persist news items into SQLite."""
        if df.empty:
            return
        with db_connection(self.db_path) as conn:
            cur = conn.cursor()
            for _, row in df.iterrows():
                cur.execute(
                    """
                    INSERT OR IGNORE INTO news_items (source, title, link, published_at, fetched_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (row["source"], row["title"], row["link"], row["published_at"], row["fetched_at"]),
                )

    def _save_keyword_stats(self, records: list[tuple]) -> None:
        """Persist keyword stats snapshot into SQLite."""
        if not records:
            return
        with db_connection(self.db_path) as conn:
            conn.executemany(
                """
                INSERT INTO keyword_stats (snapshot_date, keyword, mentions, growth_rate)
                VALUES (?, ?, ?, ?)
                """,
                records,
            )

    def _load_previous_mentions(self) -> dict[str, int]:
        """Load previous day keyword mentions from DB."""
        yesterday = (datetime.utcnow().date() - timedelta(days=1)).isoformat()
        with db_connection(self.db_path) as conn:
            query = "SELECT keyword, SUM(mentions) FROM keyword_stats WHERE snapshot_date = ? GROUP BY keyword"
            rows = conn.execute(query, (yesterday,)).fetchall()
        return {kw: mentions for kw, mentions in rows}


def fetch_disclosures(config: dict) -> list[dict[str, str]]:
    """Fetch DART disclosure list for policy/disclosure relevance scoring.

    Args:
        config: Application configuration.

    Returns:
        List of disclosure records.
    """
    endpoint = config["sources"]["dart_endpoint"]
    api_key = requests.utils.unquote(requests.utils.quote_plus(__import__("os").getenv("DART_API_KEY", "")))
    if not api_key:
        LOGGER.warning("DART_API_KEY not provided; disclosures skipped.")
        return []

    params = {
        "crtfc_key": api_key,
        "bgn_de": (datetime.utcnow().date() - timedelta(days=2)).strftime("%Y%m%d"),
        "end_de": datetime.utcnow().date().strftime("%Y%m%d"),
        "page_no": 1,
        "page_count": 100,
    }
    try:
        resp = requests.get(endpoint, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return data.get("list", [])
    except Exception:
        LOGGER.exception("Failed to fetch DART disclosures.")
        return []
