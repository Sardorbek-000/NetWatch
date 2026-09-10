from copy import error
import sqlite3 
import re


def create_connection(db_name = "netwatch.db"):
    """ create a database connection to the SQLite database specified by db_name """
    conn = None
    try:
        conn = sqlite3.connect(db_name)
        print(f"Connected to {db_name} successfully.")
    except sqlite3.Error as error:
        print(error)
    return conn

connection = create_connection('netwatch.db')

def create_tables(connection):
    """ create tables in the SQLite database """
    try:
        
        cursor = connection.cursor()
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

def  save_scan(connection, timestamp, ip_range):
            """Insert a new scan into the scans table"""
            try:
                cursor = connection.cursor()
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
                    cursor = connection.cursor()
                    cursor.executemany(
                        "INSERT INTO devices (scan_id, ip, mac, vendor, status, hostname) VALUES (?, ?, ?, ?, ?, ?)",
                        [(scan_id, device['ip'], device['mac'], device.get('vendor'), device.get('status'), device.get('hostname')) for device in devices]
                    )
                    connection.commit()
                    print(f"{len(devices)} devices saved for scan ID: {scan_id}")
                except sqlite3.Error as error:
                    print(error)


                    """validation helpers"""


def is_valid_ip(ip):            
                    # Simple IP address validation (basic)
                    ip_pattern = re.compile(r'^(\d{1,3}\.){3}\d{1,3}$')
                    if ip_pattern.match(ip):
                        # Check if each octet is within the valid range 
                        octets = ip.split('.')
                        for octet in octets:
                            if int(octet) > 255:
                                return False
                        return True
                    return False            
def is_valid_mac(mac):
                    # Simple MAC address validation (basic)
                    mac_pattern = re.compile(r'^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$')
                    return bool(mac_pattern.match(mac)) 


def is_valid_ip_range(ip_range):
                    ip_range_pattern = re.compile(r'^(\d{1,3}\.){3}\d{1,3}/\d{1,2}$')
                    if ip_range_pattern.match(ip_range):
                        # Check if the IP part is valid
                        ip_part, prefix_length = ip_range.split('/')
                        if not is_valid_ip(ip_part):
                            return False
                    
                        if not (0 <= int(prefix_length) <= 32):
                            return False
                        return True
                    return False


"""week 3: filtering and sorting scan results"""

def get_devices_by_scan_id(connection, scan_id):
    """Retrieve devices for a specific scan ID"""
    try:
        cursor = connection.cursor()
        cursor.execute("SELECT * FROM devices WHERE scan_id = ?", (scan_id,))
        devices = cursor.fetchall()
        return devices
    except sqlite3.Error as error:
        print(error)
        return []

def get_devices_by_status(connection, status):
        """Retrieve devices filtered by status"""
        try:
            cursor = connection.cursor()
            cursor.execute("SELECT * FROM devices WHERE status = ?", (status,))
            devices = cursor.fetchall()
            return devices
        except sqlite3.Error as error:
            print(error)
            return []

def get_devices_by_ip_range(connection, ip_range):
            """Retrieve devices filtered by IP range"""
            try:
                cursor = connection.cursor()
                cursor.execute("SELECT * FROM devices WHERE ip LIKE ?", (f"{ip_range}%",))
                devices = cursor.fetchall()
                return devices
            except sqlite3.Error as error:
                print(error)
                return []

def get_devices_sorted_by_ip(connection):
                """Retrieve all devices sorted by IP address"""
                try:
                    cursor = connection.cursor()

                    cursor.execute("SELECT * FROM devices ORDER BY ip ASC")
                    devices = cursor.fetchall()
                    return devices
                except sqlite3.Error as error:
                    print(error)
                    return []

def devices_by_vendor(connection, vendor):
                    """Retrieve devices filtered by vendor"""
                    try:
                        cursor = connection.cursor()
                        cursor.execute("SELECT * FROM devices WHERE vendor = ?", (vendor,))
                        devices = cursor.fetchall()
                        return devices
                    except sqlite3.Error as error:
                        print(error)
                        return []

def get_devices_by_ip(connection, ip):
                """Retrieve devices filtered by IP address"""
                try:
                    cursor = connection.cursor()
                    cursor.execute("SELECT * FROM devices WHERE ip = ?", (ip,))
                    devices = cursor.fetchall()
                    return devices
                except sqlite3.Error as error:
                    print(error)
                    return []

def get_devices_with_filters(connection, status=None, ip_range=None, vendor=None, hostname=None, mac=None):
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
                        cursor = connection.cursor()
                        cursor.execute(query, tuple(params))
                        devices = cursor.fetchall()
                        return devices
                    except sqlite3.Error as error:
                        print(error)
                        return []
                    
