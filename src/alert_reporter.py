"""Alert and reporting module."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

import pandas as pd
from apscheduler.schedulers.blocking import BlockingScheduler
from telegram import Bot

LOGGER = logging.getLogger(__name__)


class AlertReporter:
    """Creates human-readable report and optionally sends Telegram alerts."""

    def __init__(self, config: dict):
        self.config = config
        self.telegram_enabled = config.get("telegram", {}).get("enabled", False)

    def format_report(self, scored_df: pd.DataFrame) -> str:
        """Build report text in requested format."""
        date_text = datetime.now().strftime("%Y-%m-%d")
        lines = [f"[테마 탐지 리포트] {date_text}", ""]

        if scored_df.empty:
            lines.append("활성화된 테마가 없습니다.")
            return "\n".join(lines)

        for rank, row in enumerate(scored_df.itertuples(index=False), start=1):
            stocks = ", ".join(row.stocks[:5]) if isinstance(row.stocks, list) else str(row.stocks)
            lines.extend(
                [
                    f"{rank}위 테마: {row.theme} (종합점수: {row.score}점)",
                    f" - 관련 종목: {stocks}",
                    f" - 부각 이유: 뉴스 키워드 평균 증가율 {row.news_growth_avg}%",
                    f" - 거래량 급증 종목 수: {row.volume_spike_count}개",
                    "",
                ]
            )

        return "\n".join(lines)

    def send_telegram(self, message: str) -> None:
        """Send report via Telegram bot."""
        if not self.telegram_enabled:
            LOGGER.info("Telegram alert disabled in config.")
            return

        import os

        token = os.getenv("TELEGRAM_BOT_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID")
        if not token or not chat_id:
            LOGGER.warning("Telegram credentials missing; skipping telegram send.")
            return

        async def _send() -> None:
            bot = Bot(token=token)
            await bot.send_message(chat_id=chat_id, text=message)

        asyncio.run(_send())

    def schedule_daily(self, task_callable) -> None:
        """Run task daily before market open using APScheduler."""
        scheduler = BlockingScheduler(timezone=self.config["app"]["timezone"])
        scheduler.add_job(
            task_callable,
            "cron",
            hour=self.config["app"]["report_hour"],
            minute=self.config["app"]["report_minute"],
            id="theme_detection_daily",
            replace_existing=True,
        )
        LOGGER.info("Scheduler started for daily run at %02d:%02d", self.config["app"]["report_hour"], self.config["app"]["report_minute"])
        scheduler.start()
