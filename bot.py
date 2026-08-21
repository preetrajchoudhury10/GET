import os
import json
import logging
import asyncio
from datetime import datetime
from telegram import Update, Bot
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from scraper import GETJobEngine

logger = logging.getLogger(__name__)

# On Railway, mount a volume and set GET_DATA_DIR=/data so seen_jobs.json
# persists across redeploys. Defaults to the project directory locally.
DATA_DIR = os.environ.get("GET_DATA_DIR", os.path.dirname(os.path.abspath(__file__)))
SEEN_FILE = os.path.join(DATA_DIR, "seen_jobs.json")
SOURCES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sources.json")


def load_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default if default is not None else {}


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


class GETBot:
    def __init__(self):
        self.token = os.environ.get("GET_TELEGRAM_BOT_TOKEN", "")
        self.chat_id = os.environ.get("GET_TELEGRAM_CHAT_ID", "")
        self.env = {
            "ADZUNA_APP_ID": os.environ.get("ADZUNA_APP_ID", ""),
            "ADZUNA_APP_KEY": os.environ.get("ADZUNA_APP_KEY", ""),
            "JOOBLE_API_KEY": os.environ.get("JOOBLE_API_KEY", ""),
        }
        self.config = load_json(SOURCES_FILE, {})
        self.seen_data = load_json(SEEN_FILE, {"sent_ids": []})
        self.seen_ids = set(self.seen_data.get("sent_ids", []))
        self.engine = GETJobEngine(self.config, self.env)
        self.is_scanning = False
        self.bot = None

    def save_seen(self):
        self.seen_data["sent_ids"] = list(self.seen_ids)
        save_json(SEEN_FILE, self.seen_data)

    async def send_message(self, text, parse_mode="HTML"):
        if not self.bot:
            self.bot = Bot(token=self.token)
        await self.bot.send_message(
            chat_id=self.chat_id, text=text, parse_mode=parse_mode,
            disable_web_page_preview=True,
        )

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "🤖 <b>GET Jobs Bot</b>\n\n"
            "Scans 60+ sources for Graduate Engineer Trainee roles across India.\n\n"
            "Tags:\n"
            "• <b>GET[IT]</b> — software/IT trainee roles\n"
            "• <b>GET[Non-IT]</b> — mechanical, civil, electrical,\n"
            "  electronics, chemical & other core branches\n\n"
            "Runs daily at 9 AM & 9 PM IST.\n"
            "Type /help for commands.",
            parse_mode="HTML",
        )

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "📋 <b>Available Commands</b>\n\n"
            "/check - Force scan now\n"
            "/export - Download all fetched jobs as CSV\n"
            "/sources - Show source health\n"
            "/status - Last run info\n"
            "/seen - Recently sent jobs\n"
            "/help - This message",
            parse_mode="HTML",
        )

    async def run_full_scan(self, progress_cb=None):
        """Shared scan used by both /check and the scheduler."""
        all_jobs = []
        stats = {}

        def collect(name, detail):
            stats[name] = detail
            if progress_cb:
                progress_cb(name, detail)

        # Reuse engine.run_scan but capture stats locally
        new_jobs = self.engine.run_scan(sent_ids=self.seen_ids, progress_callback=collect)
        all_jobs = self.engine.last_all_jobs
        filtered_count = self.engine.last_stats["matching"]
        return all_jobs, stats, filtered_count, new_jobs

    async def send_new_jobs(self, new_jobs):
        for job in new_jobs:
            try:
                text = self.engine.format_job(job)
                await self.send_message(text)
            except Exception as e:
                logger.error(f"Send error: {e}")
            self.seen_ids.add(job["id"])
            await asyncio.sleep(0.5)
        self.save_seen()

    def build_summary(self, all_jobs, stats, filtered_count, new_jobs):
        now = datetime.now().strftime("%d %b %Y, %I:%M %p")
        it_count = sum(1 for j in new_jobs if j.get("tag") == "GET[IT]")
        nonit_count = sum(1 for j in new_jobs if j.get("tag") == "GET[Non-IT]")
        summary = (
            f"✅ <b>GET Scan Complete</b> — {now}\n\n"
            f"📄 Total fetched: {len(all_jobs)}\n"
            f"🎯 Matching GET roles (India): {filtered_count}\n"
            f"🆕 New jobs sent: {len(new_jobs)} "
            f"(GET[IT]: {it_count} | GET[Non-IT]: {nonit_count})\n\n"
            f"📋 <b>Source Breakdown:</b>\n"
        )
        for name, detail in stats.items():
            if "error" in detail:
                summary += f"  ❌ {name}: error\n"
            else:
                summary += f"  ✅ {name}: {detail.get('total', 0)}\n"
        return summary

    async def cmd_check(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if self.is_scanning:
            await update.message.reply_text("⏳ Scan already in progress...")
            return

        self.is_scanning = True
        status_msg = await update.message.reply_text("🔍 <b>Starting GET scan of 60+ sources...</b>")
        self.bot = context.bot

        try:
            done = {"n": 0}

            def progress(name, detail):
                done["n"] += 1
                if done["n"] % 3 == 0:
                    logger.info(f"Progress {done['n']}/15: {name}")

            all_jobs, stats, filtered_count, new_jobs = await asyncio.to_thread(
                self._sync_scan_wrapper, progress
            )

            await status_msg.edit_text(
                f"🔍 Scan finished. Sending <b>{len(new_jobs)}</b> new GET jobs..."
            )
            await self.send_new_jobs(new_jobs)

            summary = self.build_summary(all_jobs, stats, filtered_count, new_jobs)
            await status_msg.edit_text(summary)

        except Exception as e:
            logger.error(f"Scan error: {e}")
            await status_msg.edit_text(f"❌ Error during scan: {e}")
        finally:
            self.is_scanning = False

    def _sync_scan_wrapper(self, progress):
        new_jobs = self.engine.run_scan(sent_ids=self.seen_ids, progress_callback=progress)
        return (
            self.engine.last_all_jobs,
            self.engine.last_stats["sources"],
            self.engine.last_stats["matching"],
            new_jobs,
        )

    async def scheduled_scan(self):
        if self.is_scanning:
            logger.info("Scan already in progress, skipping scheduled run.")
            return
        self.is_scanning = True
        try:
            logger.info("Starting scheduled GET scan...")
            await self.send_message("🔍 <b>Scheduled GET scan started...</b>")
            all_jobs, stats, filtered_count, new_jobs = await asyncio.to_thread(
                self._sync_scan_wrapper, None
            )
            await self.send_new_jobs(new_jobs)
            summary = self.build_summary(all_jobs, stats, filtered_count, new_jobs)
            await self.send_message(summary)
            logger.info(f"Scheduled scan complete. {len(new_jobs)} new jobs sent.")
        except Exception as e:
            logger.error(f"Scheduled scan error: {e}")
            try:
                await self.send_message(f"❌ Scheduled scan error: {e}")
            except Exception:
                pass
        finally:
            self.is_scanning = False

    async def cmd_sources(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        sources = self.engine.get_sources_status()
        total = sum(len(v.split()) and 1 for v in sources.values())
        lines = [f"📡 <b>GET Job Sources</b>\n"]
        for name, status in sources.items():
            icon = "✅" if ("Active" in status or "companies" in status or "startups" in status or "pages" in status or "portals" in status) else "⚠️"
            lines.append(f"{icon} <b>{name}</b> — {status}")
        lines.append("\n💡 Adzuna & Jooble need API keys for more results.")
        await update.message.reply_text("\n".join(lines), parse_mode="HTML")

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        stats = self.engine.last_stats
        if not stats:
            await update.message.reply_text("No scans yet. Use /check to start.")
            return
        lines = [
            "📊 <b>Last GET Scan Status</b>\n",
            f"🕐 Last run: {self.engine.last_run or 'Never'}",
            f"📄 Total fetched: {stats.get('total_fetched', 0)}",
            f"🎯 Matching GET roles: {stats.get('matching', 0)}",
            f"🆕 New jobs sent: {stats.get('new_jobs', 0)}",
            f"📨 All-time sent: {len(self.seen_ids)}",
        ]
        await update.message.reply_text("\n".join(lines), parse_mode="HTML")

    async def cmd_seen(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.seen_ids:
            await update.message.reply_text("No jobs sent yet.")
            return
        lines = ["📨 <b>Recently Sent GET Jobs</b>\n"]
        for jid in list(self.seen_ids)[-20:]:
            parts = jid.split("|")
            source = parts[0] if parts else "?"
            job_name = parts[-1].split("/")[-1].replace("_", " ") if "/" in parts[-1] else parts[-1]
            lines.append(f"• [{source}] {job_name}")
        if len(self.seen_ids) > 20:
            lines.append(f"\n... and {len(self.seen_ids) - 20} more")
        await update.message.reply_text("\n".join(lines), parse_mode="HTML")

    async def cmd_export(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.engine.last_all_jobs:
            await update.message.reply_text("No scan data yet. Run /check first.")
            return
        await update.message.reply_text("Generating CSV...")
        filepath = self.engine.generate_csv()
        with open(filepath, "rb") as f:
            await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=f,
                filename="get_jobs_export.csv",
                caption="📋 <b>All Fetched GET Jobs</b>\n\n"
                        "Columns: Source, GET Tag, Company, Title, Location, Posted, URL",
                parse_mode="HTML",
            )
        os.remove(filepath)

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("Type /help to see available commands.")

    def build_app(self):
        app = Application.builder().token(self.token).build()
        app.add_handler(CommandHandler("start", self.cmd_start))
        app.add_handler(CommandHandler("help", self.cmd_help))
        app.add_handler(CommandHandler("check", self.cmd_check))
        app.add_handler(CommandHandler("sources", self.cmd_sources))
        app.add_handler(CommandHandler("status", self.cmd_status))
        app.add_handler(CommandHandler("seen", self.cmd_seen))
        app.add_handler(CommandHandler("export", self.cmd_export))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        return app
