from datetime import datetime

import httpx

WEATHER_CODES = {
    0: "ochiq havo",
    1: "asosan ochiq",
    2: "qisman bulutli",
    3: "bulutli",
    45: "tuman",
    48: "muzli tuman",
    51: "yengil yomg'ir",
    53: "yomg'ir",
    55: "kuchli yomg'ir",
    61: "yomg'ir",
    63: "yomg'ir",
    65: "kuchli yomg'ir",
    71: "qor",
    73: "qor",
    75: "kuchli qor",
    80: "jala",
    95: "momaqaldiroq",
}


async def get_weather_summary(latitude: float, longitude: float) -> str:
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": "temperature_2m,weather_code",
        "daily": "temperature_2m_max,temperature_2m_min",
        "timezone": "auto",
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()

    current = data.get("current", {})
    daily = data.get("daily", {})
    temp_now = current.get("temperature_2m")
    code = current.get("weather_code")
    condition = WEATHER_CODES.get(code, "noma'lum")
    temp_max = daily.get("temperature_2m_max", [None])[0]
    temp_min = daily.get("temperature_2m_min", [None])[0]

    return (
        f"Hozir: {temp_now}°C, {condition}. "
        f"Bugun: min {temp_min}°C / max {temp_max}°C."
    )


async def get_sunset(latitude: float, longitude: float) -> datetime:
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "daily": "sunset",
        "timezone": "auto",
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()

    sunset_iso = data["daily"]["sunset"][0]
    return datetime.fromisoformat(sunset_iso)
