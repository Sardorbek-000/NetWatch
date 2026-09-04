import queue          # --- FIX: work queue for the fixed worker pool ---
import socket
import threading

from database.PortParsingDatabase import ParsePortsDb


class PortScanner:
    COMMON_PORTS = sorted({
        20, 21, 22, 23, 25, 53, 67, 68, 69, 80, 110, 111, 119, 123, 135, 137,
        138, 139, 143, 161, 162, 179, 194, 389, 443, 445, 465, 514, 515, 587,
        631, 636, 989, 990, 993, 995, 1080, 1194, 1433, 1434, 1521, 1723,
        1900, 2049, 2082, 2083, 2181, 2375, 3000, 3128, 3306, 3389, 3690,
        4444, 5000, 5432, 5601, 5672, 5900, 5985, 5986, 6379, 6660, 6667,
        6881, 8000, 8008, 8080, 8081, 8443, 8888, 9000, 9090, 9200, 9300,
        9418, 10000, 11211, 15672, 27017, 27018, 32400,
    })

    def __init__(self, host, ports=None, max_threads=100, timeout=0.5,
                 on_result=None, on_progress=None, on_done=None):
        self.host = host
        self.ports = list(ports) if ports is not None else list(range(1, 65536))
        self.max_threads = max_threads
        self.timeout = timeout
        self.open_ports = []
        self.total_ports = len(self.ports)
        self.parse_ports_db = ParsePortsDb()

        self.on_result = on_result
        self.on_progress = on_progress
        self.on_done = on_done

        self._stop = threading.Event()
        self._scanned = 0
        self._lock = threading.Lock()
        self._progress_interval = max(1, self.total_ports // 50)

    def stop(self):
        self._stop.set()

    def scan_port(self, port):
        if self._stop.is_set():
            return

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        try:
            result = sock.connect_ex((self.host, port))
        except OSError:
            result = -1
        finally:
            sock.close()

        if result == 0:

            with self._lock:
                self.open_ports.append(port)
            self.parse_ports_db.InsertOpenPort(self.host, port)

            if self.on_result:
                self.on_result(port)

        with self._lock:
            self._scanned += 1
            scanned = self._scanned
        if self.on_progress and scanned % self._progress_interval == 0:
            self.on_progress(scanned, self.total_ports)

    def _worker(self, work):
        while not self._stop.is_set():
            try:
                port = work.get_nowait()
            except queue.Empty:
                return
            self.scan_port(port)

    def run(self):
        work = queue.Queue()
        for port in self.ports:
            work.put(port)

        workers = [
            threading.Thread(target=self._worker, args=(work,), daemon=True)
            for _ in range(self.max_threads)
        ]
        for w in workers:
            w.start()
        for w in workers:
            w.join()

        if self.on_progress:
            self.on_progress(self._scanned, self.total_ports)
        if self.on_done:
            self.on_done()


# if __name__ == "__main__":
#     ip = input("Enter ip address to scan: ").strip()
#     mode = input("Scan (c)ommon ports or (a)ll 65535? [c/a]: ").strip().lower()
#     ports = PortScanner.COMMON_PORTS if mode != "a" else None
#
#     portScanner = PortScanner(ip, ports=ports, on_result=lambda p: print(f"Port {p} open"))
#     portScanner.run()
#     print("scan complited")
