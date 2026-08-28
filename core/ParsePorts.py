import socket
import threading

from database.PortParsingDatabase import ParsePortsDb


class PortScanner:
    def __init__(self, host , max_threads = 100, timeout = 0.5):
        self.host = host
        self.max_threads = max_threads
        self.timeout = timeout
        self.open_ports = []
        self.total_ports = 65535
        self.parse_ports_db = ParsePortsDb()

    def scan_port(self, port):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        result = sock.connect_ex((self.host, port))
        sock.close()
        if result == 0:
            self.open_ports.append(port)
            self.parse_ports_db.InsertOpenPort(self.host, port)
            print(f"Port {port} open")

    def run(self):
        threads = []
        for port in range(1, self.total_ports + 1):
            thread = threading.Thread(target = self.scan_port, args = (port,))
            threads.append(thread)
            thread.start()

            if len(threads) == self.max_threads:
                for t in threads:
                    t.join()
                threads = []

        for t in threads:
            t.join()
        threads = []
        print("scan complited")


if __name__ == "__main__":
    ip = input("Enter ip address to scna:").strip()
    portScanner = PortScanner(ip)
    portScanner.run()