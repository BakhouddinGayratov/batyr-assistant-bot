import base64
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

logger = logging.getLogger(__name__)

BOT_COMMANDS = [
    BotCommand("start", "Botni ishga tushirish"),
    BotCommand("help", "Buyruqlar ro'yxati"),
    BotCommand("menu", "Asosiy menyu"),
    BotCommand("tasks", "Ochiq vazifalarni ko'rish"),
    BotCommand("done", "Vazifani bajarildi deb belgilash"),
    BotCommand("rate", "Valyuta kursini bilish"),
    BotCommand("plan", "Ertaga/kelajak uchun vazifa(lar) qo'shish"),
    BotCommand("settings", "Yordamchini sozlash (ism, ohang, til)"),
    BotCommand("forget", "Men haqimda eslab qolgan ma'lumotlarni o'chirish"),
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
    "💱 /rate USD UZS — valyuta kursi\n"
    "🎯 /plan <matn> — ertaga/kelajak uchun vazifa(lar) qo'shish\n"
    "🌅 Har kuni quyosh botganda ertangi/kelajakdagi ishlar haqida so'rayman\n"
    "🎙 Ovozli xabar yuboring — tushunaman va javob beraman\n"
    "🖼 Rasm yuboring (hujjat, kvitansiya va h.k.) — o'qib/tushuntirib beraman\n"
    "🌤 Har kuni ertalab ob-havo, namaz vaqtlari va vazifalar bilan digest yuboraman\n"
    "🕋 Har soat namaz/nafl vaqtlari haqida eslatib turaman\n"
    "⚙️ /settings — meni o'zingizga moslab sozlash (ism, ohang, til)\n"
    "🧠 Suhbat davomida sizning haqingizda muhim narsalarni eslab qolaman"
)

MENU_KEYBOARD = InlineKeyboardMarkup(
    [
        [InlineKeyboardButton("📋 Vazifalar", callback_data="menu:tasks")],
        [InlineKeyboardButton("💱 Valyuta kursi", callback_data="menu:rate")],
        [InlineKeyboardButton("ℹ️ Yordam", callback_data="menu:help")],
    ]
)


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
            lines = [f"#{tid}: {desc}" + (f" ({due})" if due else "") for tid, desc, due in tasks]
            await query.message.reply_text("\n".join(lines))
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
    lines = [f"#{tid}: {desc}" + (f" ({due})" if due else "") for tid, desc, due in tasks]
    await update.message.reply_text("\n".join(lines))


async def done_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    args = context.args
    if not args or not args[0].isdigit():
        await update.message.reply_text("Foydalanish: /done <raqam>, masalan /done 3")
        return
    task_id = int(args[0])
    storage.complete_task(chat_id, task_id)
    await update.message.reply_text(f"#{task_id} bajarildi deb belgilandi.")


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


async def _store_tasks_from_text(
    claude: AssistantClient, chat_id: int, text: str, default_due_date: str | None = None
) -> list[dict]:
    tasks = await claude.extract_tasks(text, default_due_date=default_due_date)
    for task in tasks:
        storage.add_task(chat_id, task["description"], task.get("due_at"))
    return tasks


async def plan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    claude: AssistantClient = context.application.bot_data["claude"]
    chat_id = update.effective_chat.id
    text = " ".join(context.args)
    if not text:
        await update.message.reply_text("Foydalanish: /plan <ertaga/kelajakda qilishingiz kerak bo'lgan ish(lar)>")
        return
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    tasks = await _store_tasks_from_text(claude, chat_id, text, default_due_date=tomorrow)
    if not tasks:
        await update.message.reply_text("Vazifa aniqlay olmadim, boshqacha yozib ko'ring.")
        return
    lines = [f"- {t['description']}" + (f" ({t.get('due_at')})" if t.get("due_at") else "") for t in tasks]
    await update.message.reply_text("Saqladim:\n" + "\n".join(lines))


async def process_user_text(claude: AssistantClient, chat_id: int, user_text: str) -> str:
    storage.add_message(chat_id, "user", user_text)

    await _store_tasks_from_text(claude, chat_id, user_text)

    fact = await claude.extract_fact(user_text)
    if fact:
        storage.add_fact(chat_id, fact)

    settings = storage.get_settings(chat_id)
    facts = storage.get_facts(chat_id)
    history = storage.get_recent_messages(chat_id, limit=12)
    reply = await claude.chat_reply(history[:-1], user_text, settings=settings, facts=facts)

    storage.add_message(chat_id, "assistant", reply)
    return reply


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    claude: AssistantClient = context.application.bot_data["claude"]
    chat_id = update.effective_chat.id
    awaiting_plan = context.application.bot_data.setdefault("awaiting_plan", set())

    if chat_id in awaiting_plan:
        awaiting_plan.discard(chat_id)
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        tasks = await _store_tasks_from_text(claude, chat_id, update.message.text, default_due_date=tomorrow)
        if not tasks:
            await update.message.reply_text("Vazifa aniqlay olmadim, boshqacha yozib ko'ring.")
            return
        lines = [f"- {t['description']}" + (f" ({t.get('due_at')})" if t.get("due_at") else "") for t in tasks]
        await update.message.reply_text("Saqladim:\n" + "\n".join(lines))
        return

    reply = await process_user_text(claude, chat_id, update.message.text)
    await update.message.reply_text(reply)


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    claude: AssistantClient = context.application.bot_data["claude"]
    chat_id = update.effective_chat.id

    voice = update.message.voice or update.message.audio
    file = await voice.get_file()
    voice_bytes = await file.download_as_bytearray()

    transcript = await claude.transcribe_audio(voice_bytes)
    reply = await process_user_text(claude, chat_id, transcript)
    await update.message.reply_text(f"🎙 {transcript}\n\n{reply}")


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    claude: AssistantClient = context.application.bot_data["claude"]
    chat_id = update.effective_chat.id
    caption = update.message.caption or ""

    photo = update.message.photo[-1]
    file = await photo.get_file()
    photo_bytes = await file.download_as_bytearray()
    image_base64 = base64.b64encode(photo_bytes).decode("utf-8")

    settings = storage.get_settings(chat_id)
    reply = await claude.describe_image(image_base64, caption, settings=settings)

    storage.add_message(chat_id, "user", caption or "[rasm yubordi]")
    storage.add_message(chat_id, "assistant", reply)
    await update.message.reply_text(reply)


async def _post_init(application: Application):
    await application.bot.set_my_commands(BOT_COMMANDS)


def build_application(token: str, claude: AssistantClient) -> Application:
    application = Application.builder().token(token).post_init(_post_init).build()
    application.bot_data["claude"] = claude

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("menu", menu_command))
    application.add_handler(CommandHandler("tasks", list_tasks))
    application.add_handler(CommandHandler("done", done_task))
    application.add_handler(CommandHandler("rate", rate_command))
    application.add_handler(CommandHandler("plan", plan_command))
    application.add_handler(CommandHandler("settings", settings_command))
    application.add_handler(CommandHandler("forget", forget_command))
    application.add_handler(CallbackQueryHandler(menu_callback, pattern=r"^menu:"))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    return application
