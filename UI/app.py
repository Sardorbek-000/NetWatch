"""
NetWatch — Frontend (Module 3)
================================================================
The CustomTkinter desktop app: the NetWatchApp shell only. Every screen
lives in its own UI/pages/*.py file. Talks to the database only through
database/storage.py's Storage class — no SQL lives in this file.

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

import customtkinter as ctk
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
from UI.pages.port_scan_page import PortScanPage

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
    MainMenuPage, SettingsPage, AddProfilePage, PortScanPage, ProfilePage,
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




if __name__ == "__main__":
    app = NetWatchApp()
    app.mainloop()