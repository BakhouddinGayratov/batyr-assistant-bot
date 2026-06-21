# Batyr Assistant Bot

Telegram bot powered by Groq (free tier, open models like Llama 3.3). v1 features:
- 1-on-1 chat with the assistant (remembers recent conversation)
- Plain-language task capture ("eslab qol: ertaga 14:00 trening")
- `/tasks` — list open tasks
- Daily morning digest (weather + open tasks) sent automatically

Deferred to v2: Google Calendar sync, group-chat tracking.

## 1. Get a Telegram bot token
1. Open Telegram, search for `@BotFather`.
2. Send `/newbot`, follow the prompts (pick a name and a username ending in `bot`).
3. Copy the token it gives you (looks like `123456:ABC-DEF...`).

## 2. Get a free Groq API key
1. Go to https://console.groq.com/keys
2. Sign in (free, no credit card required), create an API key, copy it.
3. Groq's free tier has rate limits but no cost — fine for a personal assistant bot.

## 3. Configure
1. Copy `.env.example` to `.env`.
2. Fill in `TELEGRAM_BOT_TOKEN` and `GROQ_API_KEY`.
3. Leave `OWNER_CHAT_ID` blank for now.

## 4. Run locally
```
pip install -r requirements.txt
python main.py
```
Open Telegram, find your bot, send `/start`. It replies with your `chat_id` — copy that into `.env` as `OWNER_CHAT_ID`, then restart `python main.py`. The daily digest only sends once `OWNER_CHAT_ID` is set.

Try:
- Just chat normally — the assistant replies.
- "eslab qol: ertaga soat 14:00 trening" — bot stores it as a task.
- `/tasks` — lists open tasks.
- To test the digest without waiting until morning, temporarily set `DIGEST_HOUR`/`DIGEST_MINUTE` in `.env` to a minute from now and restart.

## 5. Deploy so it runs 24/7
Recommended free option: **Fly.io** (covers one small always-on VM for free).
1. Install the Fly CLI, `fly auth login`.
2. From this folder: `fly launch` (choose no Postgres needed for v1 — SQLite file is enough).
3. Set secrets: `fly secrets set TELEGRAM_BOT_TOKEN=... GROQ_API_KEY=... OWNER_CHAT_ID=...`
4. `fly deploy`.

Alternative: Railway works the same way (push this repo, set the same env vars in the dashboard, it auto-detects the `Procfile`) — note Railway no longer has a permanent free tier, only trial credit.
