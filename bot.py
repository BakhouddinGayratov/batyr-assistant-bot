import asyncio
import base64
import calendar
import logging
from datetime import date, timedelta

from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import storage
from ai_client import AssistantClient
from currency import get_rate
from prayer import format_prayer_times, get_prayer_times
from scheduler import start_scheduler

logger = logging.getLogger(__name__)

BOT_COMMANDS = [
    BotCommand("start", "Start the bot"),
    BotCommand("help", "List of commands"),
    BotCommand("menu", "Main menu"),
    BotCommand("tasks", "View open tasks"),
    BotCommand("done", "Mark a task as done"),
    BotCommand("delete", "Delete a task"),
    BotCommand("stats", "View stats for today/week/month"),
    BotCommand("namaz", "View today's prayer times (Hanafi)"),
    BotCommand("rate", "Get currency exchange rate"),
    BotCommand("plan", "Add tasks for tomorrow / future"),
    BotCommand("settings", "Configure the assistant"),
    BotCommand("forget", "Clear remembered facts about you"),
    BotCommand("correct", "Point out a mistake to avoid"),
    BotCommand("corrections", "List of noted corrections"),
]

VALID_TONES = {"friendly", "formal", "humorous"}
VALID_VERBOSITY = {"brief", "detailed"}
VALID_EMOJI = {"none", "few", "many"}

SETTINGS_HELP = (
    "Settings:\n"
    "/settings name <name> — change assistant name\n"
    "/settings tone friendly|formal|humorous — conversation tone\n"
    "/settings verbosity brief|detailed — response length\n"
    "/settings emoji none|few|many — emoji usage level\n"
    "/settings nickname <nickname> — how to address you\n"
    "/settings language <language> — e.g. English, Russian, Uzbek\n"
    "/settings show — view current settings"
)

HELP_TEXT = (
    "What I can do:\n\n"
    "💬 Just write — we'll have a conversation\n"
    "📝 Write 'remind me: gym at 14:00 tomorrow' — I'll save it as a task\n"
    "📋 /tasks — view open tasks\n"
    "✅ /done <number> — mark a task as done\n"
    "🗑 /delete <number> — delete a task\n"
    "📊 /stats today|week|month — view completion stats\n"
    "🕋 /namaz — view today's prayer times (Hanafi)\n"
    "💱 /rate USD UZS — currency exchange rate\n"
    "🎯 /plan <text> — add tasks for tomorrow / future\n"
    "🌅 Every day at sunset I'll ask about your plans for tomorrow\n"
    "🎙 Send a voice message — I'll understand and reply\n"
    "🖼 Send a photo (document, receipt, etc.) — I'll read and explain it\n"
    "🌤 Every morning I'll send a digest with weather, prayer times, and tasks\n"
    "🕋 I'll remind you at each prayer time\n"
    "⏰ Hourly task reminders from 3:00 to 23:00\n"
    "⚙️ /settings — customize me (name, tone, language)\n"
    "🧠 I'll remember important things about you during our conversation\n"
    "🛠 /correct <mistake and what to do instead> — point out a mistake"
)

MENU_KEYBOARD = InlineKeyboardMarkup(
    [
        [InlineKeyboardButton("📋 Tasks", callback_data="menu:tasks")],
        [InlineKeyboardButton("💱 Exchange Rate", callback_data="menu:rate")],
        [InlineKeyboardButton("ℹ️ Help", callback_data="menu:help")],
    ]
)


def format_tasks_grouped(tasks: list[tuple]) -> str:
    today = date.today().isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()

    groups: dict[str, list[str]] = {"Today": [], "Tomorrow": [], "Upcoming": [], "No date": []}
    for tid, desc, due in tasks:
        line = f"#{tid}: {desc}"
        if not due:
            groups["No date"].append(line)
        elif due.startswith(today):
            groups["Today"].append(line)
        elif due.startswith(tomorrow):
            groups["Tomorrow"].append(line)
        else:
            groups["Upcoming"].append(f"{line} ({due})")

    sections = []
    for label, lines in groups.items():
        if lines:
            sections.append(f"📌 {label}:\n" + "\n".join(lines))
    return "\n\n".join(sections)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await update.message.reply_text(
        f"Hi! I'm your personal assistant.\nYour chat_id: {chat_id}\n"
        "Add this to OWNER_CHAT_ID in your .env file."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT)


async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Main menu:", reply_markup=MENU_KEYBOARD)


