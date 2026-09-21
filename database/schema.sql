-- ============================================================================
-- NetWatch — Data Processing & Analytics Module (Backend Dev 2)
-- SQLite schema for scan history.
-- ============================================================================
-- REFERENCE FILE ONLY — storage.py does NOT read this at runtime. The
-- same SQL is embedded directly in storage.py as the SCHEMA_SQL constant,
-- so the app has zero dependency on this file existing wherever it's
-- deployed (a build step that forgets to bundle it would otherwise crash
-- on startup). This file exists so the schema is easy to read/review on
-- its own, and so you can inspect an existing netwatch.db by hand:
--     sqlite3 netwatch.db < schema.sql   (safe to re-run: everything uses
--                                          IF NOT EXISTS)
--
-- Keep this in sync with SCHEMA_SQL in storage.py if you change either —
-- running `python3 storage.py` checks the two match and warns if not.
-- ============================================================================

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

-- Per-profile custom names for devices, keyed by MAC. The MAC address
-- itself is always still shown in the UI too -- this is a supplementary
-- label, not a replacement, and it's scoped to one profile: the same
-- physical device can have a different name (or none) in a different
-- Location Profile.
CREATE TABLE IF NOT EXISTS device_labels (
    profile_id  INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    mac         TEXT NOT NULL,
    custom_name TEXT NOT NULL,
    updated_at  TEXT NOT NULL,  -- ISO-8601
    PRIMARY KEY (profile_id, mac)
);

-- ETHAN — one network-health score per scan (0-100), filled in by
-- Storage.ensure_health_scores(). Deleting a scan (or its profile) deletes
-- its score too.

CREATE TABLE IF NOT EXISTS health_scores (
    scan_id         INTEGER PRIMARY KEY REFERENCES scans(id) ON DELETE CASCADE,
    score           REAL NOT NULL,
    new_devices     INTEGER NOT NULL,
    missing_devices INTEGER NOT NULL,
    unknown_vendors  INTEGER NOT NULL  
);

-- Indexes for the query patterns the architecture doc calls out:
--   "searchable by date/time", "filtering by IP/MAC/... Vendor, Status,
--   Hostname", "comparison of scans".
CREATE INDEX IF NOT EXISTS idx_scans_profile_time  ON scans(profile_id, scan_time);
CREATE INDEX IF NOT EXISTS idx_scan_devices_scan_id ON scan_devices(scan_id);
CREATE INDEX IF NOT EXISTS idx_scan_devices_mac     ON scan_devices(mac);
