"""
NetWatch — Frontend (Presentation / Visualization Module)
============================================================

The full desktop app, per the architecture doc's menu structure:

    MAIN MENU: Settings, Add Profile, [enter existing profile]
    SETTINGS: Delete Profiles, Go back to menu
    ADD PROFILE: enter the profile Title
    PROFILE: Start Scanning, History, Manage Devices
        START SCANNING: connection type, Start Interval(n-minutes[, hours]), Scan Now
        HISTORY: View scan, Compare scans, Timeline Filters

Plus the two features layered on top of Modules 1/2:
    - Device naming: rename any device by its MAC, scoped to one profile
      (the MAC itself is always still shown, never hidden).
    - New device discovery: after every scan, devices never seen before
      in this profile's history are flagged and listed separately.

Run with:
    python3 app.py

Needs admin/root for actual scanning (raw ARP) — see wireless_scanner.py's
SETUP notes. The app itself still opens and lets you browse/manage without
elevated privileges; only "Scan Now" / "Start Interval" need it.

----------------------------------------------------------------------
THREADING MODEL (read this before touching ScanPage)
----------------------------------------------------------------------
Tkinter is NOT thread-safe — widgets must only be touched from the main
thread. Scanning runs on a background thread (Module 1's design), so the
scan-complete callback below NEVER updates a widget directly. Instead it:
  1. saves to storage (Storage is safe to call from any thread — see
     storage.py's _connect(), a fresh connection per call), then
  2. puts a small message on a queue.Queue (thread-safe by design).
The main thread polls that queue every 200ms via `self.after(...)` and
does all actual widget updates there. This is the standard safe pattern
for combining Tkinter with background threads — don't shortcut it.
"""

from __future__ import annotations

import queue
import threading
from datetime import datetime
from tkinter import messagebox

import customtkinter as ctk

from storage import Storage
from wireless_scanner import InsufficientPrivilegesError, LANScanner, WirelessScanner

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

NEW_DEVICE_COLOR = "#2ecc71"
DISCONNECTED_COLOR = "#e74c3c"
DANGER_COLOR = "#a83232"
DANGER_HOVER_COLOR = "#822424"


# =============================================================================
# App shell — owns shared state (storage, current profile) and page switching
# =============================================================================
class NetWatchApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("NetWatch")
        self.geometry("880x680")
        self.minsize(720, 560)

        self.storage = Storage("netwatch.db")
        self.current_profile_id: int | None = None
        self.current_profile_name: str | None = None

        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True)
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)

        self.frames: dict[str, ctk.CTkFrame] = {}
        for page_cls in (
            MainMenuPage,
            SettingsPage,
            AddProfilePage,
            ProfilePage,
            ScanPage,
            HistoryPage,
            ScanDetailPage,
            CompareScansPage,
            DeviceManagerPage,
        ):
            frame = page_cls(container, self)
            self.frames[page_cls.__name__] = frame
            frame.grid(row=0, column=0, sticky="nsew")

        self.show_frame("MainMenuPage")
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def show_frame(self, name: str, **kwargs) -> None:
        """Switches the visible page, calling that page's on_show(**kwargs) first, if it has one."""
        frame = self.frames[name]
        on_show = getattr(frame, "on_show", None)
        if on_show is not None:
            on_show(**kwargs)
        frame.tkraise()

    def _on_close(self) -> None:
        # Stop any scan loop still running in the background before exiting,
        # so we don't leave an orphaned thread trying to write to a database
        # whose process is gone.
        scan_page = self.frames.get("ScanPage")
        if isinstance(scan_page, ScanPage) and scan_page.scanner is not None:
            scan_page.scanner.stop_periodic_scan(wait_timeout=1.0)
        self.destroy()


