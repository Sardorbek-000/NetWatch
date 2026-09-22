from __future__ import annotations

import customtkinter as ctk


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
