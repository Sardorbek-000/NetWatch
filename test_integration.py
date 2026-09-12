"""
NetWatch — Module 1 <-> Module 2 integration test
====================================================

Scans your network once, saves the result into a real SQLite database via
Storage, then reads it straight back OUT of the database (not from memory)
to prove the whole pipeline actually round-trips correctly.

Usage:
    sudo python3 test_integration.py wireless   # scan over Wi-Fi (default)
    sudo python3 test_integration.py wired      # scan over Ethernet

Needs admin/root for the ARP scan — see core/wireless_scanner.py's SETUP notes
in its module docstring if you haven't set that up yet.
"""

import sys

from storage import Storage
from core.wireless_scanner import InsufficientPrivilegesError, LANScanner, WirelessScanner


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "wireless"
    if mode not in ("wireless", "wired"):
        print(f"Usage: python3 {sys.argv[0]} [wireless|wired]")
        raise SystemExit(1)

    storage = Storage("netwatch.db")  # creates the file next to this script if it doesn't exist yet
    profile_id = storage.get_or_create_profile("Home")
    print(f"Using profile 'Home' (id={profile_id}), database: netwatch.db")

    scanner = WirelessScanner() if mode == "wireless" else LANScanner()
    scanner.register_callback(
        lambda devices, scan_time: storage.save_scan(
            devices, scan_time, profile_id, scanner.scan_type_label.lower(), scanner.subnet_cidr
        )
    )

    print(f"Scanning ({scanner.scan_type_label}) on {scanner.subnet_cidr} via {scanner.iface or 'default interface'} ...")
    try:
        devices = scanner.scan_now()
    except InsufficientPrivilegesError as exc:
        print(f"\nERROR: {exc}")
        raise SystemExit(1)

    print(f"Scan found {len(devices)} device(s).\n")

    # Read the result back OUT of netwatch.db (not the in-memory `devices`
    # list above) — this is the part that actually proves save_scan()
    # and the callback wiring worked, not just that scanning itself works.
    history = storage.get_scan_history(profile_id)
    latest_scan_id = history[-1]["id"]
    saved_devices = storage.get_devices_for_scan(latest_scan_id)

    print(f"--- Read back from netwatch.db: scan #{latest_scan_id} ---")
    for d in saved_devices:
        print(f"{d['ip']:<15} {d['mac']:<18} {(d['vendor'] or 'Unknown'):<20} {d['hostname'] or '-'}")

    print(f"\nTotal scans stored for 'Home' so far: {len(history)}")
    print("Min/max/avg device count across all stored scans:", storage.get_min_max_device_count(profile_id))


if __name__ == "__main__":
    main()
