"""aiohttp web server: REST API + static single page app (served via ingress)."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import os
import re
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from aiohttp import web

from . import __version__, analysis, learn
from .config import DATA_DIR, OPEN_METEO_MODELS, Options
from .ha import HAError
from .hub import GEOMETRY_KEYS, POWER_UNITS, Hub

_LOGGER = logging.getLogger(__name__)

STATIC = Path(__file__).parent / "static"
INGRESS_PROXY = "172.30.32.2"
ENERGY_UNITS = ("Wh", "kWh", "MWh")

routes = web.RouteTableDef()


def _hub(request: web.Request) -> Hub:
    return request.app["hub"]


def _ok(data: Any = None) -> web.Response:
    return web.json_response({"ok": True, "data": data})


async def _json(request: web.Request) -> dict[str, Any]:
    try:
        data = await request.json()
    except ValueError as err:
        raise web.HTTPBadRequest(text="Ungültiges JSON") from err
    if not isinstance(data, dict):
        raise web.HTTPBadRequest(text="Ungültige Anfrage")
    return data


def _day(value: str | None, hub: Hub) -> str:
    if value and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return value
    return hub.day_key(time.time())


def _series(value: str | None, hub: Hub) -> str:
    ids = {c["id"] for c in hub.settings.arrays} | {learn.BASE_SERIES}
    return value if value in ids else analysis.TOTAL


# ---------------------------------------------------------------- direct access
# Next to ingress EnergyPilot can be opened on its own port (e.g. as an app on the phone). Ingress is
# protected by Home Assistant's login; the direct way needs the password from the add-on options.
SESSION_COOKIE = "energypilot_session"
SESSION_DAYS = 365
OPEN_PATHS = ("/static/", "/manifest.json", "/login")  # nothing secret: styles, icons, the login itself
LOGIN_TRIES = 5  # failed logins per address ...
LOGIN_WINDOW = 300  # ... within this many seconds
_failed: dict[str, list[float]] = defaultdict(list)


def _secret() -> bytes:
    """Random key of this installation - the session cookie cannot be forged from the password alone."""
    path = DATA_DIR / "direct.key"
    try:
        return bytes.fromhex(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        key = os.urandom(32)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(key.hex(), encoding="utf-8")
            os.chmod(path, 0o600)
        except OSError as err:
            _LOGGER.warning("Could not write %s: %s", path, err)
        return key


def session_token(app: web.Application) -> str:
    """Value of the session cookie; changes with the password, so a new password logs everybody out."""
    options: Options = app["options"]
    return hmac.new(app["secret"], options.direct_password.encode(), hashlib.sha256).hexdigest()


def _login_page(error: str = "", status: int = 401) -> web.Response:
    html = (STATIC / "login.html").read_text(encoding="utf-8").replace("{{VERSION}}", __version__)
    html = html.replace("{{ERROR}}", f'<p class="err">{error}</p>' if error else "")
    return web.Response(text=html, status=status, content_type="text/html", headers={"Cache-Control": "no-store"})


@web.middleware
async def guard(request: web.Request, handler):
    options: Options = request.app["options"]
    if not options.allow_all and request.remote != INGRESS_PROXY:
        if not options.direct_password:
            return web.Response(status=403, text="EnergyPilot ist nur über Home Assistant erreichbar. Für den "
                                "Direktzugriff in den Add-on-Optionen ein Passwort setzen.")
        cookie = request.cookies.get(SESSION_COOKIE, "")
        if not request.path.startswith(OPEN_PATHS) and not hmac.compare_digest(cookie.encode(), session_token(request.app).encode()):
            if request.path.startswith("/api/"):
                return web.json_response({"ok": False, "error": "Nicht angemeldet."}, status=401)
            return _login_page()
    try:
        response = await handler(request)
        if request.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-cache"
        return response
    except HAError as err:
        return web.json_response({"ok": False, "error": str(err)}, status=502)
    except web.HTTPException as err:
        if request.path.startswith("/api/") and err.status >= 400:
            return web.json_response({"ok": False, "error": err.text or err.reason}, status=err.status)
        raise
    except Exception as err:
        _LOGGER.exception("Unhandled error on %s", request.path)
        return web.json_response({"ok": False, "error": f"Interner Fehler: {err}"}, status=500)


@routes.get("/")
async def index(request: web.Request) -> web.Response:
    html = (STATIC / "index.html").read_text(encoding="utf-8").replace("{{VERSION}}", __version__)
    return web.Response(text=html, content_type="text/html", headers={"Cache-Control": "no-cache"})


@routes.get("/manifest.json")
async def manifest(request: web.Request) -> web.Response:
    """Web app manifest: "add to home screen" starts EnergyPilot full screen like an app."""
    return web.json_response({
        "name": "EnergyPilot", "short_name": "EnergyPilot", "lang": "de",
        "start_url": "./", "scope": "./", "display": "standalone",
        "background_color": "#f3f5f9", "theme_color": "#f59e0b",
        "icons": [{"src": f"static/icon-{n}.png", "sizes": f"{n}x{n}", "type": "image/png"} for n in (180, 512)],
    }, content_type="application/manifest+json")


@routes.post("/login")
async def login(request: web.Request) -> web.Response:
    options: Options = request.app["options"]
    if not options.direct_password:
        raise web.HTTPNotFound()
    now = time.time()
    who = request.remote or "?"
    _failed[who] = [t for t in _failed[who] if now - t < LOGIN_WINDOW]
    if len(_failed[who]) >= LOGIN_TRIES:
        return _login_page("Zu viele Versuche – bitte in ein paar Minuten noch einmal.", 429)
    form = await request.post()
    if not hmac.compare_digest(str(form.get("password", "")).encode(), options.direct_password.encode()):
        _failed[who].append(now)
        _LOGGER.warning("Direktzugriff: falsches Passwort von %s", who)
        return _login_page("Das Passwort stimmt nicht.")
    _failed.pop(who, None)
    response = web.Response(status=303, headers={"Location": "./"})
    response.set_cookie(SESSION_COOKIE, session_token(request.app), max_age=SESSION_DAYS * 86400,
                        httponly=True, samesite="Lax", path="/")
    return response


@routes.get("/login")
async def login_form(request: web.Request) -> web.Response:
    return web.Response(status=303, headers={"Location": "./"})


@routes.get("/api/overview")
async def overview(request: web.Request) -> web.Response:
    hub = _hub(request)
    if hub.plan_stale(60):  # the overview shows the recommendation, too - same freshness as the plan page
        await hub.update_plan()
    return _ok(await asyncio.to_thread(hub.overview))


@routes.get("/api/day")
async def day(request: web.Request) -> web.Response:
    hub = _hub(request)
    return _ok(
        await asyncio.to_thread(
            hub.day_view, _day(request.query.get("day"), hub), _series(request.query.get("series"), hub)
        )
    )


@routes.get("/api/accuracy")
async def accuracy(request: web.Request) -> web.Response:
    hub = _hub(request)
    q = request.query
    try:
        days = max(1, min(730, int(q.get("days", 30))))
    except ValueError:
        days = 30
    horizon = q.get("horizon") if q.get("horizon") in ("d0", "d1") else "d1"
    return _ok(
        await asyncio.to_thread(
            hub.accuracy, days, horizon, _series(q.get("series"), hub), q.get("common") == "1"
        )
    )


@routes.get("/api/trend")
async def trend(request: web.Request) -> web.Response:
    hub = _hub(request)
    horizon = request.query.get("horizon") if request.query.get("horizon") in ("d0", "d1") else "d1"
    return _ok(await asyncio.to_thread(hub.trend, horizon, _series(request.query.get("series"), hub)))


@routes.get("/api/prices")
async def price_view(request: web.Request) -> web.Response:
    hub = _hub(request)
    start, _ = analysis.day_bounds(_day(request.query.get("day"), hub), hub.tz)
    try:
        days = max(1, min(31, int(request.query.get("days", 2))))
    except ValueError:
        days = 2
    end = hub.midnight(start + days * 86400 + 7200)
    return _ok({"slots": hub.price_slots(start, end), "tariff": hub.settings.data["tariff"], "now": int(time.time())})


@routes.get("/api/consumption-check")
async def consumption_check(request: web.Request) -> web.Response:
    return _ok(await asyncio.to_thread(_hub(request).consumption_check))


@routes.get("/api/journal")
async def journal(request: web.Request) -> web.Response:
    try:
        days = max(1, min(90, int(request.query.get("days", 14))))
    except ValueError:
        days = 14
    return _ok(await asyncio.to_thread(_hub(request).journal, days))


@routes.get("/api/costs")
async def costs(request: web.Request) -> web.Response:
    hub = _hub(request)
    month = request.query.get("month") or hub.day_key(time.time())[:7]
    if not re.fullmatch(r"\d{4}-\d{2}", month):
        raise web.HTTPBadRequest(text="Monat als JJJJ-MM angeben")
    y, m = int(month[:4]), int(month[5:])
    start = analysis.day_start(f"{y:04d}-{m:02d}-01", hub.tz)
    end = analysis.day_start(f"{y + (m == 12):04d}-{m % 12 + 1:02d}-01", hub.tz)
    res = await asyncio.to_thread(hub.costs, start, end)
    return _ok({"month": month, **res})


@routes.get("/api/costs/months")
async def cost_months(request: web.Request) -> web.Response:
    return _ok(await asyncio.to_thread(_hub(request).cost_months, 12))


@routes.get("/api/setup-check")
async def setup_check(request: web.Request) -> web.Response:
    from . import setupcheck

    return _ok(await setupcheck.run(_hub(request)))


@routes.get("/api/export")
async def export(request: web.Request) -> web.Response:
    """Diagnostic export (ZIP) - see diagnose.py."""
    from . import diagnose, setupcheck

    hub = _hub(request)
    try:
        check = await setupcheck.run(hub)
    except Exception:  # the export must work even if the check fails
        _LOGGER.exception("Setup check for the export failed")
        check = None
    name, data = await asyncio.to_thread(diagnose.build, hub, check)
    return web.Response(body=data, content_type="application/zip",
                        headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store"})


@routes.get("/api/plan")
async def plan(request: web.Request) -> web.Response:
    hub = _hub(request)
    if hub.plan_stale(60):
        await hub.update_plan()
    return _ok(hub.plan)


@routes.post("/api/refresh")
async def refresh(request: web.Request) -> web.Response:
    _hub(request).trigger()
    return _ok()


# ------------------------------------------------------------------ settings
@routes.get("/api/settings")
async def get_settings(request: web.Request) -> web.Response:
    hub = _hub(request)
    return _ok({**hub.settings.public(), "models_available": OPEN_METEO_MODELS, "ha_location": hub.ha_location})


@routes.post("/api/settings")
async def post_settings(request: web.Request) -> web.Response:
    hub = _hub(request)
    data = await _json(request)
    old_loc = hub.location
    old_backfill = hub.settings.data["backfill_days"]
    hub.settings.update(data)
    if hub.location != old_loc:
        await asyncio.to_thread(hub.db.clear_weather)
    if hub.settings.data["backfill_days"] > old_backfill:
        await asyncio.to_thread(hub.db.del_meta_prefix, "archive:")
        await asyncio.to_thread(hub.db.del_meta_prefix, "actual:")
    hub._plan_at = 0  # recalculate the plan with the new settings
    hub.trigger()
    return _ok(hub.settings.public())


@routes.post("/api/arrays")
async def save_array(request: web.Request) -> web.Response:
    hub = _hub(request)
    data = await _json(request)
    old = next((a for a in hub.settings.arrays if a["id"] == data.get("id")), None)
    arr = hub.settings.upsert_array(data)
    geometry_changed = old is None or any(old[k] != arr[k] for k in GEOMETRY_KEYS)
    if old and old["sensor"] != arr["sensor"]:
        await asyncio.to_thread(hub.db.delete_actual, arr["id"])
        if old["sensor"]:
            await asyncio.to_thread(hub.db.del_meta_prefix, f"actual:{old['sensor']}")
    if old and geometry_changed:
        # Forecast.Solar values were calculated for the old geometry - fetch them again right away
        await asyncio.to_thread(hub.db.delete_forecast_source, "fs", arr["id"])
        hub._fs_last.pop(arr["id"], None)
        await asyncio.to_thread(hub.db.set_meta, f"fs_last:{arr['id']}", "0")
    if geometry_changed:
        asyncio.create_task(_recompute_then_trigger(hub, arr))
    else:
        hub.trigger()
    return _ok(arr)


async def _recompute_then_trigger(hub: Hub, arr: dict) -> None:
    try:
        await hub.recompute_array(arr)
    finally:
        hub.trigger()


@routes.post("/api/arrays/{array_id}/geometry")
async def check_geometry(request: web.Request) -> web.Response:
    hub = _hub(request)
    return _ok(await asyncio.to_thread(hub.check_geometry, request.match_info["array_id"]))


@routes.delete("/api/arrays/{array_id}")
async def delete_array(request: web.Request) -> web.Response:
    hub = _hub(request)
    array_id = request.match_info["array_id"]
    if not hub.settings.delete_array(array_id):
        raise web.HTTPNotFound(text="Anlage nicht gefunden")
    await asyncio.to_thread(hub.db.delete_array, array_id)
    hub._acc_cache.clear()
    return _ok()


@routes.get("/api/entities")
async def entities(request: web.Request) -> web.Response:
    """Sensors for the pickers: power, energy and percentage sensors."""
    hub = _hub(request)
    if hub.options.demo:
        from .demo import demo_entities

        return _ok(demo_entities(hub))
    states = await hub.ha.states()
    out = []
    for st in states:
        eid = st.get("entity_id", "")
        if not eid.startswith("sensor."):
            continue
        attrs = st.get("attributes") or {}
        unit = attrs.get("unit_of_measurement")
        kind = "power" if unit in POWER_UNITS else "energy" if unit in ENERGY_UNITS else "percent" if unit == "%" else None
        if not kind:
            continue
        out.append(
            {
                "entity_id": eid,
                "name": attrs.get("friendly_name") or eid,
                "unit": unit,
                "kind": kind,
                "state": st.get("state"),
                "statistics": bool(attrs.get("state_class")),
            }
        )
    out.sort(key=lambda e: e["name"].lower())
    return _ok(out)


def create_app(options: Options, hub: Hub, start: bool = True) -> web.Application:
    app = web.Application(middlewares=[guard])
    app["options"] = options
    app["hub"] = hub
    app.add_routes(routes)
    app.router.add_static("/static", STATIC)
    if options.direct_password:
        app["secret"] = _secret()
        _LOGGER.info("Direktzugriff mit Passwort ist aktiv (Port unter „Netzwerk“ freigeben)")
    if not start:  # tests: the web server without fetching and planning
        return app

    async def on_startup(_app: web.Application) -> None:
        await hub.start()

    async def on_cleanup(_app: web.Application) -> None:
        await hub.stop()

    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    return app
