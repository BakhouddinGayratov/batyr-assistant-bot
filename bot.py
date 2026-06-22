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

logger = logging.getLogger(__name__)

BOT_COMMANDS = [
    BotCommand("start", "Botni ishga tushirish"),
    BotCommand("help", "Buyruqlar ro'yxati"),
    BotCommand("menu", "Asosiy menyu"),
    BotCommand("tasks", "Ochiq vazifalarni ko'rish"),
    BotCommand("done", "Vazifani bajarildi deb belgilash"),
    BotCommand("delete", "Vazifani butunlay o'chirish"),
    BotCommand("stats", "Bugun/hafta/oy bo'yicha statistikani ko'rish"),
    BotCommand("namaz", "Bugungi namaz vaqtlarini ko'rish (hanafiy)"),
    BotCommand("rate", "Valyuta kursini bilish"),
    BotCommand("plan", "Ertaga/kelajak uchun vazifa(lar) qo'shish"),
    BotCommand("settings", "Yordamchini sozlash (ism, ohang, til)"),
    BotCommand("forget", "Men haqimda eslab qolgan ma'lumotlarni o'chirish"),
    BotCommand("correct", "Xatosini ko'rsatish, bot uni qaytarmaydi"),
    BotCommand("corrections", "Tuzatilgan xatolar ro'yxati"),
]

VALID_TONES = {"samimiy", "rasmiy", "hazil"}
VALID_VERBOSITY = {"qisqa", "batafsil"}
VALID_EMOJI = {"yoq", "oz", "kop"}

SETTINGS_HELP = (
    "Sozlamalar:\n"
    "/settings name <ism> — yordamchi ismini o'zgartirish\n"
    "/settings tone samimiy|rasmiy|hazil — gaplashish ohangi\n"
    "/settings verbosity qisqa|batafsil — javoblar uzunligi\n"
    "/settings emoji yoq|oz|kop — emoji ishlatish darajasi\n"
    "/settings nickname <laqab> — sizni qanday chaqirishini belgilash\n"
    "/settings language <til> — masalan: o'zbek, rus, ingliz\n"
    "/settings show — hozirgi sozlamalarni ko'rish"
)

HELP_TEXT = (
    "Men nimalar qila olaman:\n\n"
    "💬 Oddiy yozing — suhbatlashamiz\n"
    "📝 \"eslab qol: ertaga 14:00 trening\" kabi yozing — vazifa sifatida saqlayman\n"
    "📋 /tasks — ochiq vazifalarni ko'rish\n"
    "✅ /done <raqam> — vazifani bajarildi deb belgilash\n"
    "🗑 /delete <raqam> — vazifani butunlay o'chirish\n"
    "📊 /stats bugun|hafta|oy — bajarish statistikasini ko'rish\n"
    "🕋 /namaz — bugungi namaz vaqtlarini ko'rish (hanafiy hisoblash)\n"
    "💱 /rate USD UZS — valyuta kursi\n"
    "🎯 /plan <matn> — ertaga/kelajak uchun vazifa(lar) qo'shish\n"
    "🌅 Har kuni quyosh botganda ertangi/kelajakdagi ishlar haqida so'rayman\n"
    "🎙 Ovozli xabar yuboring — tushunaman va javob beraman\n"
    "🖼 Rasm yuboring (hujjat, kvitansiya va h.k.) — o'qib/tushuntirib beraman\n"
    "🌤 Har kuni ertalab ob-havo, namaz vaqtlari va vazifalar bilan digest yuboraman\n"
    "🕋 Har soat namaz/nafl vaqtlari haqida eslatib turaman\n"
    "⚙️ /settings — meni o'zingizga moslab sozlash (ism, ohang, til)\n"
    "🧠 Suhbat davomida sizning haqingizda muhim narsalarni eslab qolaman\n"
    "🛠 /correct <xato va to'g'risi> — xatomni ko'rsating, qaytarmayman"
)

