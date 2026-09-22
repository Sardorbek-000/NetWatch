"""
NetWatch — Frontend (Module 3)
================================================================
The CustomTkinter desktop app: the NetWatchApp shell, plus every screen
that isn't split into its own UI/pages/*.py file yet (currently just
PortScan). Talks to the database only through database/storage.py's
Storage class — no SQL lives in this file.

----------------------------------------------------------------------
HOW TO RUN
----------------------------------------------------------------------
    From the repo root (NOT from inside UI/), with the venv active:

        python -m UI.app

    Running `python UI/app.py` directly instead can break the
    `from core...` / `from database...` imports below, since Python
    then treats UI/ itself as the top-level folder instead of the repo
    root. netwatch.db is created next to wherever the process's working
    directory is — run from the repo root so every screen/dev opens the
    same database file.

----------------------------------------------------------------------
HOW THE SCREENS FIT TOGETHER
----------------------------------------------------------------------
NetWatchApp builds every page in PAGES once, stacks them on top of each
other with .place(), and keys them by class name in self.frames (e.g.
self.frames["MainMenuPage"]). Nothing is rebuilt on navigation — there's
no per-profile Profile instance like the old build; ProfilePage instead
reads self.app.current_profile_id/current_profile_name, which
MainMenuPage.enter_profile() sets right before navigating there.

self.show_frame(name, **kwargs) is how every screen navigates: it looks
up self.frames[name], calls that frame's on_show(**kwargs) if it has one,
then raises it. on_show is this codebase's "screen became visible" hook
(CustomTkinter has no built-in event for that) — pages that show
database-backed data (profile lists, the profile hub's title) requery
Storage there instead of caching stale data across navigations.

self._on_close() is wired to the window's close button
(WM_DELETE_WINDOW) and calls on_close() on every frame that defines
one, before destroying the window — the hook a page would use to stop
any background work (e.g. a running scan thread) on exit.
"""

import queue
import socket
import threading

import customtkinter as ctk
from core.ParsePorts import PortScanner
from UI.notifier import notify
from UI.pages.add_profile_page import AddProfilePage
from UI.pages.main_menu_page import MainMenuPage
from UI.pages.settings_page import SettingsPage
from UI.pages.profile_page import ProfilePage
from database.storage import Storage
from UI.pages.scan_page import ScanPage
from UI.pages.history_page import HistoryPage
from UI.pages.scan_detail_page import ScanDetailPage
from UI.pages.compare_scans_page import CompareScansPage
from UI.pages.device_manager_page import DeviceManagerPage

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class NetWatchApp(ctk.CTk):
    """The app shell/window. Owns the one shared Storage instance and the in-memory profile cache every screen reads."""

    def __init__(self):
        super().__init__()

        self.title("NetWatch")
        self.geometry("900x600")
        self.minsize(640, 420)

        self.storage = Storage("netwatch.db")
        self.current_profile_id = None
        self.current_profile_name = None

        PAGES = [
    MainMenuPage, SettingsPage, AddProfilePage, PortScan, ProfilePage,
    ScanPage, HistoryPage, ScanDetailPage, CompareScansPage, DeviceManagerPage,
]
        self.container = ctk.CTkFrame(self, fg_color="transparent")
        self.container.pack(fill="both", expand=True, padx=20, pady=20)

        self.frames = {}
        for Frame in PAGES:
            frame = Frame(self.container, self)
            self.frames[Frame.__name__] = frame
            frame.place(relx=0, rely=0, relwidth=1, relheight=1)

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.show_frame("MainMenuPage")

    def show_frame(self, name, **kwargs):
        frame = self.frames[name]
        on_show = getattr(frame, "on_show", None)
        if on_show is not None:
            on_show(**kwargs)
        frame.tkraise()

    def _on_close(self):
        for frame in self.frames.values():
            on_close = getattr(frame, "on_close", None)
            if on_close is not None:
                on_close()
        self.destroy()




