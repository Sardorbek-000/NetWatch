"""
NetWatch — Data Processing & Analytics Module (Backend Dev 2)
================================================================

SQLite storage for scan history, plus a starter set of analytics
functions (comparison, most-connected devices, min/max counts, uptime
stability) that match what the architecture doc calls out. Add more
analytics methods to the Storage class as you build new features — the
schema (see schema.sql, applied automatically below) already supports
filtering by date range, IP/MAC/vendor/status/hostname, and comparing
any two scans, so most new features are just a new query method here.

Deliberately has ZERO dependency on core/wireless_scanner.py / scapy /
mac-vendor-lookup — Module 2 shouldn't need Module 1's networking stack
installed just to run its own tests or be imported by the Frontend. It
accepts anything with the same shape as Module 1's `Device` (an object
with a `.to_dict()` method, OR a plain dict with the same keys) — see
_normalize_device() below.

----------------------------------------------------------------------
HOW THIS CONNECTS TO MODULE 1 (core/wireless_scanner.py)
----------------------------------------------------------------------
    from storage import Storage
    from core.wireless_scanner import WirelessScanner

    storage = Storage("netwatch.db")               # creates/opens the DB, applies schema.sql
    profile_id = storage.get_or_create_profile("Home")

    scanner = WirelessScanner()                     # or LANScanner() for a wired profile
    scanner.register_callback(
        lambda devices, scan_time: storage.save_scan(
            devices, scan_time, profile_id=profile_id,
            # scan_type_label is "Wireless" or "Wired" depending on which
            # class you instantiated above -- use it instead of hardcoding
            # a string, so this line doesn't silently mislabel LANScanner
            # data as "wireless" if you swap the scanner class later.
            scan_type=scanner.scan_type_label.lower(), subnet_cidr=scanner.subnet_cidr,
        )
    )
    scanner.start_periodic_scan(interval_minutes=5, duration_hours=8)

----------------------------------------------------------------------
HOW MODULE 3 (FRONTEND) READS THIS
----------------------------------------------------------------------
    history = storage.get_scan_history(profile_id)          # for the History list
    devices = storage.get_devices_for_scan(scan_id)          # "View scan"
    diff    = storage.compare_scans(scan_id_a, scan_id_b)     # "compare scans"
    top     = storage.get_most_connected_devices(profile_id)  # "most connected"
    stats   = storage.get_min_max_device_count(profile_id)    # "min/max device counts"
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Iterable, Iterator

# ---------------------------------------------------------------------------
# Schema is embedded here (not read from schema.sql at runtime) so this
# module has ZERO dependency on an external file being present alongside
# it — a packaging/deployment step that forgets to bundle schema.sql (or
# runs storage.py from a different working directory) would otherwise hit
# an unhandled FileNotFoundError before the app even starts.
#
# schema.sql still exists as a human-readable reference/documentation
# file — e.g. for `sqlite3 netwatch.db < schema.sql` to inspect an
# existing DB by hand — but it is not the source of truth the app reads
# from. Keep the two in sync if you change one (there's a test for this;
# see the __main__ block at the bottom of this file).
# ---------------------------------------------------------------------------
SCHEMA_SQL = """
-- One row per Location Profile ("Home", "University", etc.) — the top
-- level of organization the architecture doc calls for.
CREATE TABLE IF NOT EXISTS profiles (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL  -- ISO-8601
);

