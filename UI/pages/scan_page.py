"""
NetWatch — Start Scanning page.

Threading model (read before touching this file): Tkinter is NOT
thread-safe. Scanning runs on a background thread (core.wireless_scanner's
design), so the scan-complete callback below NEVER touches a widget
directly. Instead it (1) saves to storage — safe from any thread, see
database/storage.py's _connect(), a fresh connection per call — then
(2) puts a message on a queue.Queue (thread-safe by design). The main
thread polls that queue every 200ms via self.after(...) and does all
actual widget updates there. Don't shortcut this pattern.

NOTE: `app: NetWatchApp` below is a type hint only — with
`from __future__ import annotations` it's never evaluated at runtime, so
NetWatchApp is deliberately NOT imported here. Importing it would create
UI.app -> UI.pages.scan_page -> UI.app, a circular import, since UI/app.py
is what imports this file in the first place.
"""

from __future__ import annotations

import queue
import threading
from datetime import datetime
from tkinter import messagebox

import customtkinter as ctk

from core.wireless_scanner import InsufficientPrivilegesError, LANScanner, WirelessScanner
from UI.theme import DANGER_COLOR, DANGER_HOVER_COLOR, NEW_DEVICE_COLOR


class ScanPage(ctk.CTkFrame):
    def __init__(self, parent, app: NetWatchApp) -> None:
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self.scanner: WirelessScanner | LANScanner | None = None
        self.result_queue: queue.Queue = queue.Queue()

        ctk.CTkLabel(self, text="Start Scanning", font=ctk.CTkFont(size=24, weight="bold")).pack(pady=(20, 10))

        controls = ctk.CTkFrame(self, fg_color="transparent")
        controls.pack(pady=10)

        ctk.CTkLabel(controls, text="Connection:").grid(row=0, column=0, padx=5, pady=5, sticky="e")
        self.conn_type = ctk.CTkSegmentedButton(controls, values=["Wi-Fi", "Wired"])
        self.conn_type.set("Wi-Fi")
        self.conn_type.grid(row=0, column=1, padx=5, pady=5, sticky="w")

        ctk.CTkLabel(controls, text="Interval (minutes):").grid(row=1, column=0, padx=5, pady=5, sticky="e")
        self.interval_entry = ctk.CTkEntry(controls, width=100)
        self.interval_entry.insert(0, "5")
        self.interval_entry.grid(row=1, column=1, padx=5, pady=5, sticky="w")

        ctk.CTkLabel(controls, text="Duration (hours, optional):").grid(row=2, column=0, padx=5, pady=5, sticky="e")
        self.duration_entry = ctk.CTkEntry(controls, width=100, placeholder_text="blank = forever")
        self.duration_entry.grid(row=2, column=1, padx=5, pady=5, sticky="w")

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(pady=10)
        self.scan_now_btn = ctk.CTkButton(btn_row, text="Scan Now", width=120, command=self._scan_now)
        self.scan_now_btn.pack(side="left", padx=8)
        self.start_interval_btn = ctk.CTkButton(btn_row, text="Start Interval", width=120, command=self._start_interval)
        self.start_interval_btn.pack(side="left", padx=8)
        self.stop_btn = ctk.CTkButton(
            btn_row, text="Stop", width=120, fg_color=DANGER_COLOR, hover_color=DANGER_HOVER_COLOR,
            command=self._stop, state="disabled",
        )
        self.stop_btn.pack(side="left", padx=8)

        self.status_label = ctk.CTkLabel(self, text="Idle.")
        self.status_label.pack(pady=(10, 2))
        self.new_device_banner = ctk.CTkLabel(self, text="", text_color=NEW_DEVICE_COLOR, font=ctk.CTkFont(weight="bold"))
        self.new_device_banner.pack(pady=2)

        self.results_frame = ctk.CTkScrollableFrame(self, width=760, height=260)
        self.results_frame.pack(pady=10, fill="both", expand=True)

        ctk.CTkButton(
            self, text="Back to Profile", fg_color="gray40", hover_color="gray30", command=self._back
        ).pack(pady=10)

        self._polling = False

    def on_show(self) -> None:
        self.status_label.configure(text="Idle.")
        self.new_device_banner.configure(text="")
        for child in self.results_frame.winfo_children():
            child.destroy()
        self._update_button_states()
        self._start_polling()

    def on_close(self) -> None:
        """Called by the app shell on window close — stop any background scan loop before exit."""
        if self.scanner is not None:
            self.scanner.stop_periodic_scan(wait_timeout=1.0)

    # ------------------------------------------------------------------ #
    # Scanner lifecycle
    # ------------------------------------------------------------------ #
    def _make_scanner(self):
        """
        Creates a scanner and wires its callback for THIS profile. The
        profile id is captured HERE (in the closure) rather than read
        from self.app.current_profile_id inside the callback later —
        that matters because the user could navigate to a DIFFERENT
        profile while this scanner's periodic loop is still running in
        the background; without capturing it now, a late-arriving scan
        from the old profile could get saved under the new profile's id.
        """
        cls = WirelessScanner if self.conn_type.get() == "Wi-Fi" else LANScanner
        scanner = cls()
        profile_id = self.app.current_profile_id
        scanner.register_callback(lambda devices, scan_time: self._on_scan_complete(scanner, profile_id, devices, scan_time))
        return scanner

    def _on_scan_complete(self, scanner, profile_id: int, devices, scan_time: datetime) -> None:
        """Runs on the SCANNER's background thread — no widget access here, see module docstring."""
        try:
            scan_id = self.app.storage.save_scan(devices, scan_time, profile_id, scanner.scan_type_label.lower(), scanner.subnet_cidr)
            new_devices = self.app.storage.get_new_devices_for_scan(scan_id)
        except Exception as exc:  # noqa: BLE001 — must not let this crash the background thread
            self.result_queue.put(("error", str(exc)))
            return
        self.result_queue.put(("scan_done", scan_id, devices, new_devices))

    def _scan_now(self) -> None:
        if self.scanner is None:
            self.scanner = self._make_scanner()
        self.status_label.configure(text="Scanning...")
        threading.Thread(target=self._run_scan_now, daemon=True).start()

    def _run_scan_now(self) -> None:
        """Runs scan_now() off the UI thread so a slow ARP sweep doesn't freeze the window."""
        try:
            self.scanner.scan_now()
        except InsufficientPrivilegesError as exc:
            self.result_queue.put(("error", str(exc)))

    def _start_interval(self) -> None:
        try:
            interval = float(self.interval_entry.get())
            if interval <= 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Invalid input", "Interval must be a positive number of minutes.")
            return

        duration_text = self.duration_entry.get().strip()
        duration: float | None = None
        if duration_text:
            try:
                duration = float(duration_text)
                if duration <= 0:
                    raise ValueError
            except ValueError:
                messagebox.showwarning("Invalid input", "Duration must be a positive number of hours, or left blank.")
                return

        if self.scanner is None or not self.scanner.is_running:
            self.scanner = self._make_scanner()

        self.scanner.start_periodic_scan(interval, duration)
        suffix = f" for {duration}h" if duration is not None else " (until stopped)"
        self.status_label.configure(text=f"Scanning every {interval} min{suffix}.")
        self._update_button_states()

    def _stop(self) -> None:
        if self.scanner is None:
            return
        # Don't block the UI thread here: a scan already in flight can
        # legitimately take up to timeout * (retry + 1) seconds to finish
        # (ARP retries). Do the wait on a background thread and let the
        # queue/poller finalize button state once it's genuinely done.
        self.status_label.configure(text="Stopping...")
        self.stop_btn.configure(state="disabled")
        threading.Thread(target=self._stop_worker, daemon=True).start()

    def _stop_worker(self) -> None:
        wait_timeout = self.scanner.timeout * (self.scanner.retry + 1) + 1.0
        self.scanner.stop_periodic_scan(wait_timeout=wait_timeout)
        self.result_queue.put(("stopped",))

    def _update_button_states(self) -> None:
        running = self.scanner is not None and self.scanner.is_running
        self.scan_now_btn.configure(state="disabled" if running else "normal")
        self.start_interval_btn.configure(state="disabled" if running else "normal")
        self.stop_btn.configure(state="normal" if running else "disabled")

    def _back(self) -> None:
        if self.scanner is not None:
            self.scanner.stop_periodic_scan(wait_timeout=1.0)
            self.scanner = None
        self.app.show_frame("ProfilePage")

    # ------------------------------------------------------------------ #
    # Queue polling (main thread) — the ONLY place this page touches widgets
    # based on scan results
    # ------------------------------------------------------------------ #
    def _start_polling(self) -> None:
        if self._polling:
            return
        self._polling = True
        self._poll_queue()

    def _poll_queue(self) -> None:
        try:
            while True:
                item = self.result_queue.get_nowait()
                self._handle_queue_item(item)
        except queue.Empty:
            pass
        if self.winfo_exists():
            self.after(200, self._poll_queue)
        else:
            self._polling = False

    def _handle_queue_item(self, item: tuple) -> None:
        kind = item[0]
        if kind == "stopped":
            self.status_label.configure(text="Stopped.")
            self._update_button_states()
        elif kind == "error":
            _, message = item
            self.status_label.configure(text=f"Error: {message}")
            self._update_button_states()
            messagebox.showerror("Scan error", message)
        elif kind == "scan_done":
            _, scan_id, devices, new_devices = item
            self.status_label.configure(text=f"Scan #{scan_id} complete — {len(devices)} device(s) found.")
            self._render_devices(devices, {d["mac"] for d in new_devices})
            if new_devices:
                macs = ", ".join(d["mac"] for d in new_devices)
                self.new_device_banner.configure(text=f"New device(s) found: {macs}")
            else:
                self.new_device_banner.configure(text="")
            self._update_button_states()

    def _render_devices(self, devices, new_macs: set[str]) -> None:
        for child in self.results_frame.winfo_children():
            child.destroy()
        for d in devices:
            row = ctk.CTkFrame(self.results_frame)
            row.pack(fill="x", pady=2, padx=2)
            is_new = d.mac in new_macs
            text = f"{d.ip:<15} {d.mac}   {d.vendor or 'Unknown'}   {d.hostname or '-'}" + ("  [NEW]" if is_new else "")
            color_kwargs = {"text_color": NEW_DEVICE_COLOR} if is_new else {}
            ctk.CTkLabel(row, text=text, **color_kwargs).pack(side="left", padx=5, pady=4)
            ctk.CTkButton(row, text="Rename", width=70, command=lambda mac=d.mac: self._rename(mac)).pack(
                side="right", padx=5, pady=4
            )

    def _rename(self, mac: str) -> None:
        dialog = ctk.CTkInputDialog(text=f"Custom name for {mac} (this profile only):", title="Rename Device")
        name = dialog.get_input()
        if name:
            self.app.storage.set_device_name(self.app.current_profile_id, mac, name)
