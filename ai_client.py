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
DEFAULT_TONE = "samimiy"
DEFAULT_VERBOSITY = "qisqa"
DEFAULT_LANGUAGE = "o'zbek"

TONE_DESCRIPTIONS = {
    "samimiy": "do'stona, iliq va samimiy",
    "rasmiy": "hurmatli va biroz rasmiy",
    "hazil": "yengil hazil bilan, ammo foydali",
}

VERBOSITY_DESCRIPTIONS = {
    "qisqa": "Javoblarni juda qisqa va aniq yoz (odatda 1-3 gap).",
    "batafsil": "Kerak bo'lganda batafsil va tushuntirib yoz.",
}

EMOJI_DESCRIPTIONS = {
    "yoq": "Javoblarda emoji ishlatma.",
    "oz": "Javoblarda kamdan-kam, faqat o'rinli bo'lganda bitta emoji ishlat.",
    "kop": "Javoblarda his-tuyg'ularni ifodalash uchun emojilardan erkin foydalan.",
}
DEFAULT_EMOJI = "oz"

TIME_OF_DAY_ENERGY = [
    (0, 5, "Hozir kech tun — juda tinch, qisqa va xotirjam ohangda gapir."),
    (5, 11, "Hozir ertalab — energik va ruhlantiruvchi ohangda gapir."),
    (11, 17, "Hozir kunduzi — ishchan va samarali ohangda gapir."),
    (17, 22, "Hozir kechqurun — iliq va xotirjam ohangda gapir."),
    (22, 24, "Hozir kech tun — juda tinch, qisqa va xotirjam ohangda gapir."),
]

NATURAL_UZBEK_GUIDE = (
    "Tilga e'tibor: agar til o'zbek bo'lsa, faqat tabiiy, jonli, kundalik so'zlashuv "
    "o'zbek tilida yoz — Toshkentda odamlar gaplashadigan uslubda. Inglizcha/ruschadan "
    "so'zma-so'z tarjima qilingandek qattiq, kitobiy yoki noqulay jumlalar yozma. "
    "Murakkab, uzun yoki rasman-kitobiy so'zlar o'rniga oddiy va tabiiy so'zlarni tanla. "
    "Misol: 'Men sizga yordam berishdan mamnunman' EMAS, balki 'Mayli, yordam beraman' kabi yoz. "
    "Misol: 'Ushbu vazifa muvaffaqiyatli bajarildi' EMAS, balki 'Bo'ldi, qildim' kabi yoz."
)

FACT_EXTRACTION_PROMPT = (
    "Quyidagi xabarda foydalanuvchi haqida uzoq muddatli eslab qolishga arzigulik "
    "shaxsiy ma'lumot bo'lsa (ism, kasbi, qiziqishlari, odatlari, afzal ko'rishlari va h.k.), "
    "buni QISQA bir gap qilib chiqar. Agar bunday ma'lumot yo'q bo'lsa, faqat \"null\" deb yoz. "
    "Boshqa hech narsa yozma."
)

TASK_EXTRACTION_PROMPT_TEMPLATE = (
    "Bugungi sana va vaqt: {now}. Quyidagi xabarda foydalanuvchi bir yoki bir nechta "
    "vazifa/eslatma/reja qoldirmoqchi bo'lsa (bugun, ertaga, biror kelajakdagi kun uchun), "
    "buni JSON array formatda chiqar, har bir element: "
    "{{\"description\": \"...\", \"due_at\": \"YYYY-MM-DD HH:MM yoki YYYY-MM-DD yoki null\"}}. "
    "'ertaga', 'bugun', 'dushanba', 'keyingi hafta' kabi nisbiy vaqtlarni yuqoridagi bugungi "
    "sanaga nisbatan aniq sanaga hisobla. {default_due_hint}"
    "Agar bu shunchaki suhbat bo'lib, hech qanday vazifa bo'lmasa: []. "
    "Faqat JSON array qaytar, boshqa hech narsa yozma."
)