async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id

    if query.data == "menu:tasks":
        tasks = storage.get_open_tasks(chat_id)
        if not tasks:
            await query.message.reply_text("No open tasks.")
        else:
            await query.message.reply_text(format_tasks_grouped(tasks))
    elif query.data == "menu:rate":
        await query.message.reply_text("Type: /rate USD UZS (or other currency codes)")
    elif query.data == "menu:help":
        await query.message.reply_text(HELP_TEXT)


async def list_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    tasks = storage.get_open_tasks(chat_id)
    if not tasks:
        await update.message.reply_text("No open tasks.")
        return
    await update.message.reply_text(format_tasks_grouped(tasks))


async def done_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    args = context.args
    if not args or not args[0].isdigit():
        await update.message.reply_text("Usage: /done <number>, e.g. /done 3")
        return
    task_id = int(args[0])
    storage.complete_task(chat_id, task_id)
    await update.message.reply_text(f"#{task_id} marked as done.")


async def delete_task_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    args = context.args
    if not args or not args[0].isdigit():
        await update.message.reply_text("Usage: /delete <number>, e.g. /delete 3")
        return
    task_id = int(args[0])
    storage.delete_task(chat_id, task_id)
    await update.message.reply_text(f"#{task_id} deleted.")


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    claude: AssistantClient = context.application.bot_data["claude"]
    chat_id = update.effective_chat.id
    period = (context.args[0].lower() if context.args else "today")
    settings = storage.get_settings(chat_id)
    today = date.today()

    if period in ("today", "bugun"):
        start_date = end_date = today.isoformat()
        completed_rows = storage.get_completed_tasks_between(chat_id, start_date, end_date)
        planned = storage.count_planned_tasks_between(chat_id, start_date, end_date)
        text = await claude.compose_daily_summary(
            [desc for desc, _, _ in completed_rows], planned, settings=settings
        )
    elif period in ("week", "hafta"):
        start_date = (today - timedelta(days=6)).isoformat()
        end_date = today.isoformat()
        completed_rows = storage.get_completed_tasks_between(chat_id, start_date, end_date)
        planned = storage.count_planned_tasks_between(chat_id, start_date, end_date)
        text = await claude.compose_period_analytics(
            "Last 7 days", len(completed_rows), planned, settings=settings
        )
    elif period in ("month", "oy"):
        start_date = today.replace(day=1).isoformat()
        end_date = today.isoformat()
        completed_rows = storage.get_completed_tasks_between(chat_id, start_date, end_date)
        planned = storage.count_planned_tasks_between(chat_id, start_date, end_date)
        label = calendar.month_name[today.month]
        text = await claude.compose_period_analytics(
            f"{label} (so far)", len(completed_rows), planned, settings=settings
        )
    else:
        await update.message.reply_text("Usage: /stats today|week|month")
        return

    await update.message.reply_text(text)


async def namaz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    latitude = context.application.bot_data["latitude"]
    longitude = context.application.bot_data["longitude"]
    try:
        times = await get_prayer_times(latitude, longitude, date.today())
        await update.message.reply_text(format_prayer_times(times) + "\n\n(Method: Hanafi)")
    except Exception:
        await update.message.reply_text("Couldn't fetch prayer times, please try again later.")


async def rate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) != 2:
        await update.message.reply_text("Usage: /rate USD UZS")
        return
    base, target = args[0].upper(), args[1].upper()
    try:
        rate = await get_rate(base, target)
        await update.message.reply_text(f"1 {base} = {rate:.2f} {target}")
    except Exception:
        await update.message.reply_text(
            "Couldn't find the rate. Check the currency codes (e.g. USD, EUR, UZS)."
        )


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    args = context.args

    if not args or args[0] == "show":
        settings = storage.get_settings(chat_id)
        lines = [
            f"Name: {settings.get('name', 'Jarvis')}",
            f"Tone: {settings.get('tone', 'friendly')}",
            f"Response length: {settings.get('verbosity', 'brief')}",
            f"Emoji: {settings.get('emoji', 'few')}",
            f"Your nickname: {settings.get('nickname', 'not set')}",
            f"Language: {settings.get('language', 'English')}",
        ]
        await update.message.reply_text("Current settings:\n" + "\n".join(lines) + "\n\n" + SETTINGS_HELP)
        return

    key = args[0].lower()
    value = " ".join(args[1:]).strip()

    if key == "name" and value:
        storage.set_setting(chat_id, "name", value)
        await update.message.reply_text(f"Name set to {value}.")
    elif key == "tone" and value.lower() in VALID_TONES:
        storage.set_setting(chat_id, "tone", value.lower())
        await update.message.reply_text(f"Tone changed to {value}.")
    elif key == "verbosity" and value.lower() in VALID_VERBOSITY:
        storage.set_setting(chat_id, "verbosity", value.lower())
        await update.message.reply_text(f"Response length changed to {value}.")
    elif key == "emoji" and value.lower() in VALID_EMOJI:
        storage.set_setting(chat_id, "emoji", value.lower())
        await update.message.reply_text(f"Emoji level changed to {value}.")
    elif key == "nickname" and value:
        storage.set_setting(chat_id, "nickname", value)
        await update.message.reply_text(f"I'll address you as '{value}' now.")
    elif key == "language" and value:
        storage.set_setting(chat_id, "language", value)
        await update.message.reply_text(f"Language changed to {value}.")
    else:
        await update.message.reply_text(SETTINGS_HELP)


