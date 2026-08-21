import os
import logging
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram.ext import Application
from bot import GETBot

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    get_bot = GETBot()

    if not get_bot.token:
        logger.error("GET_TELEGRAM_BOT_TOKEN not set!")
        return
    if not get_bot.chat_id:
        logger.error("GET_TELEGRAM_CHAT_ID not set!")
        return

    app = get_bot.build_app()

    async def post_init(application: Application):
        get_bot.bot = application.bot
        scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")
        scheduler.add_job(
            get_bot.scheduled_scan,
            CronTrigger(hour="9,21", minute=0, timezone="Asia/Kolkata"),
            id="scheduled_get_scan",
            name="GET scan daily 9AM & 9PM IST",
        )
        scheduler.start()
        logger.info("Scheduler started: GET scans at 09:00 & 21:00 IST daily.")

        await application.bot.send_message(
            chat_id=get_bot.chat_id,
            text="🚀 <b>GET Jobs Bot is live!</b>\n\n"
                 "Scanning 60+ sources for Graduate Engineer Trainee roles\n"
                 "(IT + Non-IT) across India.\n"
                 "Scheduled: every 12h (09:00 & 21:00 IST).\n\n"
                 "Type /help for commands.",
            parse_mode="HTML",
        )

    app.post_init = post_init
    logger.info("Starting GET bot polling...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