# =============================================================================
# Main Menu — list profiles, Add Profile, Settings
# =============================================================================
class MainMenuPage(ctk.CTkFrame):
    def __init__(self, parent, app: NetWatchApp) -> None:
        super().__init__(parent, fg_color="transparent")
        self.app = app

        ctk.CTkLabel(self, text="NetWatch", font=ctk.CTkFont(size=30, weight="bold")).pack(pady=(30, 4))
        ctk.CTkLabel(self, text="Select a profile to enter, or create a new one.").pack(pady=(0, 20))

        self.profile_list = ctk.CTkScrollableFrame(self, width=560, height=320)
        self.profile_list.pack(pady=10)

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(pady=20)
        ctk.CTkButton(btn_row, text="+ Add Profile", width=160, command=lambda: app.show_frame("AddProfilePage")).pack(
            side="left", padx=10
        )
        ctk.CTkButton(btn_row, text="Settings", width=160, command=lambda: app.show_frame("SettingsPage")).pack(
            side="left", padx=10
        )

    def on_show(self) -> None:
        for child in self.profile_list.winfo_children():
            child.destroy()
        profiles = self.app.storage.list_profiles()
        if not profiles:
            ctk.CTkLabel(self.profile_list, text="No profiles yet — add one to get started.").pack(pady=10)
            return
        for p in profiles:
            row = ctk.CTkFrame(self.profile_list)
            row.pack(fill="x", pady=4, padx=4)
            ctk.CTkLabel(row, text=p["name"], font=ctk.CTkFont(size=16)).pack(side="left", padx=10, pady=8)
            ctk.CTkButton(
                row, text="Enter", width=80, command=lambda pid=p["id"], pname=p["name"]: self._enter(pid, pname)
            ).pack(side="right", padx=10, pady=8)

    def _enter(self, profile_id: int, profile_name: str) -> None:
        self.app.current_profile_id = profile_id
        self.app.current_profile_name = profile_name
        self.app.show_frame("ProfilePage")


# =============================================================================
# Settings — delete profiles
# =============================================================================
class SettingsPage(ctk.CTkFrame):
    def __init__(self, parent, app: NetWatchApp) -> None:
        super().__init__(parent, fg_color="transparent")
        self.app = app

        ctk.CTkLabel(self, text="Settings", font=ctk.CTkFont(size=26, weight="bold")).pack(pady=(30, 10))
        ctk.CTkLabel(self, text="Delete Profiles").pack(pady=(10, 5))

        self.list_frame = ctk.CTkScrollableFrame(self, width=560, height=320)
        self.list_frame.pack(pady=10)

        ctk.CTkButton(self, text="Back to Menu", width=160, command=lambda: app.show_frame("MainMenuPage")).pack(
            pady=20
        )

    def on_show(self) -> None:
        for child in self.list_frame.winfo_children():
            child.destroy()
        profiles = self.app.storage.list_profiles()
        if not profiles:
            ctk.CTkLabel(self.list_frame, text="No profiles to delete.").pack(pady=10)
            return
        for p in profiles:
            row = ctk.CTkFrame(self.list_frame)
            row.pack(fill="x", pady=4, padx=4)
            ctk.CTkLabel(row, text=p["name"]).pack(side="left", padx=10, pady=8)
            ctk.CTkButton(
                row,
                text="Delete",
                width=80,
                fg_color=DANGER_COLOR,
                hover_color=DANGER_HOVER_COLOR,
                command=lambda pid=p["id"], pname=p["name"]: self._confirm_delete(pid, pname),
            ).pack(side="right", padx=10, pady=8)

    def _confirm_delete(self, profile_id: int, name: str) -> None:
        if messagebox.askyesno("Delete Profile", f"Delete '{name}' and ALL of its scan history? This can't be undone."):
            self.app.storage.delete_profile(profile_id)
            self.on_show()


# =============================================================================
# Add Profile — enter a profile title
# =============================================================================
class AddProfilePage(ctk.CTkFrame):
    def __init__(self, parent, app: NetWatchApp) -> None:
        super().__init__(parent, fg_color="transparent")
        self.app = app

        ctk.CTkLabel(self, text="Add Profile", font=ctk.CTkFont(size=26, weight="bold")).pack(pady=(50, 20))
        ctk.CTkLabel(self, text="Profile title (e.g. Home, University)").pack()
        self.entry = ctk.CTkEntry(self, width=320, placeholder_text="Profile name")
        self.entry.pack(pady=10)
        self.entry.bind("<Return>", lambda _event: self._create())

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(pady=20)
        ctk.CTkButton(btn_row, text="Create", width=120, command=self._create).pack(side="left", padx=10)
        ctk.CTkButton(
            btn_row, text="Cancel", width=120, fg_color="gray40", hover_color="gray30",
            command=lambda: app.show_frame("MainMenuPage"),
        ).pack(side="left", padx=10)

    def on_show(self) -> None:
        self.entry.delete(0, "end")
        self.entry.focus()

    def _create(self) -> None:
        name = self.entry.get().strip()
        if not name:
            messagebox.showwarning("Missing name", "Please enter a profile name.")
            return
        self.app.storage.get_or_create_profile(name)
        self.app.show_frame("MainMenuPage")


