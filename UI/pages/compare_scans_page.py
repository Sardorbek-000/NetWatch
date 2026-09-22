from __future__ import annotations

import customtkinter as ctk

from UI.theme import DISCONNECTED_COLOR, NEW_DEVICE_COLOR


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
