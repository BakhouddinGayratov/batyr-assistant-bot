import logging
from datetime import date, datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram.ext import Application

import storage
from ai_client import AssistantClient
from prayer import current_period_label, format_prayer_times, get_prayer_times
from weather import get_sunset, get_weather_summary

logger = logging.getLogger(__name__)


def start_scheduler(
    application: Application,
    claude: AssistantClient,
    owner_chat_id: int,
    hour: int,
    minute: int,
    timezone: str,
    latitude: float,
    longitude: float,
    reminder_start_hour: int = 9,
    reminder_end_hour: int = 21,
) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=timezone)
    application.bot_data.setdefault("awaiting_plan", set())

    async def send_digest():
        try:
            weather_summary = await get_weather_summary(latitude, longitude)
            tasks_rows = storage.get_open_tasks(owner_chat_id)
            tasks = [
                desc + (f" (muddat: {due})" if due else "")
                for _, desc, due in tasks_rows
            ]
            digest = await claude.compose_digest(weather_summary, tasks)

            prayer_times = await get_prayer_times(latitude, longitude, date.today())
            digest = f"{digest}\n\n{format_prayer_times(prayer_times)}"

            await application.bot.send_message(chat_id=owner_chat_id, text=digest)
        except Exception:
            logger.exception("Failed to send daily digest")

    async def send_reminder():
        try:
            tasks = [desc for _, desc, _ in storage.get_open_tasks(owner_chat_id)]

            prayer_times = await get_prayer_times(latitude, longitude, date.today())
            now = datetime.now(scheduler.timezone)
            period = current_period_label(prayer_times, now)

            parts = []
            if period:
                parts.append(f"🕋 Hozir {period} payti.")
            if tasks:
                parts.append(await claude.compose_reminder(tasks))

            if not parts:
                return
            await application.bot.send_message(chat_id=owner_chat_id, text="\n\n".join(parts))
        except Exception:
            logger.exception("Failed to send hourly reminder")

    async def send_planning_prompt():
        try:
            prompt_text = await claude.compose_planning_prompt()
            application.bot_data["awaiting_plan"].add(owner_chat_id)
            await application.bot.send_message(chat_id=owner_chat_id, text=prompt_text)
        except Exception:
            logger.exception("Failed to send sunset planning prompt")

    async def schedule_today_sunset_prompt():
        try:
            sunset = await get_sunset(latitude, longitude)
            now = datetime.now(sunset.tzinfo)
            if sunset <= now:
                sunset = sunset + timedelta(days=1)
            scheduler.add_job(send_planning_prompt, "date", run_date=sunset)
        except Exception:
            logger.exception("Failed to schedule sunset planning prompt")

    scheduler.add_job(send_digest, CronTrigger(hour=hour, minute=minute))
    scheduler.add_job(
        send_reminder,
        CronTrigger(hour=f"{reminder_start_hour}-{reminder_end_hour}", minute=0),
    )
    scheduler.add_job(schedule_today_sunset_prompt, CronTrigger(hour=0, minute=5))
    scheduler.start()
    scheduler.add_job(
        schedule_today_sunset_prompt,
        "date",
        run_date=datetime.now(scheduler.timezone) + timedelta(seconds=5),
    )
    return scheduler