# =============================================================================
# Profile — the hub for one Location Profile
# =============================================================================
class ProfilePage(ctk.CTkFrame):
    def __init__(self, parent, app: NetWatchApp) -> None:
        super().__init__(parent, fg_color="transparent")
        self.app = app

        self.title_label = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=28, weight="bold"))
        self.title_label.pack(pady=(50, 30))

        ctk.CTkButton(self, text="Start Scanning", width=260, height=45, command=lambda: app.show_frame("ScanPage")).pack(
            pady=10
        )
        ctk.CTkButton(self, text="History", width=260, height=45, command=lambda: app.show_frame("HistoryPage")).pack(
            pady=10
        )
        ctk.CTkButton(
            self, text="Manage Devices", width=260, height=45, command=lambda: app.show_frame("DeviceManagerPage")
        ).pack(pady=10)
        ctk.CTkButton(
            self, text="Back to Menu", width=260, fg_color="gray40", hover_color="gray30",
            command=lambda: app.show_frame("MainMenuPage"),
        ).pack(pady=(30, 10))

    def on_show(self) -> None:
        self.title_label.configure(text=self.app.current_profile_name or "")


# =============================================================================
# Start Scanning — connection type, interval/duration, Scan Now, live results
# =============================================================================
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

    # ------------------------------------------------------------------ #
    # Scanner lifecycle
    # ------------------------------------------------------------------ #
    def _make_scanner(self):
        """
        Creates a scanner and wires its callback for THIS profile. The
        profile id/name are captured here (in the closure) rather than
        read from self.app.current_profile_id inside the callback later —
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
        # (ARP retries), which is longer than we'd want to freeze the
        # window for. Do the wait on a background thread and let the
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


# =============================================================================
# History — timeline, View scan, Compare scans
# =============================================================================
class HistoryPage(ctk.CTkFrame):
    def __init__(self, parent, app: NetWatchApp) -> None:
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self.selected_for_compare: list[int] = []

        ctk.CTkLabel(self, text="History", font=ctk.CTkFont(size=24, weight="bold")).pack(pady=(20, 10))

        filter_row = ctk.CTkFrame(self, fg_color="transparent")
        filter_row.pack(pady=5)
        ctk.CTkLabel(filter_row, text="From (YYYY-MM-DD):").grid(row=0, column=0, padx=5)
        self.start_entry = ctk.CTkEntry(filter_row, width=120)
        self.start_entry.grid(row=0, column=1, padx=5)
        ctk.CTkLabel(filter_row, text="To (YYYY-MM-DD):").grid(row=0, column=2, padx=5)
        self.end_entry = ctk.CTkEntry(filter_row, width=120)
        self.end_entry.grid(row=0, column=3, padx=5)
        ctk.CTkButton(filter_row, text="Filter", width=80, command=self._load_history).grid(row=0, column=4, padx=5)
        ctk.CTkButton(filter_row, text="Clear", width=80, command=self._clear_filter).grid(row=0, column=5, padx=5)

        self.list_frame = ctk.CTkScrollableFrame(self, width=780, height=300)
        self.list_frame.pack(pady=10, fill="both", expand=True)

        self.compare_status = ctk.CTkLabel(self, text="Select up to two scans (checkboxes) to compare.")
        self.compare_status.pack(pady=5)

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(pady=10)
        ctk.CTkButton(btn_row, text="Compare Selected", width=160, command=self._compare).pack(side="left", padx=10)
        ctk.CTkButton(
            btn_row, text="Back to Profile", width=160, fg_color="gray40", hover_color="gray30",
            command=lambda: app.show_frame("ProfilePage"),
        ).pack(side="left", padx=10)

    def on_show(self) -> None:
        self.selected_for_compare = []
        self.start_entry.delete(0, "end")
        self.end_entry.delete(0, "end")
        self.compare_status.configure(text="Select up to two scans (checkboxes) to compare.")
        self._load_history()

    def _clear_filter(self) -> None:
        self.start_entry.delete(0, "end")
        self.end_entry.delete(0, "end")
        self._load_history()

    def _parse_date(self, text: str, end_of_day: bool = False) -> datetime | None:
        text = text.strip()
        if not text:
            return None
        try:
            dt = datetime.strptime(text, "%Y-%m-%d")
        except ValueError:
            messagebox.showwarning("Invalid date", f"'{text}' isn't in YYYY-MM-DD format.")
            return None
        return dt.replace(hour=23, minute=59, second=59) if end_of_day else dt

    def _load_history(self) -> None:
        for child in self.list_frame.winfo_children():
            child.destroy()
        start = self._parse_date(self.start_entry.get())
        end = self._parse_date(self.end_entry.get(), end_of_day=True)
        history = self.app.storage.get_scan_history(self.app.current_profile_id, start, end)
        if not history:
            ctk.CTkLabel(self.list_frame, text="No scans in this range.").pack(pady=10)
            return
        for s in reversed(history):  # newest first
            row = ctk.CTkFrame(self.list_frame)
            row.pack(fill="x", pady=2, padx=2)
            var = ctk.BooleanVar(value=(s["id"] in self.selected_for_compare))
            ctk.CTkCheckBox(
                row, text="", width=20, variable=var, command=lambda sid=s["id"], v=var: self._toggle_compare(sid, v)
            ).pack(side="left", padx=5)
            ctk.CTkLabel(
                row, text=f"#{s['id']}   {s['scan_time']}   {s['scan_type']}   {s['device_count']} device(s)"
            ).pack(side="left", padx=5)
            ctk.CTkButton(row, text="View", width=70, command=lambda sid=s["id"]: self.app.show_frame("ScanDetailPage", scan_id=sid)).pack(
                side="right", padx=5
            )

    def _toggle_compare(self, scan_id: int, var) -> None:
        if var.get():
            if len(self.selected_for_compare) >= 2:
                var.set(False)
                messagebox.showinfo("Limit reached", "You can only compare two scans at a time.")
                return
            self.selected_for_compare.append(scan_id)
        elif scan_id in self.selected_for_compare:
            self.selected_for_compare.remove(scan_id)
        self.compare_status.configure(text=f"Selected: {self.selected_for_compare or 'none'}")

    def _compare(self) -> None:
        if len(self.selected_for_compare) != 2:
            messagebox.showwarning("Select two scans", "Please select exactly two scans to compare.")
            return
        scan_a, scan_b = sorted(self.selected_for_compare)  # lower id = earlier scan
        self.app.show_frame("CompareScansPage", scan_id_a=scan_a, scan_id_b=scan_b)


# =============================================================================
# View Scan — full device list for one scan, with NEW badges + rename
# =============================================================================
class ScanDetailPage(ctk.CTkFrame):
    def __init__(self, parent, app: NetWatchApp) -> None:
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self.scan_id: int | None = None

        self.title_label = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=22, weight="bold"))
        self.title_label.pack(pady=(20, 10))

        self.list_frame = ctk.CTkScrollableFrame(self, width=780, height=380)
        self.list_frame.pack(pady=10, fill="both", expand=True)

        ctk.CTkButton(
            self, text="Back to History", fg_color="gray40", hover_color="gray30",
            command=lambda: app.show_frame("HistoryPage"),
        ).pack(pady=10)

    def on_show(self, scan_id: int) -> None:
        self.scan_id = scan_id
        self.title_label.configure(text=f"Scan #{scan_id}")
        self._load()

    def _load(self) -> None:
        for child in self.list_frame.winfo_children():
            child.destroy()
        devices = self.app.storage.get_devices_for_scan(self.scan_id)
        new_macs = {d["mac"] for d in self.app.storage.get_new_devices_for_scan(self.scan_id)}
        if not devices:
            ctk.CTkLabel(self.list_frame, text="No devices recorded for this scan.").pack(pady=10)
            return
        for d in devices:
            row = ctk.CTkFrame(self.list_frame)
            row.pack(fill="x", pady=2, padx=2)
            name_suffix = f" — {d['custom_name']}" if d["custom_name"] else ""
            is_new = d["mac"] in new_macs
            text = (
                f"{d['ip']:<15} {d['mac']}{name_suffix}   {d['vendor'] or 'Unknown'}   {d['hostname'] or '-'}"
                + ("  [NEW]" if is_new else "")
            )
            color_kwargs = {"text_color": NEW_DEVICE_COLOR} if is_new else {}
            ctk.CTkLabel(row, text=text, **color_kwargs).pack(side="left", padx=5, pady=4)
            ctk.CTkButton(row, text="Rename", width=70, command=lambda mac=d["mac"]: self._rename(mac)).pack(
                side="right", padx=5, pady=4
            )

    def _rename(self, mac: str) -> None:
        dialog = ctk.CTkInputDialog(text=f"Custom name for {mac} (this profile only):", title="Rename Device")
        name = dialog.get_input()
        if name:
            self.app.storage.set_device_name(self.app.current_profile_id, mac, name)
            self._load()


# =============================================================================
# Compare Scans — new / disconnected / still-connected devices between two scans
# =============================================================================
class CompareScansPage(ctk.CTkFrame):
    def __init__(self, parent, app: NetWatchApp) -> None:
        super().__init__(parent, fg_color="transparent")
        self.app = app

        self.title_label = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=22, weight="bold"))
        self.title_label.pack(pady=(20, 10))

        self.content_frame = ctk.CTkScrollableFrame(self, width=780, height=420)
        self.content_frame.pack(pady=10, fill="both", expand=True)

        ctk.CTkButton(
            self, text="Back to History", fg_color="gray40", hover_color="gray30",
            command=lambda: app.show_frame("HistoryPage"),
        ).pack(pady=10)

    def on_show(self, scan_id_a: int, scan_id_b: int) -> None:
        self.title_label.configure(text=f"Compare: Scan #{scan_id_a} -> Scan #{scan_id_b}")
        for child in self.content_frame.winfo_children():
            child.destroy()

        diff = self.app.storage.compare_scans(scan_id_a, scan_id_b)
        self._add_section("New Devices", diff["new_devices"], NEW_DEVICE_COLOR)
        self._add_section("Disconnected Devices", diff["disconnected_devices"], DISCONNECTED_COLOR)
        self._add_section("Still Connected", diff["common_devices"], None)

    def _add_section(self, title: str, devices: list[dict], color: str | None) -> None:
        ctk.CTkLabel(self.content_frame, text=f"{title} ({len(devices)})", font=ctk.CTkFont(size=16, weight="bold")).pack(
            anchor="w", pady=(12, 4)
        )
        if not devices:
            ctk.CTkLabel(self.content_frame, text="  (none)").pack(anchor="w")
            return
        for d in devices:
            name_suffix = f" — {d['custom_name']}" if d.get("custom_name") else ""
            text = f"  {d['ip']:<15} {d['mac']}{name_suffix}   {d['vendor'] or 'Unknown'}"
            color_kwargs = {"text_color": color} if color else {}
            ctk.CTkLabel(self.content_frame, text=text, **color_kwargs).pack(anchor="w")


# =============================================================================
# Manage Devices — every device ever seen in this profile, rename any of them
# =============================================================================
class DeviceManagerPage(ctk.CTkFrame):
    def __init__(self, parent, app: NetWatchApp) -> None:
        super().__init__(parent, fg_color="transparent")
        self.app = app

        ctk.CTkLabel(self, text="Manage Devices", font=ctk.CTkFont(size=24, weight="bold")).pack(pady=(20, 6))
        ctk.CTkLabel(self, text="Every device ever seen in this profile. Rename any of them below.").pack(pady=(0, 10))

        self.list_frame = ctk.CTkScrollableFrame(self, width=780, height=420)
        self.list_frame.pack(pady=10, fill="both", expand=True)

        ctk.CTkButton(
            self, text="Back to Profile", fg_color="gray40", hover_color="gray30",
            command=lambda: app.show_frame("ProfilePage"),
        ).pack(pady=10)

    def on_show(self) -> None:
        self._load()

    def _load(self) -> None:
        for child in self.list_frame.winfo_children():
            child.destroy()
        devices = self.app.storage.get_all_known_devices(self.app.current_profile_id)
        if not devices:
            ctk.CTkLabel(self.list_frame, text="No devices seen yet — run a scan first.").pack(pady=10)
            return
        for d in devices:
            row = ctk.CTkFrame(self.list_frame)
            row.pack(fill="x", pady=2, padx=2)
            name_suffix = f"  ({d['custom_name']})" if d["custom_name"] else ""
            text = f"{d['mac']}{name_suffix}   last IP: {d['ip']}   {d['vendor'] or 'Unknown'}   last seen: {d['last_seen']}"
            ctk.CTkLabel(row, text=text).pack(side="left", padx=5, pady=4)
            ctk.CTkButton(row, text="Rename", width=70, command=lambda mac=d["mac"]: self._rename(mac)).pack(
                side="right", padx=5, pady=4
            )

    def _rename(self, mac: str) -> None:
        dialog = ctk.CTkInputDialog(text=f"Custom name for {mac} (this profile only):", title="Rename Device")
        name = dialog.get_input()
        if name:
            self.app.storage.set_device_name(self.app.current_profile_id, mac, name)
            self._load()


if __name__ == "__main__":
    app = NetWatchApp()
    app.mainloop()
