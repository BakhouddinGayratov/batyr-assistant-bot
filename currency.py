import httpx


async def get_rate(base: str, target: str) -> float:
    url = f"https://open.er-api.com/v6/latest/{base.upper()}"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()

    if data.get("result") != "success":
        raise ValueError(f"Unknown currency code: {base}")

    rates = data["rates"]
    target = target.upper()
    if target not in rates:
        raise ValueError(f"Unknown currency code: {target}")

    return rates[target]
