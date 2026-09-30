"""Run EnergyPilot locally against a real Home Assistant (read-only).

Put the connection into a file ``.env`` next to this script (it is ignored by git):

    ENERGYPILOT_HA_URL=http://homeassistant.local:8123
    ENERGYPILOT_HA_TOKEN=<long-lived access token>

Then start ``python dev.py`` and open http://localhost:8099. The local instance
keeps its own data in ``data/dev`` and never writes sensors to Home Assistant.
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent


def load_env(path: Path) -> None:
    if not path.exists():
        sys.exit(f"{path} fehlt – bitte mit ENERGYPILOT_HA_URL und ENERGYPILOT_HA_TOKEN anlegen (siehe dev.py).")
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


if __name__ == "__main__":
    load_env(ROOT / ".env")
    for key in ("ENERGYPILOT_HA_URL", "ENERGYPILOT_HA_TOKEN"):
        if not os.environ.get(key):
            sys.exit(f"{key} fehlt in .env")
    os.environ.setdefault("ENERGYPILOT_DATA", str(ROOT / "data" / "dev"))
    os.environ.setdefault("ENERGYPILOT_ALLOW_ALL", "1")
    os.environ.setdefault("ENERGYPILOT_PORT", "8099")
    os.environ["ENERGYPILOT_PUBLISH"] = "0"  # read-only: never overwrite the add-on's sensors
    sys.path.insert(0, str(ROOT / "energypilot" / "rootfs" / "opt"))
    from energypilot.__main__ import main

    main()