MENU_KEYBOARD = InlineKeyboardMarkup(
    [
        [InlineKeyboardButton("📋 Vazifalar", callback_data="menu:tasks")],
        [InlineKeyboardButton("💱 Valyuta kursi", callback_data="menu:rate")],
        [InlineKeyboardButton("ℹ️ Yordam", callback_data="menu:help")],
    ]
)


def format_tasks_grouped(tasks: list[tuple]) -> str:
    today = date.today().isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()

    groups: dict[str, list[str]] = {"Bugun": [], "Ertaga": [], "Kelajakda": [], "Sanasiz": []}
    for tid, desc, due in tasks:
        line = f"#{tid}: {desc}"
        if not due:
            groups["Sanasiz"].append(line)
        elif due.startswith(today):
            groups["Bugun"].append(line)
        elif due.startswith(tomorrow):
            groups["Ertaga"].append(line)
        else:
            groups["Kelajakda"].append(f"{line} ({due})")

    sections = []
    for label, lines in groups.items():
        if lines:
            sections.append(f"📌 {label}:\n" + "\n".join(lines))
    return "\n\n".join(sections)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await update.message.reply_text(
        f"Salom! Men sizning yordamchingizman.\nSizning chat_id: {chat_id}\n"
        "Bu raqamni .env faylidagi OWNER_CHAT_ID ga qo'ying."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT)


async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Asosiy menyu:", reply_markup=MENU_KEYBOARD)


async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id

    if query.data == "menu:tasks":
        tasks = storage.get_open_tasks(chat_id)
        if not tasks:
            await query.message.reply_text("Ochiq vazifalar yo'q.")
        else:
            await query.message.reply_text(format_tasks_grouped(tasks))
    elif query.data == "menu:rate":
        await query.message.reply_text("Yozing: /rate USD UZS (yoki boshqa valyuta kodlari)")
    elif query.data == "menu:help":
        await query.message.reply_text(HELP_TEXT)


async def list_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    tasks = storage.get_open_tasks(chat_id)
    if not tasks:
        await update.message.reply_text("Ochiq vazifalar yo'q.")
        return
    await update.message.reply_text(format_tasks_grouped(tasks))


async def done_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    args = context.args
    if not args or not args[0].isdigit():
        await update.message.reply_text("Foydalanish: /done <raqam>, masalan /done 3")
        return
    task_id = int(args[0])
    storage.complete_task(chat_id, task_id)
    await update.message.reply_text(f"#{task_id} bajarildi deb belgilandi.")


async def delete_task_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    args = context.args
    if not args or not args[0].isdigit():
        await update.message.reply_text("Foydalanish: /delete <raqam>, masalan /delete 3")
        return
    task_id = int(args[0])
    storage.delete_task(chat_id, task_id)
    await update.message.reply_text(f"#{task_id} o'chirildi.")


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    claude: AssistantClient = context.application.bot_data["claude"]
    chat_id = update.effective_chat.id
    period = (context.args[0].lower() if context.args else "bugun")
    settings = storage.get_settings(chat_id)
    today = date.today()

    if period in ("bugun", "today"):
        start = end = today.isoformat()
        completed_rows = storage.get_completed_tasks_between(chat_id, start, end)
        planned = storage.count_planned_tasks_between(chat_id, start, end)
        text = await claude.compose_daily_summary(
            [desc for desc, _, _ in completed_rows], planned, settings=settings
        )
    elif period in ("hafta", "week"):
        start = (today - timedelta(days=6)).isoformat()
        end = today.isoformat()
        completed_rows = storage.get_completed_tasks_between(chat_id, start, end)
        planned = storage.count_planned_tasks_between(chat_id, start, end)
        text = await claude.compose_period_analytics(
            "So'nggi 7 kun", len(completed_rows), planned, settings=settings
        )
    elif period in ("oy", "month"):
        start = today.replace(day=1).isoformat()
        end = today.isoformat()
        completed_rows = storage.get_completed_tasks_between(chat_id, start, end)
        planned = storage.count_planned_tasks_between(chat_id, start, end)
        label = calendar.month_name[today.month]
        text = await claude.compose_period_analytics(
            f"{label} oyi (hozirgacha)", len(completed_rows), planned, settings=settings
        )
    else:
        await update.message.reply_text("Foydalanish: /stats bugun|hafta|oy")
        return

    await update.message.reply_text(text)


