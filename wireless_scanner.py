"""
NetWatch — Data Collection Module (Backend Dev 1)
====================================================
Wireless scanning part

A separate LANScanner (wired) will be added later — it will subclass
BaseScanner (below) and reuse arp_scan_subnet() as-is, so almost no
logic needs to be duplicated when that's written.



----------------------------------------------------------------------
IMPORTANT TO REAM FOR MY TEAMMATES 
----------------------------------------------------------------------

ETHAN (Backend Dev 2) — get every scan automatically:

    scanner = WirelessScanner()
    scanner.register_callback(lambda devices, scan_time: storage.save_scan(devices, scan_time))
    scanner.start_periodic_scan(interval_minutes=5)

AMIN (Tkinter/CustomTkinter dev) — read the latest result without
triggering a new scan, and run on-demand scans off the UI thread:

    devices, when = scanner.get_last_scan()

    def on_scan_now_button_click():
        threading.Thread(target=scanner.scan_now, daemon=True).start()

If you show which interface is active in the UI, use
get_interface_display_name(scanner.iface) rather than scanner.iface
directly — on Windows, scanner.iface is often a raw GUID, not "Wi-Fi".

Each `Device` has `.to_dict()` for easy handoff to SQLite / JSON / the UI.




---SETUP---
    pip install scapy mac-vendor-lookup

    Windows: also install Npcap (https://npcap.com/#download) — tick
             "Install Npcap in WinPcap API-compatible mode".
    Linux:   run as root, OR grant the capability once so you don't have
             to sudo every run:
                 sudo setcap cap_net_raw+ep $(readlink -f $(which python3))

Raw ARP packets require admin/root. See InsufficientPrivilegesError below —
catch it in the Frontend to show the "run as admin/root" prompt mentioned
in the architecture doc's "Scan Now" flow.
"""

from __future__ import annotations

import ipaddress
import logging
import os
import platform
import re
import socket
import struct
import subprocess
import threading
from abc import ABC, abstractmethod
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime

try:
    from scapy.all import ARP, Ether, conf, srp
    from scapy.error import Scapy_Exception
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "Missing dependency 'scapy'. Install with: pip install scapy\n"
        "Windows also needs Npcap: https://npcap.com/#download"
    ) from exc

try:
    from mac_vendor_lookup import MacLookup, VendorNotFoundError
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "Missing dependency 'mac-vendor-lookup'. Install with: pip install mac-vendor-lookup"
    ) from exc





# Other devs can see what's happening with: logging.basicConfig(level=logging.INFO)

logger = logging.getLogger("netwatch.data_collection")
logger.addHandler(logging.NullHandler())




# Custom exceptions — catch these specifically in the Frontend/UI layer
# ---------------------------------------------------------------------------
class InsufficientPrivilegesError(PermissionError):
    """
    Raised when ARP scanning fails because we don't have admin/root rights
    (raw sockets require elevation).

    AMIN: catch this to show the "please run as Administrator / root"
    """


class NoNetworkInterfaceError(RuntimeError):
    """Raised when the target interface doesn't exist, is down, or scanning otherwise can't proceed."""






# Data model — this is the exact shape Module 2 should persist per device
# --------------------------------------------------------------------------- 
@dataclass
class Device:
    """One discovered device from a single scan."""

    ip: str
    mac: str
    vendor: str
    hostname: str | None
    status: str  # always "online" here 
    last_seen: str  # ISO-8601 timestamp string — easy to store/sort/compare in SQLite

    def to_dict(self) -> dict:
        """Convenience for handing data to Module 2 (SQLite) / Module 3 (UI) / JSON."""
        return asdict(self)





