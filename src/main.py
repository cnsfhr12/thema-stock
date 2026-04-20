"""Main orchestrator for Korean stock theme detection system."""

from __future__ import annotations

import argparse
import logging
from datetime import datetime

from .alert_reporter import AlertReporter
from .backtester import Backtester
from .news_crawler import NewsCrawler, fetch_disclosures
from .theme_mapper import ThemeMapper
from .theme_scorer import ThemeScorer
from .utils import init_db, load_config, load_env, setup_logging
from .volume_detector import VolumeDetector

LOGGER = logging.getLogger(__name__)


def run_pipeline(config: dict) -> tuple[str, object]:
    """Execute full theme detection pipeline with module-level fault tolerance.

    Args:
        config: Application configuration.

    Returns:
        Tuple of report string and scored DataFrame.
    """
    db_path = config["database"]["path"]
    init_db(db_path)

    keyword_stats = {}
    anomalies = None
    clusters = {}
    scored_df = None

    try:
        crawler = NewsCrawler(config, db_path)
        news_df = crawler.fetch_recent_news()
        keyword_stats = crawler.extract_keyword_stats(news_df)
        disclosures = fetch_disclosures(config)
        LOGGER.info("Fetched %d disclosure items.", len(disclosures))
    except Exception:
        LOGGER.exception("news_crawler module failed; continue with fallback empty output.")

    try:
        detector = VolumeDetector(config, db_path)
        anomalies = detector.detect()
    except Exception:
        LOGGER.exception("volume_detector module failed; continue with fallback empty output.")

    try:
        mapper = ThemeMapper(config)
        clusters = mapper.build_clusters(keyword_stats, anomalies if anomalies is not None else __import__("pandas").DataFrame())
    except Exception:
        LOGGER.exception("theme_mapper module failed; continue with fallback empty output.")

    try:
        scorer = ThemeScorer(config, db_path)
        scored_df = scorer.score_themes(clusters)
    except Exception:
        LOGGER.exception("theme_scorer module failed; continue with fallback empty output.")
        scored_df = __import__("pandas").DataFrame()

    reporter = AlertReporter(config)
    report = reporter.format_report(scored_df)
    print(report)
    try:
        reporter.send_telegram(report)
    except Exception:
        LOGGER.exception("alert_reporter telegram step failed.")

    return report, scored_df


def main() -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description="Korean Theme Detection System")
    parser.add_argument("--run-now", action="store_true", help="Run pipeline immediately once")
    parser.add_argument("--schedule", action="store_true", help="Run with daily scheduler")
    parser.add_argument("--backtest-date", type=str, default="", help="Backtest with YYYY-MM-DD date")
    args = parser.parse_args()

    config = load_config()
    load_env()
    setup_logging(config)

    if args.run_now or not args.schedule:
        _, scored = run_pipeline(config)
        if args.backtest_date:
            backtester = Backtester(config)
            bt_df = backtester.evaluate(scored, args.backtest_date)
            print("\n[백테스트 결과]")
            print(bt_df.to_string(index=False) if not bt_df.empty else "결과 없음")

    if args.schedule:
        reporter = AlertReporter(config)
        reporter.schedule_daily(lambda: run_pipeline(config))


if __name__ == "__main__":
    main()