-- One row per completed scan (from Module 1's scan_now() / periodic loop).
-- device_count is denormalized (duplicated from COUNT(scan_devices)) on
-- purpose — the History screen lists potentially hundreds of past scans,
-- and this avoids a JOIN+COUNT just to show "Scan #42 — 7 devices".
CREATE TABLE IF NOT EXISTS scans (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id   INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    scan_time    TEXT NOT NULL,   -- ISO-8601, when the scan completed
    scan_type    TEXT NOT NULL,   -- "wireless" | "wired" — matches WirelessScanner/LANScanner
    subnet_cidr  TEXT,            -- e.g. "192.168.1.0/24", kept for reference/debugging
    device_count INTEGER NOT NULL
);

-- One row per device found in a given scan. This is where Device.to_dict()
-- from Module 1 lands, field-for-field.
CREATE TABLE IF NOT EXISTS scan_devices (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id   INTEGER NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
    ip        TEXT NOT NULL,
    mac       TEXT NOT NULL,
    vendor    TEXT,
    hostname  TEXT,
    status    TEXT NOT NULL,  -- as reported by Module 1 — currently always "online"
    last_seen TEXT NOT NULL   -- ISO-8601
);

-- Indexes for the query patterns the architecture doc calls out:
--   "searchable by date/time", "filtering by IP/MAC/... Vendor, Status,
--   Hostname", "comparison of scans".
CREATE INDEX IF NOT EXISTS idx_scans_profile_time  ON scans(profile_id, scan_time);
CREATE INDEX IF NOT EXISTS idx_scan_devices_scan_id ON scan_devices(scan_id);
CREATE INDEX IF NOT EXISTS idx_scan_devices_mac     ON scan_devices(mac);
"""


def _normalize_device(device: Any) -> dict:
    """
    Accepts either a Module-1-style object with `.to_dict()` (the `Device`
    dataclass from core/wireless_scanner.py) or a plain dict with the same
    keys (ip, mac, vendor, hostname, status, last_seen) — so this module
    never has to import scapy/mac-vendor-lookup just to know Device's shape.
    """
    if hasattr(device, "to_dict"):
        return device.to_dict()
    if isinstance(device, dict):
        return device
    raise TypeError(f"Unsupported device type for save_scan(): {type(device)!r}")


def _iso(value: datetime | None) -> str | None:
    """Consistent ISO-8601 formatting for anything we store/compare as a timestamp."""
    return value.isoformat(timespec="seconds") if value is not None else None


class Storage:
    """
    SQLite-backed storage for scan history. One `Storage` instance per
    database file — safe to share a single instance across threads (each
    call opens its own short-lived connection; see _connect()), which is
    exactly how Module 1's background scan thread and the Frontend's UI
    thread will both be using this at once.
    """

    def __init__(self, db_path: str = "netwatch.db") -> None:
        self.db_path = db_path
        self._init_schema()

    # ------------------------------------------------------------------ #
    # Connection handling
    # ------------------------------------------------------------------ #
    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """
        Opens a short-lived connection per call rather than holding one
        open for the app's whole lifetime. Scans happen every few minutes
        and queries are occasional/lightweight, so this keeps things
        simple and avoids any cross-thread sqlite3 connection headaches
        (Module 1's background scan thread and the Frontend's UI thread
        both call into Storage — this way neither has to worry about
        which thread "owns" a connection).
        """
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.execute("PRAGMA foreign_keys = ON")   # enforce ON DELETE CASCADE
        conn.execute("PRAGMA journal_mode = WAL")  # background writer + UI reader can coexist safely
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self) -> None:
        """Applies SCHEMA_SQL. Safe to call every startup — every statement in it is IF NOT EXISTS."""
        with self._connect() as conn:
            conn.executescript(SCHEMA_SQL)

    # ------------------------------------------------------------------ #
    # Profiles ("Home", "University", etc.)
    # ------------------------------------------------------------------ #
    def get_or_create_profile(self, name: str) -> int:
        """The usual entry point: looks up `name`, creating it if this is the first time. Returns its id."""
        with self._connect() as conn:
            row = conn.execute("SELECT id FROM profiles WHERE name = ?", (name,)).fetchone()
            if row:
                return row["id"]
            cur = conn.execute(
                "INSERT INTO profiles (name, created_at) VALUES (?, ?)",
                (name, _iso(datetime.now())),
            )
            new_id = cur.lastrowid
        return new_id

    def list_profiles(self) -> list[dict]:
        """For the main menu / Settings screen."""
        with self._connect() as conn:
            rows = conn.execute("SELECT id, name, created_at FROM profiles ORDER BY name").fetchall()
        return [dict(row) for row in rows]

    def delete_profile(self, profile_id: int) -> None:
        """Deletes a profile and — via ON DELETE CASCADE — all of its scans and scan_devices with it."""
        with self._connect() as conn:
            conn.execute("DELETE FROM profiles WHERE id = ?", (profile_id,))

    # ------------------------------------------------------------------ #
    # Saving scans — this is what Module 1's register_callback() calls
    # ------------------------------------------------------------------ #
    def save_scan(
        self,
        devices: Iterable[Any],
        scan_time: datetime,
        profile_id: int,
        scan_type: str = "wireless",
        subnet_cidr: str | None = None,
    ) -> int:
        """Persists one full scan result (scan row + one scan_devices row per device). Returns the new scan's id."""
        normalized = [_normalize_device(d) for d in devices]
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO scans (profile_id, scan_time, scan_type, subnet_cidr, device_count) "
                "VALUES (?, ?, ?, ?, ?)",
                (profile_id, _iso(scan_time), scan_type, subnet_cidr, len(normalized)),
            )
            scan_id = cur.lastrowid
            conn.executemany(
                "INSERT INTO scan_devices (scan_id, ip, mac, vendor, hostname, status, last_seen) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    (scan_id, d["ip"], d["mac"], d.get("vendor"), d.get("hostname"), d["status"], d["last_seen"])
                    for d in normalized
                ],
            )
        return scan_id

    # ------------------------------------------------------------------ #
    # Retrieval
    # ------------------------------------------------------------------ #
    def get_scan_history(
        self,
        profile_id: int,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[dict]:
        """List of past scans for a profile (id, time, type, subnet, device_count), oldest first. For the History screen."""
        query = "SELECT id, scan_time, scan_type, subnet_cidr, device_count FROM scans WHERE profile_id = ?"
        params: list[Any] = [profile_id]
        if start is not None:
            query += " AND scan_time >= ?"
            params.append(_iso(start))
        if end is not None:
            query += " AND scan_time <= ?"
            params.append(_iso(end))
        query += " ORDER BY scan_time ASC"

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def get_devices_for_scan(self, scan_id: int) -> list[dict]:
        """Full device list for one specific past scan. For "View scan"."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT ip, mac, vendor, hostname, status, last_seen "
                "FROM scan_devices WHERE scan_id = ? ORDER BY ip",
                (scan_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------ #
    # Analytics — starter set; add more methods here as you build features
    # ------------------------------------------------------------------ #
    def compare_scans(self, scan_id_a: int, scan_id_b: int) -> dict:
        """
        Compares two scans by MAC address. `scan_id_a` is treated as the
        earlier/baseline scan, `scan_id_b` as the later one — matches the
        doc's "compare scans (e.g. Scan#28 and Scan#30)" feature.

        Returns:
            {
                "new_devices":          [...],  # present in B, not in A
                "disconnected_devices": [...],  # present in A, not in B
                "common_devices":       [...],  # present in both
            }
        """
        devices_a = {d["mac"]: d for d in self.get_devices_for_scan(scan_id_a)}
        devices_b = {d["mac"]: d for d in self.get_devices_for_scan(scan_id_b)}

        new_macs = devices_b.keys() - devices_a.keys()
        disconnected_macs = devices_a.keys() - devices_b.keys()
        common_macs = devices_a.keys() & devices_b.keys()

        return {
            "new_devices": [devices_b[m] for m in new_macs],
            "disconnected_devices": [devices_a[m] for m in disconnected_macs],
            "common_devices": [devices_b[m] for m in common_macs],
        }

    def get_most_connected_devices(
        self,
        profile_id: int,
        start: datetime | None = None,
        end: datetime | None = None,
        top_n: int = 10,
    ) -> list[dict]:
        """Devices (by MAC) that showed up in the most scans within the range — "most connected devices"."""
        query = """
            SELECT sd.mac,
                   MAX(sd.hostname) AS hostname,
                   MAX(sd.vendor)   AS vendor,
                   COUNT(*)         AS times_seen
            FROM scan_devices sd
            JOIN scans s ON s.id = sd.scan_id
            WHERE s.profile_id = ?
        """
        params: list[Any] = [profile_id]
        if start is not None:
            query += " AND s.scan_time >= ?"
            params.append(_iso(start))
        if end is not None:
            query += " AND s.scan_time <= ?"
            params.append(_iso(end))
        query += " GROUP BY sd.mac ORDER BY times_seen DESC LIMIT ?"
        params.append(top_n)

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def get_min_max_device_count(
        self,
        profile_id: int,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> dict:
        """
        Min/max/average device count across scans in range — "Minimum and
        Maximum number of Devices". Returns min/max/avg as None (not 0) if
        there are no matching scans — "no data" and "0 devices seen" are
        different things and shouldn't be conflated in the UI.
        """
        query = (
            "SELECT MIN(device_count) AS min_count, MAX(device_count) AS max_count, "
            "AVG(device_count) AS avg_count, COUNT(*) AS total_scans FROM scans WHERE profile_id = ?"
        )
        params: list[Any] = [profile_id]
        if start is not None:
            query += " AND scan_time >= ?"
            params.append(_iso(start))
        if end is not None:
            query += " AND scan_time <= ?"
            params.append(_iso(end))

        with self._connect() as conn:
            row = conn.execute(query, params).fetchone()

        # A bare aggregate query with no GROUP BY ALWAYS returns exactly
        # one row, even when zero scans match — as (None, None, None, 0).
        # `if row` is therefore always True here and doesn't tell us
        # whether there was real data; check total_scans instead.
        if row is None or row["total_scans"] == 0:
            return {"min_count": None, "max_count": None, "avg_count": None, "total_scans": 0}
        return dict(row)

    def get_uptime_stability(
        self,
        profile_id: int,
        mac: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> float:
        """
        Percentage of scans (within range) in which `mac` was present — a
        simple "how consistently is this device online" metric, matching
        the doc's "Best stable Devices" feature. 0.0 if there were no
        scans in range at all.
        """
        total_query = "SELECT COUNT(*) FROM scans WHERE profile_id = ?"
        present_query = (
            "SELECT COUNT(*) FROM scans s JOIN scan_devices sd ON sd.scan_id = s.id "
            "WHERE s.profile_id = ? AND sd.mac = ?"
        )
        params_total: list[Any] = [profile_id]
        params_present: list[Any] = [profile_id, mac]
        if start is not None:
            total_query += " AND scan_time >= ?"
            present_query += " AND s.scan_time >= ?"
            params_total.append(_iso(start))
            params_present.append(_iso(start))
        if end is not None:
            total_query += " AND scan_time <= ?"
            present_query += " AND s.scan_time <= ?"
            params_total.append(_iso(end))
            params_present.append(_iso(end))

        with self._connect() as conn:
            total = conn.execute(total_query, params_total).fetchone()[0]
            present = conn.execute(present_query, params_present).fetchone()[0]

        return round((present / total) * 100, 1) if total else 0.0


# --------------------------------------------------------------------------- #
# Manual test — run this file directly to sanity-check it end-to-end with
# synthetic data (no real scanner/network needed).
# --------------------------------------------------------------------------- #
def _check_schema_sync_with_reference_file() -> None:
    """
    Dev-time check: confirms the embedded SCHEMA_SQL above matches the
    standalone schema.sql reference file, so the two can't silently drift
    apart. Only meaningful when schema.sql happens to be sitting next to
    this script (e.g. in the repo during development) — skipped entirely
    in a deployed/packaged environment where it may not exist, which is
    exactly the scenario SCHEMA_SQL being embedded is meant to be immune to.
    """
    from pathlib import Path
    import re

    schema_file = Path(__file__).parent / "schema.sql"
    if not schema_file.exists():
        print("(schema.sql not present here — skipping embedded/file consistency check)")
        return

    def _table_and_index_defs(sql: str) -> dict[str, str]:
        conn = sqlite3.connect(":memory:")
        conn.executescript(sql)
        rows = conn.execute(
            "SELECT name, sql FROM sqlite_master WHERE type IN ('table', 'index') AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        conn.close()
        # sqlite_master stores each CREATE statement's text verbatim,
        # whitespace and all — normalize so re-indenting/reformatting one
        # copy doesn't look like structural drift when it isn't.
        return {name: re.sub(r"\s+", " ", (sql_text or "").strip()) for name, sql_text in rows}

    embedded = _table_and_index_defs(SCHEMA_SQL)
    from_file = _table_and_index_defs(schema_file.read_text(encoding="utf-8"))

    if embedded == from_file:
        print("Embedded SCHEMA_SQL matches schema.sql reference file: OK")
    else:
        print("WARNING: embedded SCHEMA_SQL and schema.sql have drifted apart!")
        print("  Only in embedded code:", embedded.keys() - from_file.keys())
        print("  Only in schema.sql:", from_file.keys() - embedded.keys())


if __name__ == "__main__":
    import tempfile

    _check_schema_sync_with_reference_file()
    print()

    with tempfile.TemporaryDirectory() as tmp:
        db_path = f"{tmp}/netwatch_demo.db"
        storage = Storage(db_path)

        home = storage.get_or_create_profile("Home")
        print("Profile 'Home' id:", home)

        # Simulate two scans a few minutes apart: a laptop and a router
        # both times, plus a phone that shows up only in the second scan.
        scan1_devices = [
            {"ip": "192.168.1.1", "mac": "AA:AA:AA:AA:AA:01", "vendor": "TP-Link", "hostname": "router.lan", "status": "online", "last_seen": "2026-09-04T10:00:00"},
            {"ip": "192.168.1.5", "mac": "AA:AA:AA:AA:AA:02", "vendor": "Dell", "hostname": None, "status": "online", "last_seen": "2026-09-04T10:00:00"},
        ]
        scan2_devices = [
            {"ip": "192.168.1.1", "mac": "AA:AA:AA:AA:AA:01", "vendor": "TP-Link", "hostname": "router.lan", "status": "online", "last_seen": "2026-09-04T10:05:00"},
            {"ip": "192.168.1.5", "mac": "AA:AA:AA:AA:AA:02", "vendor": "Dell", "hostname": None, "status": "online", "last_seen": "2026-09-04T10:05:00"},
            {"ip": "192.168.1.9", "mac": "AA:AA:AA:AA:AA:03", "vendor": "Apple", "hostname": "iPhone", "status": "online", "last_seen": "2026-09-04T10:05:00"},
        ]

        scan1_id = storage.save_scan(scan1_devices, datetime(2026, 9, 4, 10, 0, 0), home, "wireless", "192.168.1.0/24")
        scan2_id = storage.save_scan(scan2_devices, datetime(2026, 9, 4, 10, 5, 0), home, "wireless", "192.168.1.0/24")
        print(f"Saved scan #{scan1_id} ({len(scan1_devices)} devices) and #{scan2_id} ({len(scan2_devices)} devices)")

        print("\nHistory:", storage.get_scan_history(home))
        print("\nDevices in scan 2:", storage.get_devices_for_scan(scan2_id))

        diff = storage.compare_scans(scan1_id, scan2_id)
        print("\nCompare scan1 -> scan2:")
        print("  New devices:", [d["mac"] for d in diff["new_devices"]])
        print("  Disconnected:", [d["mac"] for d in diff["disconnected_devices"]])
        print("  Common:", [d["mac"] for d in diff["common_devices"]])

        print("\nMost connected devices:", storage.get_most_connected_devices(home))
        print("\nMin/max/avg device count:", storage.get_min_max_device_count(home))
        print("\nUptime stability of router (AA:AA:AA:AA:AA:01):", storage.get_uptime_stability(home, "AA:AA:AA:AA:AA:01"), "%")
        print("Uptime stability of phone (AA:AA:AA:AA:AA:03):", storage.get_uptime_stability(home, "AA:AA:AA:AA:AA:03"), "%")