# Low-level ARP scan — deliberately standalone so the future LANScanner can
# import and reuse it without copy-pasting this logic.
# --------------------------------------------------------------------------- 
def arp_scan_subnet(
    subnet_cidr: str,
    iface: str | None = None,
    timeout: float = 3.0,
) -> list[tuple[str, str]]:
    """
    Broadcasts an ARP request across `subnet_cidr` and collects replies.

    Returns:
        List of (ip, mac) tuples for every device that answered.

    Raises:
        InsufficientPrivilegesError: no admin/root rights.
        NoNetworkInterfaceError: bad/absent interface, or a Scapy-level failure.
    """
    logger.debug("Starting ARP scan on %s via iface=%s", subnet_cidr, iface or "default")

    arp_request = ARP(pdst=subnet_cidr)
    broadcast = Ether(dst="ff:ff:ff:ff:ff:ff")
    packet = broadcast / arp_request

    try:
        answered, _unanswered = srp(packet, timeout=timeout, iface=iface, verbose=False)
    except PermissionError as exc:
        raise InsufficientPrivilegesError(
            "Raw socket access denied. Run NetWatch as Administrator (Windows) or with "
            "sudo / CAP_NET_RAW (Linux)."
        ) from exc
    except OSError as exc:
        # e.g. "No such device" — wrong interface name, adapter unplugged, etc.
        raise NoNetworkInterfaceError(f"Could not scan on interface '{iface}': {exc}") from exc
    except Scapy_Exception as exc:
        raise NoNetworkInterfaceError(f"Scapy error while scanning: {exc}") from exc

    results = [(received.psrc, received.hwsrc.upper()) for _sent, received in answered]
    logger.debug("ARP scan finished: %d device(s) responded", len(results))
    return results




# MAC vendor resolution — wraps mac-vendor-lookup with a local cache so we don't repeat the same lookup every scan cycle.
# --------------------------------------------------------------------------- #
class VendorResolver:
    """Downloads/caches the IEEE OUI database once, then resolves MAC -> vendor name offline."""

    def __init__(self) -> None:
        self._lookup = MacLookup()
        self._cache: dict[str, str] = {}
        self._db_ready = False
        self._download_started = False
        self._download_lock = threading.Lock()

    def _start_background_download(self) -> None:
        """
        Kicks off the (slow, network-dependent) OUI database download on a
        daemon thread, exactly once completely non-blocking — nothing
        ever calls .join() on it. Lazily triggered from resolve() on first
        use instead of running in WirelessScanner.__init__, so constructing
        a scanner (and the app starting up) never waits on the network.
        Until it finishes, resolve() just reports "Unknown".
        """
        with self._download_lock:
            if self._download_started:
                return
            self._download_started = True

        def _download() -> None:
            try:
                self._lookup.update_vendors()
                with self._download_lock:
                    self._db_ready = True
                logger.info("MAC vendor database ready.")
            except Exception as exc:
                logger.warning("Could not refresh MAC vendor database (will retry on next scan): %s", exc)
                with self._download_lock:
                    # Without this, a single temporary failure (e.g. one
                    # bad connection) would leave _download_started=True
                    # forever, and resolve() would never attempt this
                    # again for the rest of the app's lifetime.
                    self._download_started = False

        threading.Thread(target=_download, daemon=True, name="NetWatch-VendorDB").start()

    def resolve(self, mac: str) -> str:
        if not self._download_started:
            self._start_background_download()

        if mac in self._cache:
            return self._cache[mac]
        if not self._db_ready:
            # Download still in flight (or offline) — don't block waiting
            # for it. Later scans will resolve properly once it lands.
            return "Unknown"
        try:
            vendor = self._lookup.lookup(mac)
        except VendorNotFoundError:
            vendor = "Unknown"
        except Exception as exc:
            logger.debug("Vendor lookup failed for %s: %s", mac, exc)
            vendor = "Unknown"
        self._cache[mac] = vendor
        return vendor


_DNS_PORT = 53
_PTR_QTYPE = 12
_IN_QCLASS = 1