class PortScan(ctk.CTkFrame):
    """
    Scans one IP's ports. This is the reference pattern (also used by
    Profile's scanning) for running slow/blocking work without freezing
    the UI: the scan itself runs on a daemon background thread; that
    thread never touches ctk widgets directly (Tkinter isn't thread-safe)
    — it only pushes plain tuples onto self.events. self.after(100, ...)
    polls that queue back on the MAIN thread, which is the only thread
    allowed to update widgets.
    """

    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app

        self.scanner = None          # built lazily in start_scan(), None means "no scan in progress"
        self.events = queue.Queue()  # cross-thread handoff: background thread produces, _drain_events() consumes

        ctk.CTkLabel(self, text="Scan for open Ports", font=ctk.CTkFont(size=24, weight="bold")).pack(pady=(40, 20))

        self.ip_entry = ctk.CTkEntry(self, width=260, placeholder_text="IP address")
        self.ip_entry.pack(pady=10)

        self.scan_mode = ctk.CTkSegmentedButton(self, values=["Common Ports", "All Ports (1-65535)"])
        self.scan_mode.set("Common Ports")
        self.scan_mode.pack(pady=10)

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(pady=10)

        self.scan_btn = ctk.CTkButton(btn_row, text="Start Scan", width=140,
                                      command=self.start_scan)
        self.scan_btn.pack(side="left", padx=5)
        self.stop_btn = ctk.CTkButton(btn_row, text="Stop", width=100,
                                      command=self.stop_scan, state="disabled")
        self.stop_btn.pack(side="left", padx=5)

        self.main_menu_btn = ctk.CTkButton(self, text="Go Back to Menu", width=220,
                                           command=lambda: app.show_frame(MainMenu))
        self.main_menu_btn.pack(pady=10)

        self.progress = ctk.CTkProgressBar(self, width=260)
        self.progress.set(0)
        self.progress.pack(pady=(10, 4))
        self.status = ctk.CTkLabel(self, text="")
        self.status.pack()

        self.results = ctk.CTkScrollableFrame(self, width=300, height=180,
                                              label_text="Open ports")
        self.results.pack(pady=10, fill="both", expand=True)


    def start_scan(self):
        host = self.ip_entry.get().strip()
        if not host or self.scanner is not None:
            return
        notify("Port scanning", "started port scanning")
        for w in self.results.winfo_children():
            w.destroy()
        self.progress.set(0)
        self.status.configure(text="Scanning...")
        self.scan_btn.configure(state="disabled")
        # self.main_menu_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")

        ports = PortScanner.COMMON_PORTS if self.scan_mode.get() == "Common Ports" else None
        self.scanner = PortScanner(
            host,
            ports=ports,
            # These three callbacks all run on the background thread started
            # below — that's why they only ever call self.events.put(...)
            # and never touch a ctk widget directly.
            on_result=lambda p: self.events.put(("port", p)),
            on_progress=lambda done, total: self.events.put(("progress", done / total)),
            on_done=lambda: self.events.put(("done", None)),
        )
        threading.Thread(target=self.scanner.run, daemon=True).start()
        self.after(100, self._drain_events)  # start polling self.events on the main/UI thread

    def stop_scan(self):
        if self.scanner is not None:
            self.scanner.stop()
            self.status.configure(text="Stopping...")
            self.stop_btn.configure(state="disabled")

    def _drain_events(self):
        """
        Runs on the main/UI thread (scheduled via self.after). Drains
        whatever's queued up so far, then reschedules itself — this is
        the polling loop that turns background-thread events into safe
        widget updates. The 500-item cap per call just bounds how long one
        call can run if a fast scan floods the queue between polls; it
        picks back up next tick via the recursive self.after() below.
        """
        latest_progress = None
        processed = 0
        try:
            while processed < 500:
                kind, value = self.events.get_nowait()
                processed += 1
                if kind == "port":
                    self._add_port_row(value)
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

    def _add_port_row(self, port):
        try:
            service = socket.getservbyport(port)
        except OSError:
            service = "unknown"
        ctk.CTkLabel(self.results, text=f"{port:>6}   {service}",
                     font=ctk.CTkFont(family="monospace")).pack(anchor="w")

    def _scan_finished(self):
        count = len(self.results.winfo_children())
        notify("Port scanning", "Port scanning has finished")
        self.status.configure(text=f"Scan complete - {count} open port(s)")
        self.progress.set(1)
        self.scan_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        self.scanner = None



if __name__ == "__main__":
    app = NetWatchApp()
    app.mainloop()