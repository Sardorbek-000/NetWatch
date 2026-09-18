# TODO

## Port scanner: silently-dropped (filtered) ports are invisible

**Where:** `core/ParsePorts.py` (`PortScanner.scan_port`), `UI/app.py` (`PortScan` frame)

**Problem:** Scanning only works usefully against `127.0.0.1`. Against most real
devices, a stateful firewall (default on most routers/hosts) doesn't send back
`RST` (refused) or an ICMP unreachable for a closed/blocked port — it just drops
the `SYN` packet. From the socket's view that's indistinguishable from a slow
network: `connect_ex()` simply times out with `ETIMEDOUT`. The scanner only
reports `open` ports, so a stealth-filtered host produces an empty result list
with zero feedback — looks broken even though it's working as designed.

This is inherent to TCP-connect scanning (nmap calls this state `filtered`,
distinct from `closed`), not a bug with a one-line fix.

**Plan (agreed, not yet implemented):**
1. Add a third result state, `filtered`, for "timed out with no response" —
   distinct from `closed` (explicit `RST` / `ECONNREFUSED`). Currently neither
   is reported at all.
2. Surface it in the UI: show a `filtered` count next to `open ports`, so a
   scan against a stealthy host shows e.g. "0 open, 3400 filtered" instead of
   an empty list.
3. Make the per-port timeout configurable / raise it for full scans — a fully
   filtered host hits the *entire* timeout on every port (up to 65535 x 0.5s
   / 100 threads ~= 5.5 min minimum for a full scan), which is worth surfacing
   or tuning.

**Separately fixed already (committed as of this note... verify before reuse):**
Host-level errors (DNS failure, no route to host, network unreachable) were
previously being caught by the same blanket `except OSError` and silently
treated as "closed" too. That part has a real fix: distinguish those errno
values from `ECONNREFUSED`/`ETIMEDOUT` and report them via an `on_error`
callback instead of swallowing them. (This was prototyped in conversation but
reverted at the user's request — pending re-implementation alongside the
`filtered` state work above.)

## Prerequisite — wire `Storage` + scanners into the UI

**Where:** `UI/app.py`

**Problem:** `NetWatchApp.profiles` is a plain in-memory `list[str]` — never
touches `database/storage.py`'s `Storage` class, so profiles don't survive an
app restart. `Profile`'s "Start Scanning" and "History" buttons have no
`command=` at all. None of the features below are meaningful until a
profile's scans are actually run and persisted.

**Plan:**
1. `NetWatchApp.__init__`: construct `self.storage = Storage("netwatch.db")`;
   replace the in-memory list with profile dicts (`{id, name, created_at}`)
   loaded via `self.storage.list_profiles()`; add `refresh_profiles()` to
   reload after create/delete.
2. `AddProfile.create_profile()` → `self.app.storage.get_or_create_profile(name)`.
3. `Settings.delete_selected()` → `self.app.storage.delete_profile(profile_id)`
   per selected id (key `self.selected`/`self.profile_buttons` by id, not name).
4. `Profile` gets `self.profile_id`, a session-only Wireless/Wired
   `CTkSegmentedButton` (defaults to Wireless), and lazily builds
   `self.scanner` (`WirelessScanner()`/`LANScanner()`) on first "Start
   Scanning" click — mirroring `PortScan`'s existing `self.scanner = None` /
   `queue.Queue()` / `self.after(100, self._drain_events)` pattern.
5. `Profile.start_scan()` runs `self.scanner.scan_now()` on a background
   thread; the registered callback (see "Desktop notifications" below) calls
   `storage.save_scan(devices, scan_time, profile_id, scanner.scan_type_label.lower(), scanner.subnet_cidr)`.
6. On leaving a `Profile` (its `destroy()`, and the "Go Back to Menu" command),
   call `scanner.stop_periodic_scan()` if a periodic loop is running, so no
   orphaned background thread is left behind.

## CSV export of scan history and port-scan results

**Where:** new `UI/history.py` (profile scan-history export), `UI/app.py`'s
`PortScan` frame (port-results export)

**Problem:** Scan history (via `Storage`) and port-scan results (via
`ParsePortsDb`) can only be viewed inside the app right now — there's no way
to get the data out for a report or spreadsheet.

