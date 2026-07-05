import asyncio
import calendar
import logging
from datetime import date, datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram.ext import Application

import storage
from ai_client import AssistantClient
from prayer import format_prayer_times, get_prayer_times
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
    daily_summary_hour: int = 22,
    daily_summary_minute: int = 30,
    weekly_summary_dow: str = "sun",
    weekly_summary_hour: int = 22,
    weekly_summary_minute: int = 45,
    monthly_summary_day: int = 1,
    monthly_summary_hour: int = 9,
    monthly_summary_minute: int = 30,
) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=timezone)
    application.bot_data.setdefault("awaiting_plan", set())

    async def send_digest():
        try:
            tasks_rows = storage.get_open_tasks(owner_chat_id)
            settings = storage.get_settings(owner_chat_id)
            tasks = [
                desc + (f" (muddat: {due})" if due else "")
                for _, desc, due in tasks_rows
            ]
            weather_summary, prayer_times = await asyncio.gather(
                get_weather_summary(latitude, longitude),
                get_prayer_times(latitude, longitude, date.today()),
            )
            digest = await claude.compose_digest(weather_summary, tasks, settings=settings)
            digest = f"{digest}\n\n{format_prayer_times(prayer_times)}"
            await application.bot.send_message(chat_id=owner_chat_id, text=digest)
        except Exception:
            logger.exception("Failed to send daily digest")

    PRAYER_NAMES = ["Bomdod", "Peshin", "Asr", "Shom", "Xufton"]

    async def send_prayer_reminder(prayer_name: str):
        try:
            tasks = [desc for _, desc, _ in storage.get_open_tasks(owner_chat_id)]
            settings = storage.get_settings(owner_chat_id)
            parts = [f"🕋 {prayer_name} namozi vaqti keldi!"]
            if tasks:
                parts.append(await claude.compose_reminder(tasks, settings=settings))
            await application.bot.send_message(chat_id=owner_chat_id, text="\n\n".join(parts))
        except Exception:
            logger.exception("Failed to send prayer reminder for %s", prayer_name)

    async def schedule_today_prayer_reminders():
        try:
            prayer_times = await get_prayer_times(latitude, longitude, date.today())
            now = datetime.now(scheduler.timezone)
            for prayer_name in PRAYER_NAMES:
                time_str = prayer_times.get(prayer_name)
                if not time_str:
                    continue
                h, m = map(int, time_str.split(":"))
                run_date = now.replace(hour=h, minute=m, second=0, microsecond=0)
                if run_date <= now:
                    continue
                scheduler.add_job(
                    send_prayer_reminder,
                    "date",
                    run_date=run_date,
                    args=[prayer_name],
                )
                logger.info("Scheduled %s reminder at %s", prayer_name, run_date.strftime("%H:%M"))
        except Exception:
            logger.exception("Failed to schedule today's prayer reminders")

    async def send_planning_prompt():
        try:
            settings = storage.get_settings(owner_chat_id)
            prompt_text = await claude.compose_planning_prompt(settings=settings)
            application.bot_data["awaiting_plan"].add(owner_chat_id)
            await application.bot.send_message(chat_id=owner_chat_id, text=prompt_text)
        except Exception:
            logger.exception("Failed to send sunset planning prompt")

    async def send_daily_summary():
        try:
            today = date.today().isoformat()
            completed_rows = storage.get_completed_tasks_between(owner_chat_id, today, today)
            completed = [desc for desc, _, _ in completed_rows]
            planned_count = storage.count_planned_tasks_between(owner_chat_id, today, today)
            settings = storage.get_settings(owner_chat_id)
            summary = await claude.compose_daily_summary(completed, planned_count, settings=settings)
            await application.bot.send_message(chat_id=owner_chat_id, text=summary)
        except Exception:
            logger.exception("Failed to send daily summary")

    async def send_weekly_analytics():
        try:
            today = date.today()
            week_start = (today - timedelta(days=6)).isoformat()
            week_end = today.isoformat()
            completed_rows = storage.get_completed_tasks_between(owner_chat_id, week_start, week_end)
            planned_count = storage.count_planned_tasks_between(owner_chat_id, week_start, week_end)
            settings = storage.get_settings(owner_chat_id)
            analytics = await claude.compose_period_analytics(
                "Shu hafta", len(completed_rows), planned_count, settings=settings
            )
            await application.bot.send_message(chat_id=owner_chat_id, text=analytics)
        except Exception:
            logger.exception("Failed to send weekly analytics")

    async def send_monthly_analytics():
        try:
            today = date.today()
            last_day_prev_month = today.replace(day=1) - timedelta(days=1)
            month_start = last_day_prev_month.replace(day=1).isoformat()
            month_end = last_day_prev_month.isoformat()
            month_label = calendar.month_name[last_day_prev_month.month]
            completed_rows = storage.get_completed_tasks_between(owner_chat_id, month_start, month_end)
            planned_count = storage.count_planned_tasks_between(owner_chat_id, month_start, month_end)
            settings = storage.get_settings(owner_chat_id)
            analytics = await claude.compose_period_analytics(
                f"{month_label} oyi", len(completed_rows), planned_count, settings=settings
            )
            await application.bot.send_message(chat_id=owner_chat_id, text=analytics)
        except Exception:
            logger.exception("Failed to send monthly analytics")

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
    scheduler.add_job(schedule_today_prayer_reminders, CronTrigger(hour=0, minute=1))
    scheduler.add_job(schedule_today_sunset_prompt, CronTrigger(hour=0, minute=5))
    scheduler.add_job(send_daily_summary, CronTrigger(hour=daily_summary_hour, minute=daily_summary_minute))
    scheduler.add_job(
        send_weekly_analytics,
        CronTrigger(day_of_week=weekly_summary_dow, hour=weekly_summary_hour, minute=weekly_summary_minute),
    )
    scheduler.add_job(
        send_monthly_analytics,
        CronTrigger(day=monthly_summary_day, hour=monthly_summary_hour, minute=monthly_summary_minute),
    )
    scheduler.start()
    startup = datetime.now(scheduler.timezone) + timedelta(seconds=5)
    scheduler.add_job(schedule_today_prayer_reminders, "date", run_date=startup)
    scheduler.add_job(schedule_today_sunset_prompt, "date", run_date=startup + timedelta(seconds=2))
    return scheduler
