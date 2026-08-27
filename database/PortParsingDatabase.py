import sqlite3
import threading

class ParsePortsDb:
    def __init__(self, db_file = 'ports.db'):
        self.db_file = db_file
        self.conn = sqlite3.connect(self.db_file, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.lock = threading.Lock()

        self.cursor.execute('''CREATE TABLE IF NOT EXISTS open_ports ( 
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ip_address TEXT NOT NULL,
                port INTEGER NOT NULL,
                scan_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)
        ''')
        self.conn.commit()

    def InsertOpenPort(self, ip_address, port):
        with self.lock:
            self.cursor.execute('INSERT INTO open_ports (ip_address, port) VALUES (?, ?)',
        (ip_address, port)
        )
            self.conn.commit()

