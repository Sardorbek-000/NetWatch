import sqlite3 


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
cursor = connection.cursor()

def create_tables(connection):
    """ create tables in the SQLite database """
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS scans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL
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

