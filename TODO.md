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
