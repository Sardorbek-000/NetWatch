"""
NetWatch — Port Scan page.

Threading model (same shape as scan_page.py): the actual port-connect
attempts run on a daemon background thread via PortScanner.run(). That
thread never touches a ctk widget directly (Tkinter isn't thread-safe)
— it only pushes tuples onto self.events, a thread-safe queue.Queue.
The main thread polls that queue every 100ms via self.after(...) and
does all widget updates AND the Storage write there, so every touch of
app state happens on one thread.
"""

from __future__ import annotations

import ipaddress
import queue
import socket
import threading

import customtkinter as ctk

from core.ParsePorts import PortScanner
from UI.notifier import notify


class PortScanPage(ctk.CTkFrame):
    def __init__(self, parent, app) -> None:
        super().__init__(parent, fg_color="transparent")
        self.app = app

        self.scanner = None          # built lazily in start_scan(), None means "no scan in progress"
        self.events = queue.Queue()  # cross-thread handoff: background thread produces, _drain_events() consumes

        ctk.CTkLabel(self, text="Scan for open Ports", font=ctk.CTkFont(size=24, weight="bold")).pack(pady=(20, 10))

        self.ip_entry = ctk.CTkEntry(self, width=260, placeholder_text="IP address")
        self.ip_entry.pack(pady=10)

        self.scan_mode = ctk.CTkSegmentedButton(self, values=["Common Ports", "All Ports (1-65535)"])
        self.scan_mode.set("Common Ports")
        self.scan_mode.pack(pady=10)

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(pady=10)
        self.scan_btn = ctk.CTkButton(btn_row, text="Start Scan", width=140, command=self.start_scan)
        self.scan_btn.pack(side="left", padx=5)
        self.stop_btn = ctk.CTkButton(btn_row, text="Stop", width=100, command=self.stop_scan, state="disabled")
        self.stop_btn.pack(side="left", padx=5)

        self.back_btn = ctk.CTkButton(
            self, text="Back to Profile", width=220, command=lambda: app.show_frame("ProfilePage")
        )
        self.back_btn.pack(pady=10)

        self.progress = ctk.CTkProgressBar(self, width=260)
        self.progress.set(0)
        self.progress.pack(pady=(10, 4))
        self.status = ctk.CTkLabel(self, text="")
        self.status.pack()

        self.results = ctk.CTkScrollableFrame(self, width=300, height=140, label_text="Open ports")
        self.results.pack(pady=(10, 4), fill="both", expand=True)

        self.previous_frame = ctk.CTkScrollableFrame(self, width=300, height=140, label_text="Previous results")
        self.previous_frame.pack(pady=(4, 10), fill="both", expand=True)

    def on_show(self) -> None:
        self._load_previous_results()

    def on_close(self) -> None:
        """Called by the app shell on window close — stop a scan in progress before exit."""
        if self.scanner is not None:
            self.scanner.stop()

    # ------------------------------------------------------------------ #
    # Scan lifecycle
    # ------------------------------------------------------------------ #
    def start_scan(self) -> None:
        host = self.ip_entry.get().strip()
        if self.scanner is not None:
            return
        try:
            ipaddress.ip_address(host)
        except ValueError:
            self.status.configure(text=f"'{host}' isn't a valid IP address.")
            return

        notify("Port scanning", "started port scanning")
        for w in self.results.winfo_children():
            w.destroy()
        self.progress.set(0)
        self.status.configure(text="Scanning...")
        self.scan_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")

        ports = PortScanner.COMMON_PORTS if self.scan_mode.get() == "Common Ports" else None
        self.scanner = PortScanner(
            host,
            ports=ports,
            # These three callbacks all run on the background thread started
            # below — that's why they only ever call self.events.put(...)
            # and never touch a ctk widget or Storage directly.
            on_result=lambda p: self.events.put(("port", p)),
            on_progress=lambda done, total: self.events.put(("progress", done / total)),
            on_done=lambda: self.events.put(("done", None)),
        )
        threading.Thread(target=self.scanner.run, daemon=True).start()
        self.after(100, self._drain_events)  # start polling self.events on the main/UI thread

    def stop_scan(self) -> None:
        if self.scanner is not None:
            self.scanner.stop()
            self.status.configure(text="Stopping...")
            self.stop_btn.configure(state="disabled")

    # ------------------------------------------------------------------ #
    # Queue polling (main thread) — the ONLY place this page touches
    # widgets or Storage based on scan results
    # ------------------------------------------------------------------ #
    def _drain_events(self) -> None:
        latest_progress = None
        processed = 0
        try:
            while processed < 500:
                kind, value = self.events.get_nowait()
                processed += 1
                if kind == "port":
                    self._add_port_row(value)
                    self.app.storage.save_open_port(self.app.current_profile_id, self.ip_entry.get().strip(), value)
                elif kind == "progress":
                    latest_progress = value  # only keep the newest — no point drawing 40 intermediate progress bars
                elif kind == "done":
                    self.progress.set(1)
                    self._scan_finished()
                    return  # scan over — stop polling, don't reschedule
        except queue.Empty:
            pass
        if latest_progress is not None:
            self.progress.set(latest_progress)
        self.after(100, self._drain_events)

    def _add_port_row(self, port) -> None:
        try:
            service = socket.getservbyport(port)
        except OSError:
            service = "unknown"
        ctk.CTkLabel(self.results, text=f"{port:>6}   {service}", font=ctk.CTkFont(family="monospace")).pack(anchor="w")

    def _scan_finished(self) -> None:
        count = len(self.results.winfo_children())
        notify("Port scanning", "Port scanning has finished")
        self.status.configure(text=f"Scan complete - {count} open port(s)")
        self.progress.set(1)
        self.scan_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        self.scanner = None
        self._load_previous_results()

    def _load_previous_results(self) -> None:
        for w in self.previous_frame.winfo_children():
            w.destroy()
        for row in self.app.storage.get_open_ports(self.app.current_profile_id):
            ctk.CTkLabel(
                self.previous_frame,
                text=f"{row['ip']:<15} {row['port']:>6}   {row['scan_time']}",
                font=ctk.CTkFont(family="monospace"),
            ).pack(anchor="w")