async def namaz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    latitude = context.application.bot_data["latitude"]
    longitude = context.application.bot_data["longitude"]
    try:
        times = await get_prayer_times(latitude, longitude, date.today())
        await update.message.reply_text(format_prayer_times(times) + "\n\n(Hisoblash: hanafiy maktab)")
    except Exception:
        await update.message.reply_text("Namaz vaqtlarini olib bo'lmadi, birozdan keyin urinib ko'ring.")


async def rate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) != 2:
        await update.message.reply_text("Foydalanish: /rate USD UZS")
        return
    base, target = args[0].upper(), args[1].upper()
    try:
        rate = await get_rate(base, target)
        await update.message.reply_text(f"1 {base} = {rate:.2f} {target}")
    except Exception:
        await update.message.reply_text(
            "Kursni topib bo'lmadi. Valyuta kodlarini tekshiring (masalan: USD, EUR, UZS)."
        )


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    args = context.args

    if not args or args[0] == "show":
        settings = storage.get_settings(chat_id)
        default_language = "o'zbek"
        lines = [
            f"Ism: {settings.get('name', 'Jarvis')}",
            f"Ohang: {settings.get('tone', 'samimiy')}",
            f"Javob uzunligi: {settings.get('verbosity', 'qisqa')}",
            f"Emoji: {settings.get('emoji', 'oz')}",
            f"Laqabingiz: {settings.get('nickname', 'belgilanmagan')}",
            f"Til: {settings.get('language', default_language)}",
        ]
        await update.message.reply_text("Hozirgi sozlamalar:\n" + "\n".join(lines) + "\n\n" + SETTINGS_HELP)
        return

    key = args[0].lower()
    value = " ".join(args[1:]).strip()

    if key == "name" and value:
        storage.set_setting(chat_id, "name", value)
        await update.message.reply_text(f"Ismimni {value} deb belgiladim.")
    elif key == "tone" and value.lower() in VALID_TONES:
        storage.set_setting(chat_id, "tone", value.lower())
        await update.message.reply_text(f"Ohangni {value} qilib o'zgartirdim.")
    elif key == "verbosity" and value.lower() in VALID_VERBOSITY:
        storage.set_setting(chat_id, "verbosity", value.lower())
        await update.message.reply_text(f"Javob uzunligini {value} qilib o'zgartirdim.")
    elif key == "emoji" and value.lower() in VALID_EMOJI:
        storage.set_setting(chat_id, "emoji", value.lower())
        await update.message.reply_text(f"Emoji darajasini {value} qilib o'zgartirdim.")
    elif key == "nickname" and value:
        storage.set_setting(chat_id, "nickname", value)
        await update.message.reply_text(f"Endi sizni '{value}' deb chaqiraman.")
    elif key == "language" and value:
        storage.set_setting(chat_id, "language", value)
        await update.message.reply_text(f"Tilni {value} qilib o'zgartirdim.")
    else:
        await update.message.reply_text(SETTINGS_HELP)


async def forget_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    storage.clear_facts(chat_id)
    await update.message.reply_text("Siz haqingizda eslab qolgan ma'lumotlarni o'chirdim.")


async def correct_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = " ".join(context.args).strip()
    if not text:
        await update.message.reply_text(
            "Foydalanish: /correct <nima xato edi va o'rniga nima qilishim kerak>\n"
            "Masalan: /correct \"rasmiy gapirma\" demang, har doim samimiy va sodda gapir"
        )
        return
    storage.add_correction(chat_id, text)
    await update.message.reply_text("Tuzatdim, bundan keyin shunga amal qilaman.")


