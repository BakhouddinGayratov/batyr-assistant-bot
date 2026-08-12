# Batyr Assistant Bot

Telegram bot powered by OpenRouter's free models. It tries three free models in order (`openai/gpt-oss-20b:free`, `google/gemma-4-31b-it:free`, `nvidia/nemotron-3-ultra-550b-a55b:free`) and automatically falls back to the next one if a model is rate-limited or unavailable. v1 features:
- 1-on-1 chat with the assistant (remembers recent conversation)
- Plain-language task capture ("eslab qol: ertaga 14:00 trening")
- `/tasks` — list open tasks
- Daily morning digest (weather + open tasks) sent automatically

Deferred to v2: Google Calendar sync, group-chat tracking.

## 1. Get a Telegram bot token
1. Open Telegram, search for `@BotFather`.
2. Send `/newbot`, follow the prompts (pick a name and a username ending in `bot`).
3. Copy the token it gives you (looks like `123456:ABC-DEF...`).

## 2. Get a free OpenRouter API key
1. Go to https://openrouter.ai/settings/keys
2. Sign in (free, no credit card required), create an API key, copy it.
3. The bot tries three free models in order (`openai/gpt-oss-20b:free`, `google/gemma-4-31b-it:free`, `nvidia/nemotron-3-ultra-550b-a55b:free`) and falls back automatically if one is rate-limited or down — no cost. To see the current free models: `curl https://openrouter.ai/api/v1/models | grep '"prompt": "0"'`.
4. Optional: keep a Groq API key (https://console.groq.com/keys) as `GROQ_API_KEY` if you want **voice messages** — OpenRouter doesn't offer audio transcription, so the bot uses Groq's free Whisper for that.

## 3. Get a free persistent database (Turso)
Render's free tier wipes the local filesystem on every deploy/restart, so the SQLite file alone won't survive. Turso gives a free, no-card-required cloud SQLite database that the bot syncs to.
1. Go to https://turso.tech, sign up (free, no credit card).
2. Install the Turso CLI or use the dashboard to create a database, e.g. `turso db create batyr-bot`.
3. Get the URL: `turso db show batyr-bot --url` (looks like `libsql://batyr-bot-yourname.turso.io`).
4. Get a token: `turso db tokens create batyr-bot`.
5. Put both into `.env` as `TURSO_DATABASE_URL` and `TURSO_AUTH_TOKEN` (and into Render's environment variables when deploying).

If you skip this, the bot still works locally using a plain local SQLite file — only needed for persistence on Render.

## 4. Configure
1. Copy `.env.example` to `.env`.
2. Fill in `TELEGRAM_BOT_TOKEN`, `OPENROUTER_API_KEY`, `TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN`.
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
3. Set secrets: `fly secrets set TELEGRAM_BOT_TOKEN=... OPENROUTER_API_KEY=... OWNER_CHAT_ID=...`
4. `fly deploy`.

Alternative: Railway works the same way (push this repo, set the same env vars in the dashboard, it auto-detects the `Procfile`) — note Railway no longer has a permanent free tier, only trial credit.
