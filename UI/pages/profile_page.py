import customtkinter as ctk


class ProfilePage(ctk.CTkFrame):
    """Hub for one profile. Built once like the other pages — current_profile_id/name live on NetWatchApp and get read fresh each time on_show() runs."""

    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app

        self.title_label = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=24, weight="bold"))
        self.title_label.pack(pady=(40, 10))

        # ETHAN — surfaces get_flag_alerts() (watched devices that appeared
        # or disappeared on the most recent scan). Empty/hidden when there's
        # nothing to report, so it doesn't take up space on a normal visit.
        self.alert_label = ctk.CTkLabel(
            self, text="", font=ctk.CTkFont(size=13), text_color="#e74c3c", wraplength=500, justify="center"
        )
        self.alert_label.pack(pady=(0, 10))

        ctk.CTkButton(self, text="Start Scanning", width=220,
              command=lambda: self.app.show_frame("ScanPage")).pack(pady=10)
        ctk.CTkButton(self, text="History", width=220,
              command=lambda: self.app.show_frame("HistoryPage")).pack(pady=10)
        ctk.CTkButton(self, text="Manage Devices", width=220,
              command=lambda: self.app.show_frame("DeviceManagerPage")).pack(pady=10)
        ctk.CTkButton(self, text="Watched Devices", width=220,
              command=lambda: self.app.show_frame("WatchPage")).pack(pady=10)

        ctk.CTkButton(self, text="Network Health", width=220,
                      command=lambda: self.app.show_frame("HealthPage")).pack(pady=10)
        ctk.CTkButton(self, text="Port Scan", width=220,
                      command=lambda: self.app.show_frame("PortScanPage")).pack(pady=10)
        ctk.CTkButton(self, text="Go Back to Menu", width=220,
                      command=lambda: self.app.show_frame("MainMenuPage")).pack(pady=10)

    def on_show(self, **kwargs):
        if self.app.current_profile_id is None:
            self.app.show_frame("MainMenuPage")
            return
        self.title_label.configure(text=self.app.current_profile_name)
        self._refresh_alerts()

    def _refresh_alerts(self) -> None:
        alerts = self.app.storage.get_flag_alerts(self.app.current_profile_id)
        if not alerts:
            self.alert_label.configure(text="")
            return
        # ETHAN — this always reflects the latest scan vs. the one before
        # it, so revisiting this page while nothing new has happened since
        # your last look will keep showing the same line rather than
        # clearing itself — there's no "seen/dismissed" tracking yet. Good
        # enough for now; worth adding if it gets noisy in practice.
        lines = []
        for alert in alerts:
            label = alert["custom_name"] or alert["mac"]
            verb = "is back online" if alert["event"] == "reappeared" else "has disappeared"
            lines.append(f"⚠ {label} {verb}")
        self.alert_label.configure(text="\n".join(lines))