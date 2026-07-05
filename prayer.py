from datetime import date, datetime, timedelta

import httpx

ALADHAN_URL = "https://api.aladhan.com/v1/timings/{date_str}"

PRAYER_LABELS = {
    "Fajr": "Fajr",
    "Sunrise": "Sunrise",
    "Dhuhr": "Dhuhr",
    "Asr": "Asr",
    "Maghrib": "Maghrib",
    "Isha": "Isha",
}

PRAYER_ORDER = ["Fajr", "Sunrise", "Dhuhr", "Asr", "Maghrib", "Isha"]


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
    return {label: timings[key].split(" ")[0] for key, label in PRAYER_LABELS.items()}


def format_prayer_times(times: dict[str, str]) -> str:
    lines = [f"{name}: {times[name]}" for name in PRAYER_ORDER if name in times]
    return "🕋 Today's Prayer Times:\n" + "\n".join(lines)


def current_period_label(times: dict[str, str], now: datetime) -> str | None:
    def parse(label: str) -> datetime:
        h, m = map(int, times[label].split(":"))
        return now.replace(hour=h, minute=m, second=0, microsecond=0)

    fajr = parse("Fajr")
    sunrise = parse("Sunrise")
    dhuhr = parse("Dhuhr")
    asr = parse("Asr")
    maghrib = parse("Maghrib")
    isha = parse("Isha")

    duha_start = sunrise + timedelta(minutes=20)
    duha_end = dhuhr - timedelta(minutes=10)

    if fajr <= now < sunrise:
        return "Fajr"
    if duha_start <= now < duha_end:
        return "Duha (nafl)"
    if dhuhr <= now < asr:
        return "Dhuhr"
    if asr <= now < maghrib:
        return "Asr"
    if maghrib <= now < isha:
        return "Maghrib"
    if now >= isha:
        return "Isha"
    return None