def get_devices_by_date(connection, start_date, end_date):
                        """Retrieve devices filtered by date range"""
                        try:
                            cursor = connection.cursor()
                            cursor.execute("select devices.* from devices join scans on devices.scan_id = scans.id where scans.timestamp between ? and ?", (start_date, end_date))
                            devices = cursor.fetchall()
                            return devices
                        except sqlite3.Error as error:
                            print(error)
                            return []  

def get_devices_by_subnet(connection, subnet):
                          """Retrieve devices filtered by subnet"""
                          if not is_valid_ip_range(subnet):
                              return []

                          try:
                                  cursor = connection.cursor()
                                  cursor.execute("select devices.* from devices join scans on devices.scan_id = scans.id where scans.ip_range LIKE ?", (f"{subnet}%",))
                                  devices = cursor.fetchall()
                                  return devices
                          except sqlite3.Error as error:
                                  print(error)
                                  return []         

def get_devices_by_hostname_regex(connection, pattern):
                                  """Retrieve devices filtered by hostname using regex"""
                                  try:   
                                      cursor = connection.cursor()
                                      cursor.execute("SELECT * FROM devices")
                                      devices = cursor.fetchall()
                                      regex = re.compile(pattern, re.IGNORECASE)
                                      filtered_devices = [device for device in devices if device[6] and regex.search(device[6])]
                                      return filtered_devices
                                  except sqlite3.Error as error:
                                      print(error)
                                      return []

                                  "network health score calculation"

def get_last_scan(connection, current_scan_id,ip_range):

        try:
                cursor = connection.cursor()
                cursor.execute(
                        """
                        select id  from scans
                        where ip_range = ?
                        and timestamp < (select timestamp from scans where id = ?)
                                         order by timestamp desc limit 1
                                         """, 
                                         (ip_range, current_scan_id)
                )
                row = cursor.fetchone()
                return row[0] if row else None
        except sqlite3.Error as error:
                print(error)
                return None

def solve_health_score(connection, scan_id, offline_status_values = ("offline", "down")):

        """Calculate the network health score for a given scan ID"""
        try:
                cursor = connection.cursor()
                cursor.execute("select ip_range from scans where id = ?", (scan_id,))
                row = cursor.fetchone()
                if not row:
                        return None
                ip_range = row[0]

                current_devices = get_devices_by_scan_id(connection, scan_id)
                current_macs = {device[3] for device in current_devices}

                previous_scan_id = get_last_scan(connection, scan_id, ip_range)
                if previous_scan_id:
                        last_devices = get_devices_by_scan_id(connection, previous_scan_id)
                        previous_macs = {device[3] for device in last_devices}

                else:
                                previous_macs = set()


                new_devices = len(current_macs - previous_macs)
                missing_devices = len(previous_macs - current_macs)
                unkwown_vendors = sum(1 for device in current_devices if not device[4])
                offline_devices = sum(1 for device in current_devices if device[5] in offline_status_values)

                total_devices = len(current_devices) or 1 

                penalty = (
                        (new_devices / total_devices) * 25
                        + (missing_devices / total_devices) * 25
                        + (unkwown_vendors / total_devices) * 25    
                        + (offline_devices / total_devices) * 25

                )

                score = max(0, round(100 - penalty, 2))

                return {
                        "score": score,
                        "new_devices": new_devices,
                        "missing_devices": missing_devices,
                        "unknown_vendors": unkwown_vendors,
                        "offline_devices": offline_devices
                }

        except sqlite3.Error as error:
                print(error)
                return None



def save_health_score(connection, scan_id, health_score_data):
        
        try:
                cursor = connection.cursor()
                cursor.execute(
                        """
                        insert into health_scores
                          (scan_id, score, new_devices, missing_devices, unknown_vendors, offline_devices)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                                scan_id,
                                health_score_data["score"],
                                health_score_data["new_devices"],
                                health_score_data["missing_devices"],
                                health_score_data["unknown_vendors"],
                                health_score_data["offline_devices"]
                        )
                )
                connection.commit()
                print(f"Health score saved for scan ID: {scan_id}")
                return cursor.lastrowid
        except sqlite3.Error as error:
                print(error)


def get_health_score(connection, scan_id):

        try:
              cursor = connection.cursor()
              cursor.execute("SELECT * FROM health_scores WHERE scan_id = ?", (scan_id,))
              row = cursor.fetchone()
        except sqlite3.Error as error:
                      print(error)
                      return None
                
                      

def get_health_trend(connection, start_date, end_date):
                        
                        try:
                                cursor = connection.cursor()
                                cursor.execute(

                        """


                        select scans.timestamp, health_scores.score, health_scores.new_devices, health_scores.missing_devices,
                          health_scores.unknown_vendors, health_scores.offline_devices
                          from health_scores
                          join scans  on health_scores.scan_id = scans.id
                          where scans.timestamp between ? and ?
                          order by scans.timestamp asc

                        """,
                        (start_date, end_date)

                        )
                                return cursor.fetchall()
                        except sqlite3.Error as error:
                                print(error)
                                return []