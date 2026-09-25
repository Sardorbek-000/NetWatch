# Known limitations & future work

Deliberate scope boundaries in the current build, recorded with the reasoning
behind each so they can be picked up later.

## 1. Port scanner cannot distinguish `filtered` from `closed`

**Where:** `core/ParsePorts.py` (`PortScanner.scan_port`)

A stateful firewall — the default on most routers and hosts — answers a probe
to a blocked port by silently dropping the `SYN` rather than returning `RST`
or an ICMP unreachable. From the socket's point of view that is
indistinguishable from a slow network: `connect_ex()` just times out with
`ETIMEDOUT`. Because the scanner only reports open ports, scanning a stealthy
host yields an empty list and looks broken even though it is working exactly
as designed.

This is inherent to TCP-connect scanning — nmap models it as a third state,
`filtered`, separate from `closed` — and not a bug with a one-line fix.

Planned: add a `filtered` state for "timed out, no response", distinct from
`closed` (explicit `RST`/`ECONNREFUSED`), and surface a count in the UI so a
scan reports e.g. "0 open, 3400 filtered" instead of nothing at all.

## 2. Full-range port scans are slow by design

**Where:** `core/ParsePorts.py` (`max_threads`, `timeout`)

`max_threads` defaults to 3. Testing against a real LAN host showed that
several simultaneous `connect_ex()` calls against one target produce
intermittent false negatives: a genuinely open port's handshake gets delayed
past the fixed timeout under contention. Scans were reliable at 3 threads or
fewer and began missing ports at 4 or more.

This trades speed for correctness, which is the right trade for a scanner —
a fast scan that misses open ports is worse than a slow one. The cost is that
an all-65535 scan against a fully filtered host takes a long time, since every
port pays the full timeout. A configurable timeout and a progress estimate
would make the wait legible; neither changes the underlying trade-off.

## 3. No CSV export of scan history or port results

**Where:** would live in `UI/pages/history_page.py` and
`UI/pages/port_scan_page.py`

Scan history and port results can only be read inside the app. Export would
use stdlib `csv` plus `tkinter.filedialog.asksaveasfilename`, so it needs no
new dependency: one row per device per scan, sourced from
`Storage.get_scan_history()` and `Storage.get_devices_for_scan()`.

## 4. Open ports report a number, not a service fingerprint

**Where:** `core/ParsePorts.py`, `Storage.save_open_port`

An open port is reported as a number plus a guess from
`socket.getservbyport()`. There is no indication of what is actually listening
or which version. Grabbing a banner on the `result == 0` branch only — a short
`recv()` after connect, with `HEAD / HTTP/1.0` first for HTTP-like ports —
would add this without slowing the scan, since only open ports pay the cost.
It would require a `banner` column on `open_ports`.

## 5. Notifications cover port scans but not device changes

**Where:** `UI/pages/scan_page.py`, `UI/notifier.py`

`notify()` fires on port-scan start and finish, but not when a network scan
finds a new or disconnected device — which is arguably the more useful signal.
`Storage.compare_scans()` already computes the diff, so this is a matter of
calling it after `save_scan()` and firing one coalesced notification per scan
("2 new device(s), 1 disconnected on Home"), never one per device, and
staying silent when nothing changed.
