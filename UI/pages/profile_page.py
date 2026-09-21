import customtkinter as ctk


class ProfilePage(ctk.CTkFrame):
    """Hub for one profile. Built once like the other pages — current_profile_id/name live on NetWatchApp and get read fresh each time on_show() runs."""

    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app

        self.title_label = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=24, weight="bold"))
        self.title_label.pack(pady=(40, 30))

        # ctk.CTkButton(self, text="Start Scanning", width=220).pack(pady=10)   # TODO(Sardor)
        # ctk.CTkButton(self, text="History", width=220).pack(pady=10)          # TODO(Sardor)
        # ctk.CTkButton(self, text="Manage Devices", width=220).pack(pady=10)   # TODO(Sardor)

        ctk.CTkButton(self, text="Port Scan", width=220,
                      command=lambda: self.app.show_frame("PortScan")).pack(pady=10) 
        ctk.CTkButton(self, text="Go Back to Menu", width=220,
                      command=lambda: self.app.show_frame("MainMenuPage")).pack(pady=10)

    def on_show(self, **kwargs):
        if self.app.current_profile_id is None:
            self.app.show_frame("MainMenuPage")
            return
        self.title_label.configure(text=self.app.current_profile_name)