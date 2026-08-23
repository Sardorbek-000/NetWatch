"""
NetWatch - Database Schema Setup
Backend Dev 2 - Data Processing & Analytics Module


"""

import sqlite3

DB_NAME = "netwatch.db"


def create_database():
    """Creates the netwatch.db file and sets up the scans/devices tables."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # One row per scan run
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scans (
            scan_id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL
        )
    """)

    # One row per device found in a given scan
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_id INTEGER NOT NULL,
            ip TEXT,
            mac TEXT,
            vendor TEXT,
            status TEXT,
            hostname TEXT,
            FOREIGN KEY (scan_id) REFERENCES scans (scan_id)
        )
    """)

    conn.commit()
    conn.close()
    print(f"Database '{DB_NAME}' created with 'scans' and 'devices' tables.")


def insert_dummy_scan():
    """
    Inserts one fake scan with a few fake devices, so you have something
    to test queries against before Dev 1's real scanner data is ready.
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Insert a scan record
    cursor.execute(
        "INSERT INTO scans (timestamp) VALUES (?)",
        ("2026-08-20 10:00:00",)
    )
    scan_id = cursor.lastrowid  # grabs the ID that was just auto-generated

    # Insertion of dummy devices associated with the scan
    dummy_devices = [
        (scan_id, "192.168.1.1", "AA:BB:CC:00:11:22", "TP-Link", "up", "router.local"),
        (scan_id, "192.168.1.16", "AA:BB:CC:33:44:55", "Apple", "up", "ethans-iphone"),
        (scan_id, "192.168.1.21", "AA:BB:CC:66:77:88", "Dell", "down", None),
    ]

    cursor.executemany("""
        INSERT INTO devices (scan_id, ip, mac, vendor, status, hostname)
        VALUES (?, ?, ?, ?, ?, ?)
    """, dummy_devices)

    conn.commit()
    conn.close()
    print(f"Dummy scan #{scan_id} inserted with {len(dummy_devices)} devices.")





def save_scan(scan_data):
    """
    Saves a scan and its associated devices to the database.
    :param scan_data: A dictionary containing 'timestamp' and 'devices' list.
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Insert the scan record
    cursor.execute(
        "INSERT INTO scans (timestamp) VALUES (?)",
        (scan_data['timestamp'],)
    )
    scan_id = cursor.lastrowid

    # Prepare device records for insertion
    device_records = [
        (scan_id, device['ip'], device['mac'], device['vendor'], device['status'], device.get('hostname'))
        for device in scan_data['devices']
    ]

    cursor.executemany("""
        INSERT INTO devices (scan_id, ip, mac, vendor, status, hostname)
        VALUES (?, ?, ?, ?, ?, ?)
    """, device_records)

    conn.commit()
    conn.close()
    print(f"Scan #{scan_id} saved with {len(device_records)} devices.")

def preview_data():
    """Quick sanity check - prints out everything currently in the database."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    print("\n--- Scans ---")
    cursor.execute("SELECT * FROM scans")
    for row in cursor.fetchall():
        print(row)

    print("\n--- Devices ---")
    cursor.execute("SELECT * FROM devices")
    for row in cursor.fetchall():
        print(row)

    conn.close()


if __name__ == "__main__":
    create_database()
    insert_dummy_scan()
    preview_data()
