import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_TRANSCRIBE_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
MODEL = "llama-3.3-70b-versatile"
VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"
TRANSCRIBE_MODEL = "whisper-large-v3-turbo"

DEFAULT_NAME = "Jarvis"
DEFAULT_TONE = "friendly"
DEFAULT_VERBOSITY = "brief"
DEFAULT_LANGUAGE = "English"
DEFAULT_EMOJI = "few"

TONE_DESCRIPTIONS = {
    "friendly": "warm, friendly, and casual",
    "formal": "respectful and somewhat formal",
    "humorous": "light-hearted with gentle humor, but still helpful",
}

VERBOSITY_DESCRIPTIONS = {
    "brief": "Keep responses very short and to the point (usually 1-3 sentences).",
    "detailed": "Provide detailed explanations when needed.",
}

EMOJI_DESCRIPTIONS = {
    "none": "Do not use any emojis in responses.",
    "few": "Use emojis sparingly, only when clearly appropriate.",
    "many": "Feel free to use emojis to add warmth and expression.",
}

TIME_OF_DAY_ENERGY = [
    (0, 5, "It's late night — be very calm, brief, and soothing."),
    (5, 11, "It's morning — be energetic and encouraging."),
    (11, 17, "It's midday — be focused and productive."),
    (17, 22, "It's evening — be warm and relaxed."),
    (22, 24, "It's late night — be very calm, brief, and soothing."),
]

NATURAL_LANGUAGE_GUIDE = (
    "Write in natural, conversational language. "
    "Avoid stiff, overly formal, robotic, or translated-sounding phrases. "
    "Be human and approachable."
)

FACT_EXTRACTION_PROMPT = (
    "If the following message contains a long-term personal fact worth remembering "
    "(name, profession, interests, habits, preferences, etc.), "
    "extract it as ONE short sentence. If there is no such fact, reply with exactly 'null'. "
    "Reply with nothing else."
)

TASK_EXTRACTION_PROMPT_TEMPLATE = (
    "Today's date and time: {now}. Analyze the following message.\n\n"
    "ONLY treat it as a task if the user EXPLICITLY and CLEARLY asks you to remember, "
    "save, or note something as a task. Examples of explicit requests: "
    "\"remind me\", \"note this\", \"add a task\", \"don't forget\", \"I need to\", "
    "\"I must not forget\" — there must be a clear instruction or request.\n\n"
    "If the user is just CHATTING or INFORMING about future plans "
    "(e.g. \"I have a meeting on Monday\", \"I'll go to the gym tomorrow\") "
    "— DO NOT treat this as a task — return an empty array.\n\n"
    "If a task is found, return a JSON array, each element: "
    "{{\"description\": \"...\", \"due_at\": \"YYYY-MM-DD HH:MM or YYYY-MM-DD or null\"}}. "
    "Convert relative times like 'tomorrow', 'next Monday' to exact dates based on today. "
    "{default_due_hint}"
    "When in doubt, return an EMPTY array — better to miss a task than to add a false one. "
    "Return ONLY the JSON array, nothing else."
)


