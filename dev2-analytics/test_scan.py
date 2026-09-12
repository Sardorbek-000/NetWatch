

import subprocess
import re
import socket
import sys
import ipaddress
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

import netwatch_db as db


def ping(ip):
    """Ping a single IP once, quietly. Returns True if it responded."""
    try:
        result = subprocess.run(
            ["ping", "-n", "1", "-w", "300", str(ip)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return result.returncode == 0
    except Exception:
        return False


def sweep_subnet(ip_range):
    """Ping every host in the subnet concurrently to populate the ARP table."""
    network = ipaddress.ip_network(ip_range, strict=False)
    hosts = list(network.hosts())
    print(f"Pinging {len(hosts)} addresses in {ip_range} ... this may take a moment.")
    with ThreadPoolExecutor(max_workers=50) as executor:
        list(executor.map(ping, hosts))


def read_arp_table():
    """Parse `arp -a` output into a list of {ip, mac} dicts."""
    output = subprocess.run(["arp", "-a"], capture_output=True, text=True).stdout
    devices = []
    # Windows arp -a line format: "  192.168.1.1          aa-bb-cc-dd-ee-ff     dynamic"
    pattern = re.compile(r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\s+([0-9a-fA-F-]{17})\s+(\w+)")
    for line in output.splitlines():
        match = pattern.search(line)
        if match:
            ip, mac, entry_type = match.groups()
            if entry_type.lower() != "dynamic":
                continue  # skip static entries like broadcast/multicast rows
            devices.append({
                "ip": ip,
                "mac": mac.replace("-", ":").upper(),
            })
    return devices


def resolve_hostname(ip):
    """Best-effort reverse DNS lookup. Returns None if it fails."""
    try:
        return socket.gethostbyaddr(ip)[0]
    except Exception:
        return None


def build_device_list(raw_devices):
    """Turn raw {ip, mac} entries into the dict shape record_scan expects."""
    devices = []
    for entry in raw_devices:
        devices.append({
            "ip": entry["ip"],
            "mac": entry["mac"],
            "vendor": None,          # no vendor lookup wired in yet
            "status": "online",      # it responded to ping, so it's online
            "hostname": resolve_hostname(entry["ip"]),
        })
    return devices


def main():
    ip_range = sys.argv[1] if len(sys.argv) > 1 else "192.168.1.0/24"

    sweep_subnet(ip_range)
    raw_devices = read_arp_table()

    if not raw_devices:
        print("No devices found. Double check the subnet is correct for your network (run `ipconfig`).")
        return

    devices = build_device_list(raw_devices)
    print(f"Found {len(devices)} devices:")
    for d in devices:
        print(f"  {d['ip']:<15} {d['mac']}  {d['hostname'] or ''}")

    connection = db.create_connection("netwatch.db")
    db.create_tables(connection)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    scan_id, health_data = db.record_scan(connection, timestamp, ip_range, devices)

    print(f"\nScan saved (scan_id={scan_id})")
    print(f"Health score: {health_data}")


if __name__ == "__main__":
    main()