async def corrections_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    corrections = storage.get_corrections(chat_id)
    if not corrections:
        await update.message.reply_text("Hozircha tuzatilgan xatolar yo'q.")
        return
    lines = [f"- {c}" for c in corrections]
    await update.message.reply_text("Tuzatilgan xatolar:\n" + "\n".join(lines))


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
        "O'tmishdagi sanaga vazifa qo'sha olmayman, faqat bugun yoki kelajak uchun reja yozish mumkin:\n"
        + "\n".join(lines)
    )


async def plan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    claude: AssistantClient = context.application.bot_data["claude"]
    chat_id = update.effective_chat.id
    text = " ".join(context.args)
    if not text:
        await update.message.reply_text("Foydalanish: /plan <ertaga/kelajakda qilishingiz kerak bo'lgan ish(lar)>")
        return
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    stored, rejected = await _store_tasks_from_text(claude, chat_id, text, default_due_date=tomorrow)
    if not stored and not rejected:
        await update.message.reply_text("Vazifa aniqlay olmadim, boshqacha yozib ko'ring.")
        return
    parts = []
    if stored:
        lines = [f"- {t['description']}" + (f" ({t.get('due_at')})" if t.get("due_at") else "") for t in stored]
        parts.append("Saqladim:\n" + "\n".join(lines))
    if rejected:
        parts.append(_rejected_tasks_note(rejected))
    await update.message.reply_text("\n\n".join(parts))


async def process_user_text(
    claude: AssistantClient, chat_id: int, user_text: str, history: list[tuple[str, str]]
) -> str:
    settings = storage.get_settings(chat_id)
    facts = storage.get_facts(chat_id)
    corrections = storage.get_corrections(chat_id)

    extracted_tasks, fact, reply = await asyncio.gather(
        claude.extract_tasks(user_text),
        claude.extract_fact(user_text),
        claude.chat_reply(history, user_text, settings=settings, facts=facts, corrections=corrections),
    )

    today_str = date.today().isoformat()
    rejected = []
    for task in extracted_tasks:
        due = task.get("due_at")
        due_date = due[:10] if due else None
        if due_date and due_date < today_str:
            rejected.append(task)
        else:
            storage.add_task(chat_id, task["description"], due)

    if fact:
        storage.add_fact(chat_id, fact)

    if rejected:
        reply = _rejected_tasks_note(rejected) + "\n\n" + reply

    history.append(("user", user_text))
    history.append(("assistant", reply))
    del history[:-12]
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
            await update.message.reply_text("Vazifa aniqlay olmadim, boshqacha yozib ko'ring.")
            return
        parts = []
        if stored:
            lines = [
                f"- {t['description']}" + (f" ({t.get('due_at')})" if t.get("due_at") else "") for t in stored
            ]
            parts.append("Saqladim:\n" + "\n".join(lines))
        if rejected:
            parts.append(_rejected_tasks_note(rejected))
        await update.message.reply_text("\n\n".join(parts))
        return

    history = context.application.bot_data.setdefault("chat_history", {}).setdefault(chat_id, [])
    try:
        reply = await process_user_text(claude, chat_id, update.message.text, history)
    except Exception:
        logger.exception("Failed to process text message for chat %s", chat_id)
        await update.message.reply_text("Uzr, javob berishda xatolik yuz berdi. Birozdan keyin qayta urinib ko'ring.")
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
        reply = await process_user_text(claude, chat_id, transcript, history)
    except Exception:
        logger.exception("Failed to process voice message for chat %s", chat_id)
        await update.message.reply_text("Uzr, ovozli xabarni qayta ishlab bo'lmadi. Birozdan keyin qayta urinib ko'ring.")
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
        await update.message.reply_text("Uzr, rasmni qayta ishlab bo'lmadi. Birozdan keyin qayta urinib ko'ring.")
        return
    await update.message.reply_text(reply)


async def _post_init(application: Application):
    await application.bot.set_my_commands(BOT_COMMANDS)


async def _error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Unhandled exception while processing update %s", update, exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text(
            "Uzr, kutilmagan xatolik yuz berdi. Birozdan keyin qayta urinib ko'ring."
        )


def build_application(token: str, claude: AssistantClient) -> Application:
    application = Application.builder().token(token).post_init(_post_init).build()
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
