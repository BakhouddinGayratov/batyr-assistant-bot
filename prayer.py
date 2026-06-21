from datetime import date, datetime, timedelta

import httpx

ALADHAN_URL = "https://api.aladhan.com/v1/timings/{date_str}"

PRAYER_LABELS_UZ = {
    "Fajr": "Bomdod",
    "Sunrise": "Quyosh",
    "Dhuhr": "Peshin",
    "Asr": "Asr",
    "Maghrib": "Shom",
    "Isha": "Xufton",
}

PRAYER_ORDER = ["Bomdod", "Quyosh", "Peshin", "Asr", "Shom", "Xufton"]


async def get_prayer_times(
    latitude: float, longitude: float, for_date: date, method: int = 2, school: int = 1
) -> dict[str, str]:
    date_str = for_date.strftime("%d-%m-%Y")
    params = {"latitude": latitude, "longitude": longitude, "method": method, "school": school}
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(ALADHAN_URL.format(date_str=date_str), params=params)
        resp.raise_for_status()
        data = resp.json()

    timings = data["data"]["timings"]
    return {label: timings[key].split(" ")[0] for key, label in PRAYER_LABELS_UZ.items()}


def format_prayer_times(times: dict[str, str]) -> str:
    lines = [f"{name}: {times[name]}" for name in PRAYER_ORDER if name in times]
    return "🕋 Bugungi namaz vaqtlari:\n" + "\n".join(lines)


def current_period_label(times: dict[str, str], now: datetime) -> str | None:
    def parse(label: str) -> datetime:
        h, m = map(int, times[label].split(":"))
        return now.replace(hour=h, minute=m, second=0, microsecond=0)

    bomdod = parse("Bomdod")
    quyosh = parse("Quyosh")
    peshin = parse("Peshin")
    asr = parse("Asr")
    shom = parse("Shom")
    xufton = parse("Xufton")

    zuho_start = quyosh + timedelta(minutes=20)
    zuho_end = peshin - timedelta(minutes=10)

    if bomdod <= now < quyosh:
        return "Bomdod namozi"
    if zuho_start <= now < zuho_end:
        return "Zuho namozi (nafl)"
    if peshin <= now < asr:
        return "Peshin namozi"
    if asr <= now < shom:
        return "Asr namozi"
    if shom <= now < xufton:
        return "Shom namozi va Avvobin nafli"
    if now >= xufton:
        return "Xufton namozi"
    return None
