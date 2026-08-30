import sqlite3 


def create_connection(db_name = "netwatch_db"):
    """ create a database connection to the SQLite database specified by db_name """
    conn = None
    try:
        conn = sqlite3.connect(db_name)
        print(f"Connected to {db_name} successfully.")
    except sqlite3.Error as error:
        print(error)
    return conn

connection = create_connection('netwatch.db')
cursor = connection.cursor()

def create_tables(connection):
    """ create tables in the SQLite database """
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS scans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                ip_range TEXT NOT NULL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS devices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_id INTEGER NOT NULL,
                ip TEXT NOT NULL,
                mac TEXT NOT NULL,
                vendor TEXT,
                status TEXT,
                hostname TEXT,
                FOREIGN KEY (scan_id) REFERENCES scans (id)
            )
        """)
        connection.commit()
        print("Tables created successfully.")
    except sqlite3.Error as error:
        print(error)

        
        def save_scan(connection, timestamp, ip_range):
            """Insert a new scan into the scans table"""
            try:
                cursor.execute("INSERT INTO scans (timestamp,ip_range) VALUES (?, ?)", (timestamp, ip_range))
                connection.commit()
                print(f"Scan saved with timestamp: {timestamp}")
                return cursor.lastrowid
            except sqlite3.Error as error:
                print(error)
                return None



            def save_scan_results(connection, scan_id, devices):
                """Insert multiple devices into the devices table for a given scan"""
                try:
                    cursor.executemany(
                        "INSERT INTO devices (scan_id, ip, mac, vendor, status, hostname) VALUES (?, ?, ?, ?, ?, ?)",
                        [(scan_id, device['ip'], device['mac'], device.get('vendor'), device.get('status'), device.get('hostname')) for device in devices]
                    )
                    connection.commit()
                    print(f"{len(devices)} devices saved for scan ID: {scan_id}")
                except sqlite3.Error as error:
                    print(error)


                    """week 3: filtering and sorting scan results"""

def get_devices_by_scan_id(connection, scan_id):
    """Retrieve devices for a specific scan ID"""
    try:
        cursor.execute("SELECT * FROM devices WHERE scan_id = ?", (scan_id,))
        devices = cursor.fetchall()
        return devices
    except sqlite3.Error as error:
        print(error)
        return []

    def get_devices_by_status(connection, status):
        """Retrieve devices filtered by status"""
        try:
            cursor.execute("SELECT * FROM devices WHERE status = ?", (status,))
            devices = cursor.fetchall()
            return devices
        except sqlite3.Error as error:
            print(error)
            return []

        def get_devices_by_ip_range(connection, ip_range):
            """Retrieve devices filtered by IP range"""
            try:
                cursor.execute("SELECT * FROM devices WHERE ip LIKE ?", (f"{ip_range}%",))
                devices = cursor.fetchall()
                return devices
            except sqlite3.Error as error:
                print(error)
                return []

            def get_devices_sorted_by_ip(connection):
                """Retrieve all devices sorted by IP address"""
                try:
                    cursor.execute("SELECT * FROM devices ORDER BY ip ASC")
                    devices = cursor.fetchall()
                    return devices
                except sqlite3.Error as error:
                    print(error)
                    return []


                def devices_by_vendor(connection, vendor):
                    """Retrieve devices filtered by vendor"""
                    try:
                        cursor.execute("SELECT * FROM devices WHERE vendor = ?", (vendor,))
                        devices = cursor.fetchall()
                        return devices
                    except sqlite3.Error as error:
                        print(error)
                        return []


                    def get_devices_by_hostname(connection, hostname):
                        """Retrieve devices filtered by hostname"""
                        try:
                            cursor.execute("SELECT * FROM devices WHERE hostname = ?", (hostname,))
                            devices = cursor.fetchall()
                            return devices
                        except sqlite3.Error as error:
                            print(error)
                            return []


                        def get_devices_by_mac(connection, mac):
                            """Retrieve devices filtered by MAC address"""
                            try:
                                cursor.execute("SELECT * FROM devices WHERE mac = ?", (mac,))
                                devices = cursor.fetchall()
                                return devices
                            except sqlite3.Error as error:
                                print(error)
                                return []


            def get_devices_by_ip(connection, ip):
                """Retrieve devices filtered by IP address"""
                try:
                    cursor.execute("SELECT * FROM devices WHERE ip = ?", (ip,))
                    devices = cursor.fetchall()
                    return devices
                except sqlite3.Error as error:
                    print(error)
                    return []

                def get_devices_with_filters(CONNECTION, status=None, ip_range=None, vendor=None, hostname=None, mac=None):
                    """Retrieve devices with multiple optional filters"""
                    query = "SELECT * FROM devices WHERE 1=1"
                    params = []

                    if status:
                        query += " AND status = ?"
                        params.append(status)
                    if ip_range:
                        query += " AND ip LIKE ?"
                        params.append(f"{ip_range}%")
                    if vendor:
                        query += " AND vendor = ?"
                        params.append(vendor)
                    if hostname:
                        query += " AND hostname = ?"
                        params.append(hostname)
                    if mac:
                        query += " AND mac = ?"
                        params.append(mac)

                    try:
                        cursor.execute(query, tuple(params))
                        devices = cursor.fetchall()
                        return devices
                    except sqlite3.Error as error:
                        print(error)
                        return []

                            
                