async def forget_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    storage.clear_facts(chat_id)
    await update.message.reply_text("Cleared all remembered facts about you.")


async def correct_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = " ".join(context.args).strip()
    if not text:
        await update.message.reply_text(
            "Usage: /correct <what was wrong and what to do instead>\n"
            "Example: /correct don't be formal, always be casual and simple"
        )
        return
    storage.add_correction(chat_id, text)
    await update.message.reply_text("Got it, I'll keep that in mind.")


async def corrections_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    corrections = storage.get_corrections(chat_id)
    if not corrections:
        await update.message.reply_text("No corrections noted yet.")
        return
    lines = [f"- {c}" for c in corrections]
    await update.message.reply_text("Noted corrections:\n" + "\n".join(lines))


async def _store_tasks_from_text(
    claude: AssistantClient, chat_id: int, text: str, default_due_date: str | None = None
) -> tuple[list[dict], list[dict]]:
    tasks = await claude.extract_tasks(text, default_due_date=default_due_date)
    today_str = date.today().isoformat()
    stored, rejected = [], []
    for task in tasks:
        due = task.get("due_at")
        due_date = due[:10] if due else None
        if due_date and due_date < today_str:
            rejected.append(task)
        else:
            storage.add_task(chat_id, task["description"], due)
            stored.append(task)
    return stored, rejected


def _rejected_tasks_note(rejected: list[dict]) -> str:
    lines = [f"- {t['description']} ({t.get('due_at')})" for t in rejected]
    return (
        "I can only add tasks for today or the future, not past dates:\n"
        + "\n".join(lines)
    )


async def plan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    claude: AssistantClient = context.application.bot_data["claude"]
    chat_id = update.effective_chat.id
    text = " ".join(context.args)
    if not text:
        await update.message.reply_text("Usage: /plan <tasks for tomorrow or future>")
        return
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    stored, rejected = await _store_tasks_from_text(claude, chat_id, text, default_due_date=tomorrow)
    if not stored and not rejected:
        await update.message.reply_text("Couldn't identify a task, try rephrasing.")
        return
    parts = []
    if stored:
        lines = [f"- {t['description']}" + (f" ({t.get('due_at')})" if t.get("due_at") else "") for t in stored]
        parts.append("Saved:\n" + "\n".join(lines))
    if rejected:
        parts.append(_rejected_tasks_note(rejected))
    await update.message.reply_text("\n\n".join(parts))


async def _extract_and_store_background(
    claude: AssistantClient, chat_id: int, user_text: str, send_followup
):
    tasks_result, fact = await asyncio.gather(
        claude.extract_tasks(user_text),
        claude.extract_fact(user_text),
        return_exceptions=True,
    )

    if isinstance(tasks_result, Exception):
        logger.exception("Background task extraction failed", exc_info=tasks_result)
    else:
        today_str = date.today().isoformat()
        rejected = []
        for task in tasks_result:
            due = task.get("due_at")
            due_date = due[:10] if due else None
            if due_date and due_date < today_str:
                rejected.append(task)
            else:
                storage.add_task(chat_id, task["description"], due)
        if rejected and send_followup:
            await send_followup(_rejected_tasks_note(rejected))

    if isinstance(fact, Exception):
        logger.exception("Background fact extraction failed", exc_info=fact)
    elif fact:
        storage.add_fact(chat_id, fact)


