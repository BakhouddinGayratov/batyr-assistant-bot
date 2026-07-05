import logging
import os

from dotenv import load_dotenv

import storage
from bot import build_application
from ai_client import AssistantClient
from healthcheck import start_health_server

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def main():
    storage.init_db()

    port = int(os.environ.get("PORT", 8080))
    start_health_server(port)

    token = os.environ["TELEGRAM_BOT_TOKEN"]
    owner_chat_id = os.environ.get("OWNER_CHAT_ID")
    digest_hour = int(os.environ.get("DIGEST_HOUR", 9))
    digest_minute = int(os.environ.get("DIGEST_MINUTE", 0))
    timezone = os.environ.get("TIMEZONE", "Asia/Tashkent")
    latitude = float(os.environ.get("LATITUDE", 41.2995))
    longitude = float(os.environ.get("LONGITUDE", 69.2401))

    claude = AssistantClient(timezone=timezone)
    application = build_application(token, claude)
    application.bot_data["latitude"] = latitude
    application.bot_data["longitude"] = longitude

    if owner_chat_id:
        application.bot_data["scheduler_config"] = dict(
            claude=claude,
            owner_chat_id=int(owner_chat_id),
            hour=digest_hour,
            minute=digest_minute,
            timezone=timezone,
            latitude=latitude,
            longitude=longitude,
        )
    else:
        logger.warning(
            "OWNER_CHAT_ID is not set yet — daily digest is disabled. "
            "Send /start to the bot to get your chat_id, then add it to .env."
        )

    logger.info("Bot starting (polling)...")
    application.run_polling()


if __name__ == "__main__":
    main()
