"""
NetWatch — Frontend (Module 3)
================================================================
The CustomTkinter desktop app: every screen (Main Menu, Add Profile,
Settings, Profile, Port Scan) plus the NetWatchApp shell that switches
between them. Talks to the database only through database/storage.py's
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
NetWatchApp creates ALL of MainMenu/Settings/AddProfile/PortScan once,
stacks them on top of each other with .place(), and show_frame() just
raises the one that should be on top (self.frames[frame_class].tkraise()).
Profile is the odd one out: a new instance is built every time you enter
a profile (open_profile()) because, unlike the others, it needs data
(profile id/name) at construction time.

Any screen that shows data pulled from the database (profile lists,
scan results) refreshes it in an overridden tkraise() — CustomTkinter
doesn't have a built-in "screen became visible" event, so overriding
tkraise() is this codebase's way of hooking that moment.
"""

import queue
import socket
import threading

import customtkinter as ctk
from core.ParsePorts import PortScanner
from UI.notifier import notify
from UI.pages.add_profile_page import AddProfilePage
from UI.pages.main_menu_page import MainMenuPage
from database.storage import Storage


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

        PAGES = [MainMenuPage, Settings, AddProfilePage, PortScan]
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



class Settings(ctk.CTkFrame):
    """Multi-select delete screen for profiles. Selection state (self.selected/self.profile_buttons) is keyed by profile id, not name — names aren't guaranteed unique-forever the way an id is."""

    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self.selected = set()          # profile ids currently checked for deletion
        self.profile_buttons = {}      # profile id -> its CTkButton, so toggle_profile can recolor it

        ctk.CTkLabel(self, text="Settings", font=ctk.CTkFont(size=24, weight="bold")).pack(pady=(40, 20))

        self.profile_list = ctk.CTkScrollableFrame(self, width=260, height=220, label_text="Profiles")
        self.profile_list.pack(pady=10)

        self.delete_btn = ctk.CTkButton(self, text="Delete Selected", width=220, fg_color="darkred",
                                        hover_color="#8b0000", state="disabled",
                                        command=self.delete_selected)
        self.delete_btn.pack(pady=10)
        ctk.CTkButton(self, text="Go Back to Menu", width=220,
                      command=lambda: app.show_frame(MainMenu)).pack(pady=10)

    def refresh_profiles(self):
        """Rebuilds the checklist from self.app.profiles. Does NOT itself re-query the DB — call self.app.refresh_profiles() first if the cache might be stale (see delete_selected())."""
        for widget in self.profile_list.winfo_children():
            widget.destroy()
        self.selected.clear()
        self.profile_buttons.clear()
        self.delete_btn.configure(state="disabled")
        for profile in self.app.profiles:
            btn = ctk.CTkButton(self.profile_list, text=profile["name"], width=220,
                                fg_color="transparent", border_width=1,
                                command=lambda p=profile: self.toggle_profile(p["id"]))
            btn.pack(pady=5)
            self.profile_buttons[profile["id"]] = btn

    def toggle_profile(self, profile_id):
        btn = self.profile_buttons[profile_id]
        if profile_id in self.selected:
            self.selected.remove(profile_id)
            btn.configure(fg_color="transparent")
        else:
            self.selected.add(profile_id)
            btn.configure(fg_color="darkred")
        self.delete_btn.configure(state="normal" if self.selected else "disabled")

    def delete_selected(self):
        for profile_id in self.selected:
            self.app.storage.delete_profile(profile_id)   # cascades to that profile's scans/scan_devices/device_labels too
        self.app.refresh_profiles()   # sync the shared NetWatchApp.profiles cache with the DB first...
        self.refresh_profiles()       # ...THEN redraw this screen's buttons from it, or you'd redraw the stale list

    def tkraise(self, *args):
        super().tkraise(*args)
        self.refresh_profiles()

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

class Profile(ctk.CTkFrame):
    """
    Hub for one Location Profile (e.g. "Home"). A fresh instance is built
    every time open_profile() runs, unlike the other screens which are
    built once — that's how it receives which profile it's showing.

    "Start Scanning" and "History" have no command= yet — scanning needs
    the same background-thread/queue pattern as PortScan above (network
    scans are blocking calls too), just wired up to WirelessScanner/
    LANScanner + Storage.save_scan() instead of PortScanner. Not
    implemented yet.
    """

    def __init__(self, parent, app, profile):
        super().__init__(parent, fg_color="transparent")
        self.profile_name = profile["name"]
        self.profile_id = profile["id"]
        ctk.CTkLabel(self, text=self.profile_name, font=ctk.CTkFont(size=24, weight="bold")).pack(pady=(40, 30))

        ctk.CTkButton(self, text="Start Scanning", width=220).pack(pady=10)
        ctk.CTkButton(self, text="History", width=220).pack(pady=10)
        ctk.CTkButton(self, text="Go Back to Menu", width=220,
                      command=lambda: app.show_frame(MainMenu)).pack(pady=10)

    def get_profile_name(self):
        return self.profile_name



if __name__ == "__main__":
    app = NetWatchApp()
    app.mainloop()