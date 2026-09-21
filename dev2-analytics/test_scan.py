
import subprocess
import re
import socket
import sys
import ipaddress
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

import netwatch_db as db


def ping(ip):

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
    
    network = ipaddress.ip_network(ip_range, strict=False)
    hosts = list(network.hosts())
    print(f"Pinging {len(hosts)} addresses in {ip_range} ... this may take a moment.")
    with ThreadPoolExecutor(max_workers=50) as executor:
        list(executor.map(ping, hosts))


def read_arp_table():
    """Parse `arp -a` output into a list of {ip, mac} dicts."""
    output = subprocess.run(["arp", "-a"], capture_output=True, text=True).stdout
    devices = []

    pattern = re.compile(r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\s+([0-9a-fA-F-]{17})\s+(\w+)")
    for line in output.splitlines():
        match = pattern.search(line)
        if match:
            ip, mac, entry_type = match.groups()
            if entry_type.lower() != "dynamic":
                continue  #
            devices.append({
                "ip": ip,
                "mac": mac.replace("-", ":").upper(),
            })
    return devices


def resolve_hostname(ip):
    
    try:
        return socket.gethostbyaddr(ip)[0]
    except Exception:
        return None


def build_device_list(raw_devices):
    devices = []
    for entry in raw_devices:
        devices.append({
            "ip": entry["ip"],
            "mac": entry["mac"],
            "vendor": None,          
            "status": "online",     
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
