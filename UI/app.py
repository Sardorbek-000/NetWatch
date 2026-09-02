# --- UPDATED: stdlib imports needed for threaded scanning ---
import queue
import socket
import threading

import customtkinter as ctk
from core.ParsePorts import PortScanner

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class NetWatchApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("NetWatch")
        self.geometry("800x500")
        self.minsize(640, 420)

        self.profiles = []

        self.container = ctk.CTkFrame(self, fg_color="transparent")
        self.container.pack(fill="both", expand=True, padx=20, pady=20)

        self.frames = {}
        for Frame in (MainMenu, Settings, AddProfile, PortScan):
            frame = Frame(self.container, self)
            self.frames[Frame] = frame
            frame.place(relx=0, rely=0, relwidth=1, relheight=1)

        self.profile_frame = None

        self.show_frame(MainMenu)

    def show_frame(self, frame_class):
        self.frames[frame_class].tkraise()

    def open_profile(self, profile_name):
        if self.profile_frame is not None:
            self.profile_frame.destroy()
        self.profile_frame = Profile(self.container, self, profile_name)
        self.profile_frame.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.profile_frame.tkraise()


class MainMenu(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app
    def refresh_main_menu(self):
        for widget in self.winfo_children():
            widget.destroy()
        ctk.CTkLabel(self, text="NetWatch", font=ctk.CTkFont(size=28, weight="bold")).pack(pady=(40, 30))

        # ctk.CTkButton(self, text="Enter Profile", width=220,
        #               command=lambda: app.show_frame(Profile)).pack(pady=10)

        for profile_name in self.app.profiles:
            ctk.CTkButton(self, text=profile_name, width=220,
                      command=lambda p=profile_name: self.app.open_profile(p)).pack(pady=10)
        ctk.CTkButton(self, text="Scan Ports", width=220,
                      command=lambda: app.show_frame(PortScan)).pack(pady=10)
        ctk.CTkButton(self, text="Add Profile", width=220,
                      command=lambda: app.show_frame(AddProfile)).pack(pady=10)
        ctk.CTkButton(self, text="Settings", width=220,
                      command=lambda: app.show_frame(Settings)).pack(pady=10)

    def tkraise(self, *args):
        super().tkraise(*args)
        self.refresh_main_menu()



class Settings(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")

        ctk.CTkLabel(self, text="Settings", font=ctk.CTkFont(size=24, weight="bold")).pack(pady=(40, 30))
        self.title_entry = ctk.CTkEntry(self, width=260, placeholder_text="Profile title")
        self.title_entry.pack(pady=10)
        ctk.CTkButton(self, text="Delete Profiles", width=220, command=lambda: self.del_profile(self.title_entry.get())).pack(pady=10)
        ctk.CTkButton(self, text="Go Back to Menu", width=220,
                      command=lambda: app.show_frame(MainMenu)).pack(pady=10)

    def del_profile(self, profile_name):
        app.profiles.remove(profile_name)
        app.show_frame(MainMenu)
        self.title_entry.delete(0, "end")

class PortScan(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app

        # --- UPDATED: scan state + thread-safe channel from worker to UI ---
        self.scanner = None
        self.events = queue.Queue()

        ctk.CTkLabel(self, text="Scan for open Ports", font=ctk.CTkFont(size=24, weight="bold")).pack(pady=(40, 20))

        self.ip_entry = ctk.CTkEntry(self, width=260, placeholder_text="IP address")
        self.ip_entry.pack(pady=10)


        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(pady=10)

        self.scan_btn = ctk.CTkButton(btn_row, text="Start Scan", width=140,
                                      command=self.start_scan)
        self.scan_btn.pack(side="left", padx=5)
        self.stop_btn = ctk.CTkButton(btn_row, text="Stop", width=100,
                                      command=self.stop_scan, state="disabled")
        self.stop_btn.pack(side="left", padx=5)

        # --- FIX: .pack() returns None, so this must be two statements or
        #     self.main_menu_btn is None and .configure() below crashes ---
        self.main_menu_btn = ctk.CTkButton(self, text="Go Back to Menu", width=220,
                                           command=lambda: app.show_frame(MainMenu))
        self.main_menu_btn.pack(pady=10)

        # --- UPDATED: progress bar + status line ---
        self.progress = ctk.CTkProgressBar(self, width=260)
        self.progress.set(0)
        self.progress.pack(pady=(10, 4))
        self.status = ctk.CTkLabel(self, text="")
        self.status.pack()

        # --- UPDATED: scrollable list that shows the open ports ---
        self.results = ctk.CTkScrollableFrame(self, width=300, height=180,
                                              label_text="Open ports")
        self.results.pack(pady=10, fill="both", expand=True)


    def start_scan(self):
        host = self.ip_entry.get().strip()
        if not host or self.scanner is not None:
            return

        for w in self.results.winfo_children():
            w.destroy()
        self.progress.set(0)
        self.status.configure(text="Scanning...")
        self.scan_btn.configure(state="disabled")
        # self.main_menu_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")

        self.scanner = PortScanner(
            host,
            on_result=lambda p: self.events.put(("port", p)),
            on_progress=lambda done, total: self.events.put(("progress", done / total)),
            on_done=lambda: self.events.put(("done", None)),
        )
        threading.Thread(target=self.scanner.run, daemon=True).start()
        self.after(100, self._drain_events)

    def stop_scan(self):
        if self.scanner is not None:
            self.scanner.stop()
            self.status.configure(text="Stopping...")
            self.stop_btn.configure(state="disabled")

    def _drain_events(self):
        latest_progress = None
        processed = 0
        try:
            while processed < 500:
                kind, value = self.events.get_nowait()
                processed += 1
                if kind == "port":
                    self._add_port_row(value)
                elif kind == "progress":
                    latest_progress = value
                elif kind == "done":
                    self.progress.set(1)
                    self._scan_finished()
                    return
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
        self.status.configure(text=f"Scan complete - {count} open port(s)")
        self.progress.set(1)
        self.scan_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        self.scanner = None

class AddProfile(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        ctk.CTkLabel(self, text="Add Profile", font=ctk.CTkFont(size=24, weight="bold")).pack(pady=(40, 30))

        self.title_entry = ctk.CTkEntry(self, width=260, placeholder_text="Profile title")
        self.title_entry.pack(pady=10)

        ctk.CTkButton(self, text="Create", width=220, command=lambda : self.create_profile()).pack(pady=10)
        ctk.CTkButton(self, text="Go Back to Menu", width=220,
                      command=lambda: app.show_frame(MainMenu)).pack(pady=10)

    def create_profile(self):
        profile_name = self.title_entry.get()
        if profile_name.strip():
            self.app.profiles.append(profile_name)
            self.title_entry.delete(0, "end")
            print(f"Profile added: {profile_name}")
            self.app.show_frame(MainMenu)


class Profile(ctk.CTkFrame):
    def __init__(self, parent, app, profile_name):
        super().__init__(parent, fg_color="transparent")
        self.profile_name = profile_name
        ctk.CTkLabel(self, text=profile_name, font=ctk.CTkFont(size=24, weight="bold")).pack(pady=(40, 30))

        ctk.CTkButton(self, text="Start Scanning", width=220).pack(pady=10)
        ctk.CTkButton(self, text="History", width=220).pack(pady=10)
        ctk.CTkButton(self, text="Go Back to Menu", width=220,
                      command=lambda: app.show_frame(MainMenu)).pack(pady=10)

    def get_profile_name(self):
        return self.profile_name



if __name__ == "__main__":
    app = NetWatchApp()
    app.mainloop()