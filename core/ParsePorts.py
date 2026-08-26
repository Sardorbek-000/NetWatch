import socket
import threading


class PortScanner:
    def __init__(self, host, port, max_threads, timeout = 0.5):
        self.host = host
        self.port = port
        self.max_threads = max_threads
        self.timeout = timeout
        self.open_ports = []


