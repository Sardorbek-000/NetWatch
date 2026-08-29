import queue          # --- FIX: work queue for the fixed worker pool ---
import socket
import threading

from database.PortParsingDatabase import ParsePortsDb


class PortScanner:
    def __init__(self, host, max_threads=100, timeout=0.5,
                 on_result=None, on_progress=None, on_done=None):
        self.host = host
        self.max_threads = max_threads
        self.timeout = timeout
        self.open_ports = []
        self.total_ports = 65535
        self.parse_ports_db = ParsePortsDb()

        self.on_result = on_result
        self.on_progress = on_progress
        self.on_done = on_done

        self._stop = threading.Event()
        self._scanned = 0
        self._lock = threading.Lock()

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
        if self.on_progress and scanned % 200 == 0:
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
        for port in range(1, self.total_ports + 1):
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


if __name__ == "__main__":
    ip = input("Enter ip address to scna:").strip()
    portScanner = PortScanner(ip, on_result=lambda p: print(f"Port {p} open"))
    portScanner.run()
    print("scan complited")
