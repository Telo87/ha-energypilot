"""SQLite storage for forecasts, measurements and prices.

Forecasts are kept per target hour in two *horizons* so storage stays small
while both matter for planning:

- ``d1`` – day-ahead: the last forecast issued before midnight (local time) of
  the target day. This is what a plan for tomorrow is based on.
- ``d0`` – short-term: the last forecast issued before the target hour began.

Every fetch overwrites the rows it is still allowed to update, so each
(source, array, hour, horizon) holds exactly one value.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterable
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS forecast (
    source TEXT NOT NULL,
    array_id TEXT NOT NULL,
    target INTEGER NOT NULL,
    horizon TEXT NOT NULL,
    wh REAL NOT NULL,
    issued INTEGER NOT NULL,
    PRIMARY KEY (source, array_id, target, horizon)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS weather (
    model TEXT NOT NULL,
    target INTEGER NOT NULL,
    horizon TEXT NOT NULL,
    ghi REAL, dhi REAL, temp REAL, cloud REAL, wind REAL,
    issued INTEGER NOT NULL,
    PRIMARY KEY (model, target, horizon)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS actual (
    series TEXT NOT NULL,
    target INTEGER NOT NULL,
    wh REAL NOT NULL,
    PRIMARY KEY (series, target)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS price (
    ts INTEGER PRIMARY KEY,
    dur INTEGER NOT NULL,
    spot REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS plan_log (
    ts INTEGER PRIMARY KEY,  -- start of the hour
    mode TEXT NOT NULL,  -- recommendation at the start of the hour
    price REAL,  -- ct/kWh
    pv REAL,  -- forecast kWh for the full hour
    load REAL,
    soc_plan_start REAL,  -- %
    soc_plan_end REAL,
    soc_actual REAL,  -- % measured when the recommendation was made
    logged INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


class Database:
    def __init__(self, path: Path | str) -> None:
        if isinstance(path, Path):
            path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.executescript(SCHEMA)
        self._lock = threading.Lock()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _write(self, sql: str, rows: Iterable[tuple]) -> int:
        rows = list(rows)
        if not rows:
            return 0
        with self._lock, self._conn:
            self._conn.executemany(sql, rows)
        return len(rows)

    def _read(self, sql: str, args: tuple = ()) -> list[tuple]:
        with self._lock:
            return self._conn.execute(sql, args).fetchall()

    # ---------------------------------------------------------------- forecast
    def put_forecast(self, rows: Iterable[tuple[str, str, int, str, float, int]]) -> int:
        """rows: (source, array_id, target, horizon, wh, issued)"""
        return self._write("INSERT OR REPLACE INTO forecast VALUES (?,?,?,?,?,?)", rows)

    def put_forecast_if_missing(self, rows: Iterable[tuple]) -> int:
        """Archive backfill must never overwrite live collected values."""
        return self._write("INSERT OR IGNORE INTO forecast VALUES (?,?,?,?,?,?)", rows)

    def forecasts(self, start: int, end: int, horizon: str) -> list[tuple[str, str, int, float]]:
        """(source, array_id, target, wh) for start <= target < end."""
        return self._read(
            "SELECT source, array_id, target, wh FROM forecast "
            "WHERE horizon=? AND target>=? AND target<? ORDER BY target",
            (horizon, start, end),
        )

    def forecast_sources(self) -> list[tuple[str, int, int, int]]:
        """(source, rows, first target, last issued)"""
        return self._read(
            "SELECT source, COUNT(*), MIN(target), MAX(issued) FROM forecast GROUP BY source"
        )

    def put_weather(self, rows: Iterable[tuple]) -> int:
        """rows: (model, target, horizon, ghi, dhi, temp, cloud, wind, issued)"""
        return self._write("INSERT OR REPLACE INTO weather VALUES (?,?,?,?,?,?,?,?,?)", rows)

    def put_weather_if_missing(self, rows: Iterable[tuple]) -> int:
        return self._write("INSERT OR IGNORE INTO weather VALUES (?,?,?,?,?,?,?,?,?)", rows)

    def weather(self, models: list[str]) -> list[tuple[str, int, str, float, float, float, int]]:
        """(model, target, horizon, ghi, dhi, temp, issued) of the given models."""
        if not models:
            return []
        marks = ",".join("?" * len(models))
        return self._read(
            f"SELECT model, target, horizon, ghi, dhi, temp, issued FROM weather WHERE model IN ({marks})",
            tuple(models),
        )

    def clear_weather(self) -> None:
        """Location changed – stored weather belongs to the old place."""
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM weather")
            self._conn.execute("DELETE FROM forecast WHERE source LIKE 'om:%'")
            self._conn.execute("DELETE FROM meta WHERE key LIKE 'archive:%'")

    def delete_array(self, array_id: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM forecast WHERE array_id=?", (array_id,))
            self._conn.execute("DELETE FROM actual WHERE series=?", (array_id,))

    def delete_forecast_source(self, source: str, array_id: str | None = None) -> None:
        with self._lock, self._conn:
            if array_id:
                self._conn.execute(
                    "DELETE FROM forecast WHERE source=? AND array_id=?", (source, array_id)
                )
            else:
                self._conn.execute("DELETE FROM forecast WHERE source=?", (source,))

    # ------------------------------------------------------------------ actual
    def put_actual(self, rows: Iterable[tuple[str, int, float]]) -> int:
        return self._write("INSERT OR REPLACE INTO actual VALUES (?,?,?)", rows)

    def actuals(self, start: int, end: int, series: str | None = None) -> list[tuple[str, int, float]]:
        if series:
            return self._read(
                "SELECT series, target, wh FROM actual WHERE series=? AND target>=? AND target<? "
                "ORDER BY target",
                (series, start, end),
            )
        return self._read(
            "SELECT series, target, wh FROM actual WHERE target>=? AND target<? ORDER BY target",
            (start, end),
        )

    def delete_actual_range(self, series: str, start: int, end: int) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM actual WHERE series=? AND target>=? AND target<?", (series, start, end))

    def delete_actual(self, series: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM actual WHERE series=?", (series,))

    def actual_range(self, series: str) -> tuple[int | None, int | None, int]:
        row = self._read(
            "SELECT MIN(target), MAX(target), COUNT(*) FROM actual WHERE series=?", (series,)
        )[0]
        return row[0], row[1], row[2]

    # ------------------------------------------------------------------- price
    def put_prices(self, rows: Iterable[tuple[int, int, float]]) -> int:
        return self._write("INSERT OR REPLACE INTO price VALUES (?,?,?)", rows)

    def prices(self, start: int, end: int) -> list[tuple[int, int, float]]:
        return self._read(
            "SELECT ts, dur, spot FROM price WHERE ts>=? AND ts<? ORDER BY ts", (start, end)
        )

    def last_price_ts(self) -> int | None:
        return self._read("SELECT MAX(ts) FROM price")[0][0]

    # ---------------------------------------------------------------- plan log
    def log_plan(self, row: tuple) -> bool:
        """First recommendation of an hour; later recalculations do not overwrite it."""
        return self._write("INSERT OR IGNORE INTO plan_log VALUES (?,?,?,?,?,?,?,?,?)", [row]) > 0

    def plan_log(self, start: int, end: int) -> list[tuple]:
        return self._read(
            "SELECT ts, mode, price, pv, load, soc_plan_start, soc_plan_end, soc_actual, logged "
            "FROM plan_log WHERE ts>=? AND ts<? ORDER BY ts",
            (start, end),
        )

    # -------------------------------------------------------------------- meta
    def get_meta(self, key: str, default: str | None = None) -> str | None:
        rows = self._read("SELECT value FROM meta WHERE key=?", (key,))
        return rows[0][0] if rows else default

    def set_meta(self, key: str, value: str) -> None:
        self._write("INSERT OR REPLACE INTO meta VALUES (?,?)", [(key, value)])

    def del_meta_prefix(self, prefix: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM meta WHERE key LIKE ?", (prefix + "%",))
