"""Shared utility helpers for the theme detection system."""

from __future__ import annotations

import logging
import os
import random
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Generator, Iterable

import yaml
from dotenv import load_dotenv


def load_config(config_path: str = "config.yaml") -> dict:
    """Load YAML configuration from disk.

    Args:
        config_path: Path to YAML config file.

    Returns:
        Parsed config dictionary.
    """
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def setup_logging(config: dict) -> None:
    """Initialize file + console logging based on config.

    Args:
        config: Application configuration dict.
    """
    log_file = Path(config["logging"]["file"])
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=getattr(logging, config["logging"]["level"].upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[logging.FileHandler(log_file, encoding="utf-8"), logging.StreamHandler()],
    )


def load_env() -> None:
    """Load .env file into process environment."""
    load_dotenv(override=False)


def sleep_with_jitter(delay_range: Iterable[float]) -> None:
    """Sleep a random duration between min and max delay.

    Args:
        delay_range: Length-2 iterable containing [min_sec, max_sec].
    """
    low, high = delay_range
    time.sleep(random.uniform(float(low), float(high)))


@contextmanager
def db_connection(db_path: str) -> Generator[sqlite3.Connection, None, None]:
    """Yield SQLite connection and commit safely.

    Args:
        db_path: SQLite DB path.
    """
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: str) -> None:
    """Create required database tables when missing.

    Args:
        db_path: SQLite DB path.
    """
    with db_connection(db_path) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS news_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT,
                title TEXT,
                link TEXT UNIQUE,
                published_at TEXT,
                fetched_at TEXT
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS keyword_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_date TEXT,
                keyword TEXT,
                mentions INTEGER,
                growth_rate REAL
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS stock_anomalies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_date TEXT,
                ticker TEXT,
                name TEXT,
                volume_ratio REAL,
                return_5d REAL,
                market_cap REAL,
                anomaly_score REAL
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS theme_scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_date TEXT,
                theme TEXT,
                score REAL,
                components TEXT,
                stocks TEXT,
                rationale TEXT
            );
            """
        )


def now_iso() -> str:
    """Return current timestamp in ISO format."""
    return datetime.utcnow().isoformat(timespec="seconds")


def getenv_required(key: str) -> str:
    """Get environment variable or raise a clear error.

    Args:
        key: Environment variable name.

    Returns:
        Environment variable value.

    Raises:
        RuntimeError: If variable is not set.
    """
    value = os.getenv(key)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {key}")
    return value
