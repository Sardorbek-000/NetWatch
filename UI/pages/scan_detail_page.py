from __future__ import annotations

import customtkinter as ctk

from UI.theme import NEW_DEVICE_COLOR


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