def _encode_dns_name(name: str) -> bytes:
    """DNS wire-format encoding of a dotted name, e.g. 'a.b.c' length-prefixed labels + null byte."""
    parts = name.strip(".").split(".")
    return b"".join(bytes([len(p)]) + p.encode("ascii") for p in parts) + b"\x00"


class _MalformedDnsResponse(Exception):
    """
    Internal: raised when a DNS response is truncated, malformed, or its
    compression pointers cycle. This code parses UDP responses that could
    come from anywhere on the LAN (spoofable, and run inside worker
    threads) — it must never hang or crash on hostile/garbled input, only
    ever raise this and let the caller treat it as "no hostname found".
    """


_MAX_DNS_NAME_LENGTH = 255  # RFC 1035 hard limit on total encoded name length
_MAX_POINTER_JUMPS = 20  # generous ceiling — a real response needs at most a handful


def _decode_dns_name(packet: bytes, offset: int) -> tuple[str, int]:
    """
    Decodes a (possibly compressed) DNS name starting at `offset`.
    DNS responses commonly point back into the packet instead of repeating
    a name in full, so this follows those pointers. Returns (name, offset
    just past the name in the ORIGINAL stream — not the jumped-to spot).

    Hardened against malformed/malicious responses:
      every byte access is bounds-checked against len(packet) first
      pointer jumps are capped AND each jump target is tracked, so a
        cycle (offset A -> B -> A) raises instead of looping forever
      total decoded name length is capped per RFC 1035
    Raises _MalformedDnsResponse on any violation — never raises a raw
    IndexError/struct.error, and never loops indefinitely.
    """
    labels: list[str] = []
    pos = offset
    jumped = False
    end_offset = offset
    jumps = 0
    visited_pointers: set[int] = set()
    total_len = 0

    while True:
        if pos >= len(packet):
            raise _MalformedDnsResponse(f"name extends past end of packet (offset {pos})")

        length = packet[pos]

        if length == 0:
            pos += 1
            if not jumped:
                end_offset = pos
            break

        if (length & 0xC0) == 0xC0:  # top 2 bits set -> compression pointer
            if pos + 1 >= len(packet):
                raise _MalformedDnsResponse("truncated compression pointer")
            pointer = ((length & 0x3F) << 8) | packet[pos + 1]

            jumps += 1
            if jumps > _MAX_POINTER_JUMPS:
                raise _MalformedDnsResponse("too many compression-pointer jumps (likely cycle)")
            if pointer in visited_pointers:
                raise _MalformedDnsResponse("compression-pointer cycle detected")
            visited_pointers.add(pointer)

            if not jumped:
                end_offset = pos + 2
            pos = pointer
            jumped = True
            continue

        pos += 1
        if pos + length > len(packet):
            raise _MalformedDnsResponse(f"label extends past end of packet (offset {pos})")

        total_len += length + 1
        if total_len > _MAX_DNS_NAME_LENGTH:
            raise _MalformedDnsResponse("decoded name exceeds RFC 1035 max length")

        labels.append(packet[pos : pos + length].decode("ascii", errors="replace"))
        pos += length

    return ".".join(labels), end_offset


def _build_ptr_query(ip: str) -> tuple[bytes, int]:
    """Builds a raw DNS PTR (reverse-lookup) query packet for `ip`. Returns (packet, transaction_id)."""
    transaction_id = int.from_bytes(os.urandom(2), "big")
    header = struct.pack(">HHHHHH", transaction_id, 0x0100, 1, 0, 0, 0)  # 1 question, recursion desired
    reversed_octets = ip.split(".")[::-1]
    query_name = ".".join(reversed_octets) + ".in-addr.arpa"
    question = _encode_dns_name(query_name) + struct.pack(">HH", _PTR_QTYPE, _IN_QCLASS)
    return header + question, transaction_id