class AssistantClient:
    def __init__(self, timezone: str = "Asia/Tashkent"):
        self.api_key = os.environ["GROQ_API_KEY"]
        self.timezone = ZoneInfo(timezone)
        self._client = httpx.AsyncClient(
            timeout=30,
            headers={"Authorization": f"Bearer {self.api_key}"},
        )

    async def aclose(self):
        await self._client.aclose()

    async def _complete(self, system: str, messages: list[dict], max_tokens: int = 600, model: str = MODEL) -> str:
        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system}] + messages,
        }
        resp = await self._client.post(GROQ_URL, json=payload)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    def build_system_prompt(
        self,
        settings: dict[str, str] | None = None,
        facts: list[str] | None = None,
        corrections: list[str] | None = None,
    ) -> str:
        settings = settings or {}
        name = settings.get("name", DEFAULT_NAME)
        tone = TONE_DESCRIPTIONS.get(settings.get("tone", DEFAULT_TONE), TONE_DESCRIPTIONS[DEFAULT_TONE])
        verbosity = VERBOSITY_DESCRIPTIONS.get(
            settings.get("verbosity", DEFAULT_VERBOSITY), VERBOSITY_DESCRIPTIONS[DEFAULT_VERBOSITY]
        )
        emoji = EMOJI_DESCRIPTIONS.get(settings.get("emoji", DEFAULT_EMOJI), EMOJI_DESCRIPTIONS[DEFAULT_EMOJI])
        language = settings.get("language", DEFAULT_LANGUAGE)
        nickname = settings.get("nickname")

        hour = datetime.now(self.timezone).hour
        energy = next(
            (e for start, end, e in TIME_OF_DAY_ENERGY if start <= hour < end),
            TIME_OF_DAY_ENERGY[0][2],
        )

        prompt = (
            f"Your name is {name}. You are the user's personal assistant (via Telegram bot). "
            f"Communicate with the user in {language}, using a {tone} tone. {verbosity} {emoji} {energy} "
            "If the user mentions a task, reminder, or plan, confirm you've noted it naturally "
            "(e.g. 'Got it!' or 'Noted!'). "
            f"{NATURAL_LANGUAGE_GUIDE}"
        )

        if nickname:
            prompt += f" Address the user as '{nickname}'."

        if corrections:
            corrections_text = "\n".join(f"- {c}" for c in corrections)
            prompt += (
                "\n\nIMPORTANT: The user has flagged the following as mistakes to avoid. "
                f"NEVER repeat them:\n{corrections_text}"
            )

        if facts:
            facts_text = "\n".join(f"- {f}" for f in facts)
            prompt += f"\n\nWhat you know about the user:\n{facts_text}"

        return prompt

    async def chat_reply(
        self,
        history: list[tuple[str, str]],
        user_message: str,
        settings: dict[str, str] | None = None,
        facts: list[str] | None = None,
        corrections: list[str] | None = None,
    ) -> str:
        system_prompt = self.build_system_prompt(settings, facts, corrections)
        messages = [{"role": role, "content": content} for role, content in history]
        messages.append({"role": "user", "content": user_message})
        return await self._complete(system_prompt, messages)

    async def extract_fact(self, user_message: str) -> str | None:
        raw = await self._complete(
            FACT_EXTRACTION_PROMPT,
            [{"role": "user", "content": user_message}],
            max_tokens=100,
        )
        raw = raw.strip().strip('"')
        if not raw or raw.lower() == "null":
            return None
        return raw

    async def extract_tasks(self, user_message: str, default_due_date: str | None = None) -> list[dict]:
        now = datetime.now(self.timezone).strftime("%Y-%m-%d %H:%M, %A")
        default_due_hint = (
            f"If no explicit date is given, default to {default_due_date}. "
            if default_due_date
            else ""
        )
        prompt = TASK_EXTRACTION_PROMPT_TEMPLATE.format(now=now, default_due_hint=default_due_hint)
        raw = await self._complete(
            prompt,
            [{"role": "user", "content": user_message}],
            max_tokens=500,
        )
        try:
            tasks = json.loads(raw.strip())
            return tasks if isinstance(tasks, list) else []
        except json.JSONDecodeError:
            return []

    async def transcribe_audio(self, audio_bytes: bytes, filename: str = "voice.ogg") -> str:
        files = {"file": (filename, bytes(audio_bytes), "audio/ogg")}
        data = {"model": TRANSCRIBE_MODEL}
        resp = await self._client.post(GROQ_TRANSCRIBE_URL, files=files, data=data)
        resp.raise_for_status()
        return resp.json()["text"]

    async def describe_image(self, image_base64: str, caption: str, settings: dict[str, str] | None = None) -> str:
        text = caption or (
            "What is in this image? Explain clearly. "
            "If there is any text, numbers, or writing (document, receipt, table, etc.), "
            "read it out word for word, accurately."
        )
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": text},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}},
                ],
            }
        ]
        return await self._complete(
            self.build_system_prompt(settings), messages, max_tokens=600, model=VISION_MODEL
        )

    async def compose_reminder(self, tasks: list[str], settings: dict[str, str] | None = None) -> str:
        tasks_text = "\n".join(f"- {t}" for t in tasks) if tasks else "None."
        prompt = (
            f"Open tasks:\n{tasks_text}\n\n"
            "Write a very short (1-2 sentences), friendly, motivating reminder. "
            "Briefly mention the most important/closest task and encourage action."
        )
        return await self._complete(
            self.build_system_prompt(settings), [{"role": "user", "content": prompt}], max_tokens=200
        )

    async def compose_digest(
        self, weather_summary: str, tasks: list[str], settings: dict[str, str] | None = None
    ) -> str:
        tasks_text = "\n".join(f"- {t}" for t in tasks) if tasks else "No tasks yet."
        prompt = (
            f"Write a morning digest. Weather: {weather_summary}\n"
            f"Open tasks (today and upcoming):\n{tasks_text}\n\n"
            "Write a short, motivating morning message. Clearly show the weather and tasks, "
            "noting which are for today."
        )
        return await self._complete(
            self.build_system_prompt(settings), [{"role": "user", "content": prompt}], max_tokens=500
        )

    async def compose_planning_prompt(self, settings: dict[str, str] | None = None) -> str:
        prompt = (
            "The day is ending (sunset). Ask the user what tasks or plans they have for tomorrow "
            "or the coming days (there can be multiple). Keep it short and friendly. "
            "At the end, mention that if they just reply, you'll save their response as tasks."
        )
        return await self._complete(
            self.build_system_prompt(settings), [{"role": "user", "content": prompt}], max_tokens=200
        )

    async def compose_daily_summary(
        self, completed: list[str], planned_count: int, settings: dict[str, str] | None = None
    ) -> str:
        completed_text = "\n".join(f"- {c}" for c in completed) if completed else "Nothing marked as done."
        prompt = (
            f"Tasks completed today ({len(completed)}):\n{completed_text}\n"
            f"Total tasks planned for today: {planned_count}.\n\n"
            "Write a short, sincere end-of-day summary. State the completion rate and write "
            "in an encouraging tone (praise for good results, gently motivate if low)."
        )
        return await self._complete(
            self.build_system_prompt(settings), [{"role": "user", "content": prompt}], max_tokens=300
        )

    async def compose_period_analytics(
        self,
        period_label: str,
        completed_count: int,
        planned_count: int,
        settings: dict[str, str] | None = None,
    ) -> str:
        rate = f"{round(100 * completed_count / planned_count)}%" if planned_count else "no data"
        prompt = (
            f"Stats for {period_label}: planned — {planned_count}, "
            f"completed — {completed_count}, completion rate — {rate}.\n\n"
            "Write a short analytical summary based on these numbers — how well they did, "
            "and give one short recommendation for the next period."
        )
        return await self._complete(
            self.build_system_prompt(settings), [{"role": "user", "content": prompt}], max_tokens=350
        )