class AssistantClient:
    def __init__(self, timezone: str = "Asia/Tashkent"):
        self.api_key = os.environ["GROQ_API_KEY"]
        self.timezone = ZoneInfo(timezone)

    async def _complete(self, system: str, messages: list[dict], max_tokens: int = 600, model: str = MODEL) -> str:
        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system}] + messages,
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(GROQ_URL, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        return data["choices"][0]["message"]["content"]

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
            f"Sening isming {name}. Sen foydalanuvchining shaxsiy yordamchisisan (Telegram bot orqali). "
            f"Foydalanuvchi bilan {language} tilida, {tone} ohangda gaplash. {verbosity} {emoji} {energy} "
            "Agar foydalanuvchi biror vazifa, eslatma yoki rejani aytsa, buni qayd etganingni "
            "tabiiy tilda tasdiqla (masalan: 'Yozib qoldim!'). "
            f"{NATURAL_UZBEK_GUIDE}"
        )

        if nickname:
            prompt += f" Foydalanuvchini '{nickname}' deb chaqir."

        if corrections:
            corrections_text = "\n".join(f"- {c}" for c in corrections)
            prompt += (
                "\n\nMUHIM: foydalanuvchi avval quyidagi xatolarni ko'rsatib tuzatgan. "
                f"Bularni HECH QACHON takrorlama:\n{corrections_text}"
            )

        if facts:
            facts_text = "\n".join(f"- {f}" for f in facts)
            prompt += f"\n\nFoydalanuvchi haqida bilganlaring:\n{facts_text}"

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
            f"Agar foydalanuvchi aniq sana aytmagan bo'lsa, sukut bo'yicha {default_due_date} sanasini ishlat. "
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
        headers = {"Authorization": f"Bearer {self.api_key}"}
        files = {"file": (filename, bytes(audio_bytes), "audio/ogg")}
        data = {"model": TRANSCRIBE_MODEL}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(GROQ_TRANSCRIBE_URL, headers=headers, files=files, data=data)
            resp.raise_for_status()
        return resp.json()["text"]

    async def describe_image(self, image_base64: str, caption: str, settings: dict[str, str] | None = None) -> str:
        text = caption or (
            "Bu rasmda nima bor? O'zbek tilida tushuntir. "
            "Agar rasmda matn, raqamlar yoki yozuv bo'lsa (hujjat, kvitansiya, jadval va h.k.), "
            "ularni so'zma-so'z, aniq o'qib ber."
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
        tasks_text = "\n".join(f"- {t}" for t in tasks) if tasks else "Yo'q."
        prompt = (
            f"Foydalanuvchining ochiq vazifalari:\n{tasks_text}\n\n"
            "O'zbek tilida, juda qisqa (1-2 gap), do'stona va motivatsion eslatma yoz. "
            "Eng yaqin/muhim vazifalarni qisqacha eslat va harakatga undash."
        )
        return await self._complete(
            self.build_system_prompt(settings), [{"role": "user", "content": prompt}], max_tokens=200
        )

    async def compose_digest(
        self, weather_summary: str, tasks: list[str], settings: dict[str, str] | None = None
    ) -> str:
        tasks_text = "\n".join(f"- {t}" for t in tasks) if tasks else "Hozircha vazifalar yo'q."
        prompt = (
            f"Ertalabki digest tayyorla. Ob-havo: {weather_summary}\n"
            f"Ochiq vazifalar (bugungi va kelajakdagi):\n{tasks_text}\n\n"
            "Foydalanuvchiga o'zbek tilida, qisqa, motivatsion ertalabki xabar yoz. "
            "Ob-havo va vazifalar ro'yxatini aniq ko'rsat, qaysi vazifalar bugunga tegishli ekanini ajrat."
        )
        return await self._complete(
            self.build_system_prompt(settings), [{"role": "user", "content": prompt}], max_tokens=500
        )

    async def compose_planning_prompt(self, settings: dict[str, str] | None = None) -> str:
        prompt = (
            "Kun yakunlanmoqda (quyosh botdi). Foydalanuvchidan ertaga yoki keyingi kunlarda "
            "qilishi kerak bo'lgan ishlarni/vazifalarni so'ra (bir nechta bo'lishi mumkin). "
            "O'zbek tilida, qisqa va do'stona yoz. "
            "Oxirida shuni tushuntir: javobini shunchaki yozib yuborsa, ularni vazifa sifatida saqlab qo'yaman."
        )
        return await self._complete(
            self.build_system_prompt(settings), [{"role": "user", "content": prompt}], max_tokens=200
        )