def _parse_ptr_response(data: bytes, transaction_id: int) -> str | None:
    """
    Pulls the first PTR record's name out of a raw DNS response, if
    present and matching our query. Never raises — any malformed,
    truncated, or garbled input (this is unauthenticated UDP off the LAN)
    is treated as "no hostname found" rather than crashing the worker
    thread that called resolve_hostname().
    """
    try:
        return _parse_ptr_response_unsafe(data, transaction_id)
    except (_MalformedDnsResponse, struct.error, IndexError, UnicodeDecodeError) as exc:
        logger.debug("Ignoring malformed/truncated DNS response: %s", exc)
        return None


def _parse_ptr_response_unsafe(data: bytes, transaction_id: int) -> str | None:
    """Does the actual parsing; may raise on malformed input — always call via _parse_ptr_response()."""
    if len(data) < 12:
        raise _MalformedDnsResponse("response shorter than a DNS header (12 bytes)")

    resp_id, _flags, qdcount, ancount = struct.unpack(">HHHH", data[:8])
    if resp_id != transaction_id or ancount == 0:
        return None

    pos = 12
    for _ in range(qdcount):  # skip the echoed question section
        _, pos = _decode_dns_name(data, pos)
        if pos + 4 > len(data):
            raise _MalformedDnsResponse("truncated question QTYPE/QCLASS")
        pos += 4  # QTYPE + QCLASS

    for _ in range(ancount):
        _, pos = _decode_dns_name(data, pos)
        if pos + 10 > len(data):
            raise _MalformedDnsResponse("truncated answer resource-record header")
        rtype, _rclass, _ttl, rdlength = struct.unpack(">HHIH", data[pos : pos + 10])
        pos += 10
        if pos + rdlength > len(data):
            raise _MalformedDnsResponse("truncated answer RDATA")
        if rtype == _PTR_QTYPE:
            name, _ = _decode_dns_name(data, pos)
            return name.rstrip(".") or None
        pos += rdlength
    return None


def _get_windows_dns_servers() -> list[str]:
    """
    Parses `ipconfig /all` for configured IPv4 DNS server addresses.
    Windows has no /etc/resolv.conf, so this is the equivalent lookup —
    used by _guess_dns_server() before it falls back to guessing the
    router lives at the first host in the subnet.
    """
    try:
        output = subprocess.run(
            ["ipconfig", "/all"],
            capture_output=True,
            text=True,
            timeout=3,
            check=True,
        ).stdout
    except Exception as exc:
        logger.debug("Could not run ipconfig to find DNS servers: %s", exc)
        return []

    servers: list[str] = []
    in_dns_block = False
    ipv4_pattern = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")
    for line in output.splitlines():
        stripped = line.strip()
        if "DNS Servers" in stripped:
            in_dns_block = True
            # The first address is often on the same line, after the colon.
            after_colon = stripped.split(":", 1)[-1].strip()
            if ipv4_pattern.match(after_colon):
                servers.append(after_colon)
            continue
        if in_dns_block:
            if ipv4_pattern.match(stripped):
                servers.append(stripped)  # a continuation line — ipconfig lists one IP per line
            else:
                in_dns_block = False  # blank/next-field line -> left the DNS Servers block
    return servers


def _guess_dns_server(ip: str) -> str:
    """
    Picks a DNS server to query for LAN reverse lookups.

    Prefers the OS-configured resolver — best chance of knowing local
    hostnames handed out by DHCP:
      - Linux/macOS: read /etc/resolv.conf
      - Windows: parse `ipconfig /all` (no resolv.conf exists there)

    Only falls back to "the router is the first host in this /24" if
    neither of those yields anything — true for most home/hotspot
    networks, but WRONG on networks where the router/DHCP server sits at
    a different address (e.g. .254). That heuristic is a last resort, not
    the primary mechanism, precisely because it can be wrong.

    A public resolver like 8.8.8.8 is never used here — it has no idea
    about private 192.168.x.x addresses, only your router/local DNS does.
    """
    if platform.system() == "Windows":
        servers = _get_windows_dns_servers()
        if servers:
            return servers[0]
    else:
        try:
            with open("/etc/resolv.conf", "r", encoding="utf-8") as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 2 and parts[0] == "nameserver":
                        return parts[1]
        except OSError:
            pass  # file not present for some reason — fall through to the heuristic below

    network = ipaddress.ip_network(f"{ip}/24", strict=False)
    return str(next(network.hosts()))


