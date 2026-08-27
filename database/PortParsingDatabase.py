import sqlite3

class ParsePortsDb:
    def __init__(self, db_file = 'ports.db'):
        self.db_file = db_file
        self.conn = sqlite3.connect(self.db_file)