**Plan:**
- Use stdlib `csv` + `tkinter.filedialog.asksaveasfilename` — no new
  dependency.
- **Profile export** (in the new History screen, see "Scan-history trend
  charts" below): one row per device per scan, sourced by iterating
  `storage.get_scan_history(profile_id)` then
  `storage.get_devices_for_scan(scan_id)`. Columns: `scan_id, scan_time,
  scan_type, subnet_cidr, ip, mac, vendor, hostname, status, last_seen`.
- **Port-scan export** (`PortScan`, enabled once a scan completes, mirroring
  the existing `scan_btn`/`stop_btn` enable/disable pattern): reads from
  `self.scanner.parse_ports_db` via a new `ParsePortsDb.get_open_ports(ip)`
  method (added alongside the banner column below — needs `row_factory =
  sqlite3.Row`). Columns: `ip_address, port, service_guess, banner,
  scan_timestamp` (`service_guess` reuses the existing
  `socket.getservbyport(port)` / `except OSError: "unknown"` logic already in
  `_add_port_row`).

## Port banner / service fingerprinting

**Where:** `core/ParsePorts.py` (`PortScanner.scan_port`),
`database/PortParsingDatabase.py` (`ParsePortsDb`)

**Problem:** An open port only ever reports its number + a guessed service
name from `socket.getservbyport`. There's no indication of what's actually
listening (e.g. which SSH/HTTP server, its version).

**Plan:**
1. `ParsePortsDb.__init__`: after the existing `CREATE TABLE IF NOT EXISTS
   open_ports`, add an idempotent migration — check
   `PRAGMA table_info(open_ports)` for a `banner` column and
   `ALTER TABLE open_ports ADD COLUMN banner TEXT` if missing. Also set
   `self.conn.row_factory = sqlite3.Row` (needed for `get_open_ports` above).
2. `InsertOpenPort(self, ip_address, port, banner=None)` — default keeps any
   un-updated call site working. `INSERT INTO open_ports (ip_address, port,
   banner) VALUES (?, ?, ?)`.
3. Add `get_open_ports(self, ip_address)` → list of `{port, banner,
   scan_timestamp}` dicts (needed by the CSV export above).
4. `core/ParsePorts.py`: add `BANNER_TIMEOUT = 1.0` (separate from the main
   connect timeout — only open ports pay this cost, so it doesn't slow a full
   65535-port scan) and `HTTP_LIKE_PORTS = {80, 8080, 8000, 8008, 8081, 8888,
   443, 8443}`.
5. In `scan_port(port)`, once `connect_ex` returns `result == 0`: keep the
   socket open, `settimeout(BANNER_TIMEOUT)`, and either send
   `b"HEAD / HTTP/1.0\r\n\r\n"` then `recv(1024)` for plain-HTTP-like ports
   (skip sending on 443/8443 — TLS, just attempt a passive recv) or just
   `recv(1024)` directly for everything else (SSH/FTP/SMTP-style greeting
   banners). Decode leniently (`errors="replace"`), strip, cap at 200 chars;
   `None` on timeout/`OSError`. Restructure the existing single
   `try/finally: sock.close()` into two blocks (connect, then optional
   banner-grab) so the close still happens promptly on a non-open result.
6. Pass the banner into `InsertOpenPort(host, port, banner)` and change
   `on_result(port)` → `on_result(port, banner)`. Update the one call site in
   `UI/app.py`'s `PortScan.start_scan()` (`on_result=lambda p, b: ...`) and
   `_add_port_row` to display the (truncated) banner next to the service name.
7. Compatible with the `filtered`-vs-`closed` TODO above — banner-grab logic
   only touches the `result == 0` branch.

## Scheduled/periodic scans in the Profile screen

**Where:** `UI/app.py` (`Profile` class)

**Problem:** `BaseScanner.start_periodic_scan()`/`stop_periodic_scan()` are
fully implemented in `core/wireless_scanner.py` but nothing in the UI ever
calls them — every scan today has to be triggered manually.

**Plan:**
- Add an interval control (`CTkOptionMenu` with presets like `1/5/15/30/60`
  minutes, session-only — not persisted across restarts, matching how the
  Wireless/Wired choice above is also session-only) and a
  "Start/Stop Periodic Scan" toggle button next to "Start Scanning" in
  `Profile`.
- Both the one-shot "Start Scanning" button and the periodic toggle share the
  **same** `self.scanner` instance and the **same** registered callback
  (register once, lazily, the first time either button creates the scanner) —
  so notifications and `save_scan` behave identically regardless of what
  triggered the scan.
- Starting periodic: `self.scanner.start_periodic_scan(interval_minutes=n)`;
  disable the one-shot "Start Scanning" button while periodic is active (avoid
  two concurrent `scan_now()` calls), flip the toggle to "Stop Periodic Scan".
- Stopping: `stop_periodic_scan()` can block up to 5s per its own docstring —
  run it on a background thread too, showing a disabled "Stopping..." state
  until a queued sentinel event confirms it returned.

## Scan-history trend charts

**Where:** new `UI/history.py`, `UI/requirements.txt`

**Problem:** `database/storage.py` already computes device-count-over-time
data (`get_scan_history`), min/max/avg (`get_min_max_device_count`), most-
connected devices (`get_most_connected_devices`), and per-device uptime %
(`get_uptime_stability`) — none of it is ever charted or shown anywhere.

**Plan:**
- New `History` frame, scoped to a `Profile` (built lazily the first time
  `Profile`'s "History" button is clicked, shown by placing/raising it over a
  `Profile`-owned sub-container — same `.place()`/`tkraise()` trick
  `NetWatchApp` already uses for its top-level frames — with a "Back" button
  returning to `Profile`'s own main view).
- Scrollable list of past scans from `get_scan_history(profile_id)`.
- Device-count-over-time line chart, plus a one-line summary ("min X / max Y
  / avg Z across N scans") from `get_min_max_device_count(profile_id)`.
- Per-device uptime % table: iterate `get_most_connected_devices(profile_id,
  top_n=20)` for the MAC list, then `get_uptime_stability(profile_id, mac)`
  per MAC.
- **Decided-but-flagged:** render the chart via embedded matplotlib
  (`matplotlib.figure.Figure` + `matplotlib.backends.backend_tkagg.
  FigureCanvasTkAgg`) — add `matplotlib` to `UI/requirements.txt` (currently
  only pins `customtkinter==6.0.0`). Build the `Figure`/`Axes`/`Canvas` once,
  `ax.clear()` + re-plot + `canvas.draw()` on refresh (call from an overridden
  `tkraise()`, matching `MainMenu`/`Settings`'s existing refresh pattern) —
  don't rebuild the canvas each time or it'll leak Tk widgets. Alternative if
  a new dependency isn't wanted: hand-roll a simple line/bar chart directly on
  a plain `tkinter.Canvas` — more code, no axes/legends, but zero new
  dependency. Revisit this choice before implementing if that trade-off
  matters more once real usage patterns are known.

## Desktop notifications on new/disconnected devices

**Where:** `UI/app.py` (`Profile`'s scan-result callback), no changes needed
to `database/storage.py` or `UI/notifier.py`

**Problem:** `Storage.compare_scans()` already computes new/disconnected
devices between two scans, and `UI/notifier.py`'s `notify()` already works,
but nothing connects them — a scan finding a new device today is silent.

**Plan:**
- In the scan-result callback added by the prerequisite section above
  (`_on_scan_result(devices, scan_time)`, runs on the scanner's background
  thread for both manual and periodic scans): after `save_scan` returns
  `scan_id`, if `self._last_scan_id` is set (i.e. not the profile's first scan
  this session), call `storage.compare_scans(self._last_scan_id, scan_id)`.
- Skip notifying entirely if both `new_devices` and `disconnected_devices` are
  empty (the common case on periodic scans — don't spam "nothing changed").
- Otherwise fire **one** coalesced `notify("NetWatch", message)` call per
  scan-diff — never one call per device. Message format:
  `f"{new_n} new device(s), {gone_n} disconnected on {profile_name}"`,
  omitting whichever clause is 0 (e.g. just `"2 new device(s) on Home"` if
  nothing disconnected).
- Update `self._last_scan_id = scan_id` after each scan. `notifier.notify()`
  is a blocking synchronous call under a lock — safe to call directly from
  the background scan thread, no extra marshaling needed.