def resolve_hostname(ip: str, timeout: float = 1.0, dns_server: str | None = None) -> str | None:
    """
    Best-effort reverse-DNS lookup. Many phones/IoT devices simply won't have one — that's fine.

    Uses a PRIVATE socket created just for this call (instead of
    socket.gethostbyaddr() + the global socket.setdefaulttimeout()) so the
    timeout is local and thread-safe: this function runs concurrently from
    many worker threads (see WirelessScanner.scan's ThreadPoolExecutor),
    and mutating process-wide default-timeout state from multiple threads
    at once is a race condition — one thread's reset can clobber another's
    still-in-flight lookup.
    """
    server = dns_server or _guess_dns_server(ip)
    query, transaction_id = _build_ptr_query(ip)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)  # local to this socket only — nothing global touched
    try:
        sock.sendto(query, (server, _DNS_PORT))
        data, _addr = sock.recvfrom(512)
    except (socket.timeout, OSError):
        return None
    finally:
        sock.close()

    return _parse_ptr_response(data, transaction_id)





# Local network auto-detection
# --------------------------------------------------------------------------- 
def get_local_ip() -> str:
    """
    Returns this machine's LAN IP.
    Falls back to 127.0.0.1 if there's no network route at all (e.g. Wi-Fi
    is off, cable unplugged) — so constructing a scanner while offline
    doesn't crash the app on startup. The resulting scan just won't find
    anything meaningful until the machine reconnects.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        logger.warning("No network route available (offline?) — falling back to 127.0.0.1.")
        return "127.0.0.1"
    finally:
        s.close()


def guess_subnet_cidr(prefix_length: int = 24) -> str:
    """
    Builds a CIDR range (e.g. "192.168.1.0/24") from the local IP.

    NOTE: assumes a /24, true for the large majority of home/university
    Wi-Fi networks. If a particular Location Profile uses a different
    mask, pass `subnet_cidr` explicitly to WirelessScanner instead of
    relying on this guess (e.g. a future "advanced" field in Add Profile).
    """
    local_ip = get_local_ip()
    network = ipaddress.ip_network(f"{local_ip}/{prefix_length}", strict=False)
    return str(network)


def guess_wireless_interface() -> str | None:
    try:
        return conf.iface.name if conf.iface else None
    except Exception as exc:
        logger.debug("Could not auto-detect interface: %s", exc)
        return None


def get_interface_display_name(iface: str | None) -> str:
    """
    Best-effort HUMAN-FRIENDLY name for `iface`, for the Frontend to show
    (e.g. next to "Scanning on: ..."). On Linux/macOS the raw identifier
    (e.g. "wlan0", "wlp2s0") is already readable and is returned as-is.
    On Windows, `iface` is often a GUID — this maps it back to the
    adapter's real description (e.g. "Intel(R) Wi-Fi 6 AX201") by asking
    Scapy for the full Windows interface list and matching on name/GUID.
    Falls back to returning `iface` unchanged if no match is found.
    """
    if not iface:
        return "Default network adapter"

    if platform.system() == "Windows":
        try:
            from scapy.arch.windows import get_windows_if_list  # Windows-only, imported lazily

            for entry in get_windows_if_list():
                if iface in (entry.get("name"), entry.get("guid")):
                    return entry.get("description") or entry.get("name") or iface
        except Exception as exc:
            logger.debug("Could not resolve friendly Windows interface name for %r: %s", iface, exc)

    return iface






# BaseScanner — shared skeleton for any scanner (Wireless now, LAN later).
# Handles periodic scanning on a background thread, on-demand scans, thread-safe access to the last result, and the callback mechanism other modules use to receive fresh scan data. Subclasses just implement scan().
# --------------------------------------------------------------------------- 
class BaseScanner(ABC):
    def __init__(self) -> None:
        self._callbacks: list[Callable[[list[Device], datetime], None]] = []
        self._lock = threading.Lock()
        self._last_devices: list[Device] = []
        self._last_scan_time: datetime | None = None

        self._stop_event = threading.Event()
        self._scan_thread: threading.Thread | None = None
        self._interval_seconds: int | None = None

    @abstractmethod
    def scan(self) -> list[Device]:
        """Perform ONE scan and return the devices found."""
        raise NotImplementedError

    
    
    
    
    # Public API — this is what ETHAN (storage) / AMIN 3 (UI) use
    # ------------------------------------------------------------------ #
    def register_callback(self, callback: Callable[[list[Device], datetime], None]) -> None:
        """
        `callback(devices, scan_time)` receives:
            devices:   list[Device]  — result of that scan
            scan_time: datetime      — when the scan completed
        """
        self._callbacks.append(callback)

    def unregister_callback(self, callback: Callable) -> None:
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def get_last_scan(self) -> tuple[list[Device], datetime | None]:
        """Thread-safe getter for the most recent result — e.g. the UI can read this without re-scanning."""
        with self._lock:
            return list(self._last_devices), self._last_scan_time

    def scan_now(self) -> list[Device]:
        """
        Runs a single scan immediately. This is a BLOCKING call — callers
        (e.g. the "Scan Now" button) are responsible for running it off the
        UI thread so Tkinter doesn't freeze:

            threading.Thread(target=scanner.scan_now, daemon=True).start()
        """
        devices = self.scan()
        scan_time = datetime.now()
        with self._lock:
            self._last_devices = devices
            self._last_scan_time = scan_time
        self._notify_callbacks(devices, scan_time)
        return devices

    def start_periodic_scan(self, interval_minutes: float) -> None:
        """Starts scanning every `interval_minutes` on a daemon background thread. Returns immediately."""
        if self._scan_thread and self._scan_thread.is_alive():
            logger.warning("Periodic scan already running; call stop_periodic_scan() first.")
            return

        self._interval_seconds = max(1, int(interval_minutes * 60))
        self._stop_event.clear()
        self._scan_thread = threading.Thread(target=self._scan_loop, daemon=True, name="NetWatch-ScanLoop")
        self._scan_thread.start()
        logger.info("Periodic scan started (every %s minutes)", interval_minutes)

    def stop_periodic_scan(self, wait_timeout: float = 5.0) -> None:
        """
        Stops the background scanning loop (e.g. user leaves the profile / closes the app).

        Python threads can't be force-killed, so if a scan is still in
        flight after `wait_timeout` seconds (e.g. a slow ARP sweep on a
        big subnet), we don't block the caller forever — we log a warning
        and return instead. We deliberately do NOT clear self._scan_thread
        in that case: start_periodic_scan()'s is_alive() check then keeps
        refusing to spawn a second loop until the orphaned one actually
        exits on its own (it checks _stop_event right after its current
        scan finishes), so you can never end up with two scan loops
        running concurrently against the same shared state.
        """
        self._stop_event.set()
        if not self._scan_thread:
            logger.info("Periodic scan stopped")
            return

        self._scan_thread.join(timeout=wait_timeout)
        if self._scan_thread.is_alive():
            logger.warning(
                "Scan thread did not stop within %.0fs — a scan is likely still running. "
                "It will exit on its own once that scan completes; start_periodic_scan() "
                "will refuse to start a duplicate loop until then.",
                wait_timeout,
            )
            return

        logger.info("Periodic scan stopped")





    # Internals
    # ------------------------------------------------------------------ 
    def _scan_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.scan_now()
            except Exception:
                # A single failed scan must never silently kill the background
                # thread — log it and try again next interval.
                logger.exception("Scheduled scan failed")
            self._stop_event.wait(self._interval_seconds)  # wakes instantly on stop_periodic_scan()

    def _notify_callbacks(self, devices: list[Device], scan_time: datetime) -> None:
        for cb in self._callbacks:
            try:
                cb(devices, scan_time)
            except Exception:
                logger.exception("A scan callback raised an exception")





# WirelessScanner 
# --------------------------------------------------------------------------- #
class WirelessScanner(BaseScanner):
    """
    Wi-Fi (WLAN) device discovery via ARP.
    Args:
        subnet_cidr: e.g. "192.168.1.0/24". Auto-guessed if None.
        iface: NIC name to scan on. Auto-detected (best-effort) if None.
        timeout: seconds to wait for ARP replies per scan.
        resolve_hostnames: reverse-DNS lookups add latency; disable for
            faster scans if hostnames aren't needed.
    """

    def __init__(
        self,
        subnet_cidr: str | None = None,
        iface: str | None = None,
        timeout: float = 3.0,
        resolve_hostnames: bool = True,
    ) -> None:
        super().__init__()
        self.subnet_cidr = subnet_cidr or guess_subnet_cidr()
        self.iface = iface or guess_wireless_interface()
        self.timeout = timeout
        self.resolve_hostnames = resolve_hostnames

        self._vendor_resolver = VendorResolver()

        logger.info("WirelessScanner ready: subnet=%s iface=%s", self.subnet_cidr, self.iface or "default")

    def scan(self) -> list[Device]:
        """One full wireless scan: ARP sweep + vendor/hostname enrichment."""
        raw_hits = arp_scan_subnet(self.subnet_cidr, iface=self.iface, timeout=self.timeout)
        now_iso = datetime.now().isoformat(timespec="seconds")

        # Reverse-DNS is the slow part (up to `timeout`s per host with no
        # PTR record). We only ever look up devices that actually answered
        # ARP (a handful, not the whole /24), and we parallelize it so one
        # slow/unresponsive host doesn't stall the whole scan.
        hostnames: dict[str, str | None] = {}
        if self.resolve_hostnames and raw_hits:
            with ThreadPoolExecutor(max_workers=min(20, len(raw_hits))) as pool:
                future_to_ip = {pool.submit(resolve_hostname, ip): ip for ip, _mac in raw_hits}
                for future in as_completed(future_to_ip):
                    ip = future_to_ip[future]
                    hostnames[ip] = future.result()

        devices = [
            Device(
                ip=ip,
                mac=mac,
                vendor=self._vendor_resolver.resolve(mac),
                hostname=hostnames.get(ip),
                status="online",
                last_seen=now_iso,
            )
            for ip, mac in raw_hits
        ]

        logger.info("Wireless scan complete: %d device(s) found on %s", len(devices), self.subnet_cidr)
        return devices



# Manual test — run this file directly to sanity-check on your own machine.
# Needs admin/root 
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    def _print_scan(devices: list[Device], scan_time: datetime) -> None:
        print(f"\n--- Scan at {scan_time.isoformat(timespec='seconds')} ({len(devices)} device(s)) ---")
        for d in devices:
            print(f"{d.ip:<15} {d.mac:<18} {d.vendor:<25} {d.hostname or '-'}")

    scanner = WirelessScanner()  # auto-detects subnet + interface
    scanner.register_callback(_print_scan)  # Module 2 would register storage.save_scan here instead

    try:
        scanner.scan_now()  # one-off scan, e.g. the "Scan Now" button
        # scanner.start_periodic_scan(interval_minutes=5)  # e.g. "Start Interval" button
    except InsufficientPrivilegesError as exc:
        print(f"\nERROR: {exc}")