async def process_user_text(
    claude: AssistantClient,
    chat_id: int,
    user_text: str,
    history: list[tuple[str, str]],
    send_followup=None,
) -> str:
    settings = storage.get_settings(chat_id)
    facts = storage.get_facts(chat_id)
    corrections = storage.get_corrections(chat_id)

    reply = await claude.chat_reply(
        history, user_text, settings=settings, facts=facts, corrections=corrections
    )

    history.append(("user", user_text))
    history.append(("assistant", reply))
    del history[:-12]

    asyncio.create_task(_extract_and_store_background(claude, chat_id, user_text, send_followup))
    return reply


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    claude: AssistantClient = context.application.bot_data["claude"]
    chat_id = update.effective_chat.id
    awaiting_plan = context.application.bot_data.setdefault("awaiting_plan", set())

    if chat_id in awaiting_plan:
        awaiting_plan.discard(chat_id)
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        stored, rejected = await _store_tasks_from_text(
            claude, chat_id, update.message.text, default_due_date=tomorrow
        )
        if not stored and not rejected:
            await update.message.reply_text("Couldn't identify a task, try rephrasing.")
            return
        parts = []
        if stored:
            lines = [
                f"- {t['description']}" + (f" ({t.get('due_at')})" if t.get("due_at") else "") for t in stored
            ]
            parts.append("Saved:\n" + "\n".join(lines))
        if rejected:
            parts.append(_rejected_tasks_note(rejected))
        await update.message.reply_text("\n\n".join(parts))
        return

    history = context.application.bot_data.setdefault("chat_history", {}).setdefault(chat_id, [])
    try:
        reply = await process_user_text(
            claude, chat_id, update.message.text, history, send_followup=update.message.reply_text
        )
    except Exception:
        logger.exception("Failed to process text message for chat %s", chat_id)
        await update.message.reply_text("Sorry, something went wrong. Please try again.")
        return
    await update.message.reply_text(reply)


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    claude: AssistantClient = context.application.bot_data["claude"]
    chat_id = update.effective_chat.id

    try:
        voice = update.message.voice or update.message.audio
        file = await voice.get_file()
        voice_bytes = await file.download_as_bytearray()

        transcript = await claude.transcribe_audio(voice_bytes)
        history = context.application.bot_data.setdefault("chat_history", {}).setdefault(chat_id, [])
        reply = await process_user_text(
            claude, chat_id, transcript, history, send_followup=update.message.reply_text
        )
    except Exception:
        logger.exception("Failed to process voice message for chat %s", chat_id)
        await update.message.reply_text("Sorry, couldn't process the voice message. Please try again.")
        return
    await update.message.reply_text(f"🎙 {transcript}\n\n{reply}")


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    claude: AssistantClient = context.application.bot_data["claude"]
    chat_id = update.effective_chat.id
    caption = update.message.caption or ""

    try:
        photo = update.message.photo[-1]
        file = await photo.get_file()
        photo_bytes = await file.download_as_bytearray()
        image_base64 = base64.b64encode(photo_bytes).decode("utf-8")

        settings = storage.get_settings(chat_id)
        reply = await claude.describe_image(image_base64, caption, settings=settings)
    except Exception:
        logger.exception("Failed to process photo for chat %s", chat_id)
        await update.message.reply_text("Sorry, couldn't process the photo. Please try again.")
        return
    await update.message.reply_text(reply)


async def _post_init(application: Application):
    await application.bot.set_my_commands(BOT_COMMANDS)
    scheduler_config = application.bot_data.get("scheduler_config")
    if scheduler_config:
        start_scheduler(application, **scheduler_config)


async def _post_shutdown(application: Application):
    claude: AssistantClient | None = application.bot_data.get("claude")
    if claude:
        await claude.aclose()


async def _error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Unhandled exception while processing update %s", update, exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text(
            "Sorry, an unexpected error occurred. Please try again."
        )


def build_application(token: str, claude: AssistantClient) -> Application:
    application = (
        Application.builder().token(token).post_init(_post_init).post_shutdown(_post_shutdown).build()
    )
    application.bot_data["claude"] = claude

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("menu", menu_command))
    application.add_handler(CommandHandler("tasks", list_tasks))
    application.add_handler(CommandHandler("done", done_task))
    application.add_handler(CommandHandler("delete", delete_task_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("namaz", namaz_command))
    application.add_handler(CommandHandler("rate", rate_command))
    application.add_handler(CommandHandler("plan", plan_command))
    application.add_handler(CommandHandler("settings", settings_command))
    application.add_handler(CommandHandler("forget", forget_command))
    application.add_handler(CommandHandler("correct", correct_command))
    application.add_handler(CommandHandler("corrections", corrections_command))
    application.add_handler(CallbackQueryHandler(menu_callback, pattern=r"^menu:"))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_error_handler(_error_handler)

    return application
