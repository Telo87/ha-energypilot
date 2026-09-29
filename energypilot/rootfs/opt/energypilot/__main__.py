"""Entry point: ``python3 -m energypilot``."""

import logging

from aiohttp import web

from .config import DATA_DIR, Settings, load_options
from .db import Database
from .ha import HomeAssistant
from .hub import Hub
from .server import create_app


def main() -> None:
    options = load_options()
    logging.basicConfig(
        level=getattr(logging, options.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    db = Database(DATA_DIR / "energypilot.db")
    hub = Hub(options, Settings(), db, HomeAssistant())
    app = create_app(options, hub)
    logging.getLogger("energypilot").info("EnergyPilot läuft auf Port %d", options.port)
    web.run_app(app, host="0.0.0.0", port=options.port, access_log=None, print=None)


if __name__ == "__main__":
    main()
