import sqlite3

class ParsePortsDb:
    def __init__(self, db_file = 'ports.db'):
        self.db_file = db_file
        self.conn = sqlite3.connect(self.db_file)
        self.cursor = self.conn.cursor()

        self.cursor.execute('''CREATE TABLE IF NOT EXISTS open_ports ( 
                id INTIGEER PRIMARY KEY AUTOINCRIMENT,
                ip_address TEXT NOT NULL,
                port INTEGER NOT NULL,
                scan_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        ''')
        self.conn.commit()

    def InsertOpenPort(self, ip_address, port):
        self.cursor.execute('INSERT INTO open_ports (ip_address, port, scan_timestamp) VALUES (?, ?, ?)',
    (ip_address, port)
    )
        self.conn.commit()

