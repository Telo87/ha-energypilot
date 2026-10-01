"""Forecast and price sources (all plain HTTP/JSON)."""

from __future__ import annotations

from typing import Any

import aiohttp


class SourceError(Exception):
    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status  # HTTP status, e.g. 429 = rate limit


async def get_json(
    session: aiohttp.ClientSession, url: str, params: dict | None = None, headers: dict | None = None
) -> Any:
    try:
        async with session.get(url, params=params, headers=headers) as resp:
            if resp.status == 429:
                raise SourceError("Abruflimit erreicht – nächster Versuch später", 429)
            if resp.status in (401, 403):
                raise SourceError("Zugriff verweigert – API-Schlüssel prüfen")
            if resp.status >= 400:
                text = (await resp.text())[:200]
                raise SourceError(f"HTTP {resp.status}: {text}")
            return await resp.json(content_type=None)
    except (aiohttp.ClientError, TimeoutError) as err:
        raise SourceError(f"nicht erreichbar ({err.__class__.__name__})") from err
    except ValueError as err:
        raise SourceError("ungültige Antwort") from err
