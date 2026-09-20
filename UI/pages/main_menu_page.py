import customtkinter as ctk



class MainMenuPage(ctk.CTkFrame):
    """Landing screen: lists every saved profile as a button, plus the Scan Ports / Add Profile / Settings entry points."""

    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app

    def on_show(self, **kwargs):
        for widget in self.winfo_children():
            widget.destroy()
        ctk.CTkLabel(self, text="NetWatch", font=ctk.CTkFont(size=28, weight="bold")).pack(pady=(40, 30))

        for profile in self.app.storage.list_profiles():
            ctk.CTkButton(self, text=profile["name"], width=220,
                      command=lambda p=profile: self.enter_profile(p)).pack(pady=10)
        ctk.CTkButton(self, text="Scan Ports", width=220,
                      command=lambda: self.app.show_frame("PortScan")).pack(pady=10)
        ctk.CTkButton(self, text="Add Profile", width=220,
                      command=lambda: self.app.show_frame("AddProfilePage")).pack(pady=10)
        ctk.CTkButton(self, text="Settings", width=220,
                      command=lambda: self.app.show_frame("Settings")).pack(pady=10)

    def enter_profile(self, profile):
        self.app.current_profile_id = profile["id"]
        self.app.current_profile_name = profile["name"]
        #TODO self.app.show_frame(self.app.current_profile_name) -- gonna impement it
