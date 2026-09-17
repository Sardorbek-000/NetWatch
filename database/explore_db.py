"""
NetWatch — quick database explorer.

Prints what's in netwatch.db in a readable form, using the same tested
Storage class the app itself uses (so this always reflects the real
schema, no separate SQL to maintain).

Usage:
    python3 database/explore_db.py                     # overview: all profiles + recent scans
    python3 database/explore_db.py --profile Home      # full scan history for one profile
    python3 database/explore_db.py --scan 3            # full device list for scan #3
    python3 database/explore_db.py --db other.db ...   # point at a different database file
"""

import argparse

from storage import Storage


def main() -> None:
    parser = argparse.ArgumentParser(description="Browse netwatch.db from the terminal")
    parser.add_argument("--db", default="netwatch.db", help="Path to the database file (default: netwatch.db)")
    parser.add_argument("--profile", help="Show full scan history for this profile name")
    parser.add_argument("--scan", type=int, help="Show full device list for this scan id")
    args = parser.parse_args()

    storage = Storage(args.db)

    if args.scan is not None:
        devices = storage.get_devices_for_scan(args.scan)
        print(f"--- Scan #{args.scan}: {len(devices)} device(s) ---")
        for d in devices:
            print(f"{d['ip']:<15} {d['mac']:<18} {(d['vendor'] or 'Unknown'):<20} {(d['hostname'] or '-'):<20} {d['status']}")
        return

    if args.profile:
        profile_id = storage.get_or_create_profile(args.profile)  # looks up; only creates if it truly doesn't exist yet
        history = storage.get_scan_history(profile_id)
        print(f"--- Scan history for '{args.profile}' (id={profile_id}): {len(history)} scan(s) ---")
        for s in history:
            print(f"#{s['id']:<4} {s['scan_time']}  {s['scan_type']:<9} {s['subnet_cidr'] or '-':<18} {s['device_count']} device(s)")
        return

    # Default: overview of everything in the database.
    profiles = storage.list_profiles()
    print(f"--- {len(profiles)} profile(s) in {args.db} ---")
    for p in profiles:
        history = storage.get_scan_history(p["id"])
        print(f"\n[{p['id']}] {p['name']}  (created {p['created_at']}, {len(history)} scan(s))")
        for s in history[-5:]:  # only the 5 most recent, to keep the overview short
            print(f"    #{s['id']:<4} {s['scan_time']}  {s['scan_type']:<9} {s['device_count']} device(s)")
        if len(history) > 5:
            print(f"    ... and {len(history) - 5} more. Use --profile \"{p['name']}\" to see all of them.")


if __name__ == "__main__":
    main()
