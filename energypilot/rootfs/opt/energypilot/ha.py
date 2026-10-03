"""Home Assistant access: REST (states, config, sensors) and WebSocket (statistics).

Inside the add-on the Supervisor proxy is used. For development against a real
instance set ENERGYPILOT_HA_URL (e.g. http://homeassistant.local:8123) and
ENERGYPILOT_HA_TOKEN (long-lived access token).
"""

from __future__ import annotations

import itertools
import logging
import os
from datetime import datetime
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)


class HAError(Exception):
    pass


def _ts(value: Any) -> int:
    """Statistics timestamps: ms since epoch (new) or ISO strings (old)."""
    if isinstance(value, (int, float)):
        return int(value / 1000) if value > 1e11 else int(value)
    return int(datetime.fromisoformat(str(value)).timestamp())


class HomeAssistant:
    def __init__(self) -> None:
        sup = os.environ.get("SUPERVISOR_TOKEN")
        if sup:
            self._token = sup
            self._rest = "http://supervisor/core/api"
            self._ws = "ws://supervisor/core/websocket"
        else:
            url = os.environ.get("ENERGYPILOT_HA_URL", "").rstrip("/")
            self._token = os.environ.get("ENERGYPILOT_HA_TOKEN", "") if url else ""
            self._rest = f"{url}/api"
            self._ws = url.replace("http", "ws", 1) + "/api/websocket"
        self._session: aiohttp.ClientSession | None = None
        self._ids = itertools.count(1)
        self._warned = False

    @property
    def available(self) -> bool:
        return bool(self._token)

    def _sess(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession(
                headers={"Authorization": f"Bearer {self._token}"},
                timeout=aiohttp.ClientTimeout(total=30),
            )
        return self._session

    async def close(self) -> None:
        if self._session:
            await self._session.close()

    # -------------------------------------------------------------------- REST
    async def _get(self, path: str) -> Any:
        if not self._token:
            raise HAError("Keine Verbindung zu Home Assistant (kein Token).")
        try:
            async with self._sess().get(f"{self._rest}/{path}") as resp:
                if resp.status == 404:
                    return None
                if resp.status >= 400:
                    raise HAError(f"Home Assistant antwortet mit HTTP {resp.status}")
                return await resp.json()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise HAError(f"Home Assistant nicht erreichbar: {err}") from err

    async def config(self) -> dict:
        return await self._get("config") or {}

    async def direct_port(self) -> int | None:
        """Host port the user opened for direct access under "Network" (None: not opened / not an add-on)."""
        if not os.environ.get("SUPERVISOR_TOKEN"):
            return None
        try:
            async with self._sess().get("http://supervisor/addons/self/info") as resp:
                network = ((await resp.json()).get("data") or {}).get("network") or {}
            port = next((v for k, v in network.items() if k.endswith("/tcp")), None)
            return int(port) if port else None
        except (aiohttp.ClientError, TimeoutError, ValueError, TypeError, AttributeError):
            return None

    async def states(self) -> list[dict]:
        return await self._get("states") or []

    async def state(self, entity_id: str) -> dict | None:
        return await self._get(f"states/{entity_id}")

    async def publish(self, entity_id: str, state: Any, attributes: dict[str, Any]) -> None:
        if not self._token:
            return
        payload = {"state": "unknown" if state is None else state, "attributes": attributes}
        try:
            async with self._sess().post(f"{self._rest}/states/{entity_id}", json=payload) as resp:
                if resp.status >= 400 and not self._warned:
                    self._warned = True
                    _LOGGER.warning("Publishing %s failed: HTTP %s", entity_id, resp.status)
        except (aiohttp.ClientError, TimeoutError) as err:
            if not self._warned:
                self._warned = True
                _LOGGER.warning("Publishing sensors failed: %s", err)

    # --------------------------------------------------------------- WebSocket
    async def ws(self, *messages: dict) -> list[Any]:
        """Run WebSocket commands on one short-lived connection, return their results."""
        if not self._token:
            raise HAError("Keine Verbindung zu Home Assistant (kein Token).")
        results = []
        try:
            async with self._sess().ws_connect(self._ws, max_msg_size=0, heartbeat=30) as sock:
                hello = await sock.receive_json()
                if hello.get("type") == "auth_required":
                    await sock.send_json({"type": "auth", "access_token": self._token})
                    auth = await sock.receive_json()
                    if auth.get("type") != "auth_ok":
                        raise HAError("Anmeldung an der Home-Assistant-WebSocket-API fehlgeschlagen.")
                for msg in messages:
                    msg_id = next(self._ids)
                    await sock.send_json({**msg, "id": msg_id})
                    while True:
                        reply = await sock.receive_json()
                        if reply.get("id") == msg_id and reply.get("type") == "result":
                            break
                    if not reply.get("success"):
                        err = (reply.get("error") or {}).get("message", "unbekannter Fehler")
                        raise HAError(f"Home Assistant: {err}")
                    results.append(reply.get("result"))
        except (aiohttp.ClientError, TimeoutError, TypeError, ValueError) as err:
            raise HAError(f"Home-Assistant-WebSocket nicht erreichbar: {err}") from err
        return results

    async def statistics_metadata(self, ids: list[str]) -> dict[str, dict]:
        (res,) = await self.ws({"type": "recorder/get_statistics_metadata", "statistic_ids": ids})
        return {m["statistic_id"]: m for m in res or []}

    async def statistics(
        self, ids: list[str], start: int, end: int, types: list[str], period: str = "hour"
    ) -> dict[str, list[dict]]:
        """Long-term statistics; each row gets an integer ``ts`` (start, unix seconds)."""
        (res,) = await self.ws(
            {
                "type": "recorder/statistics_during_period",
                "start_time": datetime.fromtimestamp(start).astimezone().isoformat(),
                "end_time": datetime.fromtimestamp(end).astimezone().isoformat(),
                "statistic_ids": ids,
                "period": period,
                "types": types,
                "units": {"power": "W", "energy": "Wh"},
            }
        )
        out: dict[str, list[dict]] = {}
        for sid, rows in (res or {}).items():
            out[sid] = [{**r, "ts": _ts(r["start"])} for r in rows]
        return out
