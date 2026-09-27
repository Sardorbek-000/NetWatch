from __future__ import annotations

import customtkinter as ctk


class DeviceManagerPage(ctk.CTkFrame):
    def __init__(self, parent, app: NetWatchApp) -> None:
        super().__init__(parent, fg_color="transparent")
        self.app = app

        ctk.CTkLabel(self, text="Manage Devices", font=ctk.CTkFont(size=24, weight="bold")).pack(pady=(20, 6))
        ctk.CTkLabel(
            self,
            text="Every device ever seen in this profile. Rename any of them, or Watch one to "
                 "get flagged if it disappears or comes back.",
        ).pack(pady=(0, 10))

        # Packed BEFORE the expanding list_frame, with side="bottom" — see
        # the same comment in scan_page.py for why the order matters.
        ctk.CTkButton(
            self, text="Back to Profile", fg_color="gray40", hover_color="gray30",
            command=lambda: app.show_frame("ProfilePage"),
        ).pack(side="bottom", pady=10)

        self.list_frame = ctk.CTkScrollableFrame(self, width=780, height=420)
        self.list_frame.pack(pady=10, fill="both", expand=True)

    def on_show(self) -> None:
        self._load()

    def _load(self) -> None:
        for child in self.list_frame.winfo_children():
            child.destroy()
        devices = self.app.storage.get_all_known_devices(self.app.current_profile_id)
        if not devices:
            ctk.CTkLabel(self.list_frame, text="No devices seen yet — run a scan first.").pack(pady=10)
            return

        # ETHAN — one call gets status (online/missing, how long missing,
        # uptime%) for every watched device at once, instead of a per-row
        # query; devices that aren't watched just won't be in this dict.
        flagged_by_mac = {
            f["mac"]: f for f in self.app.storage.get_flagged_devices(self.app.current_profile_id)
        }

        for d in devices:
            row = ctk.CTkFrame(self.list_frame)
            row.pack(fill="x", pady=2, padx=2)

            info_frame = ctk.CTkFrame(row, fg_color="transparent")
            info_frame.pack(side="left", fill="x", expand=True)

            name_suffix = f"  ({d['custom_name']})" if d["custom_name"] else ""
            text = f"{d['mac']}{name_suffix}   last IP: {d['ip']}   {d['vendor'] or 'Unknown'}   last seen: {d['last_seen']}"
            ctk.CTkLabel(info_frame, text=text, anchor="w").pack(anchor="w", padx=5, pady=(4, 0))

            flag = flagged_by_mac.get(d["mac"])
            if flag is not None:
                if flag["is_online"]:
                    status_text, status_color = "👁 Watching — online", "#2ecc71"
                else:
                    missed = flag["consecutive_missing_scans"]
                    plural = "scan" if missed == 1 else "scans"
                    status_text = f"👁 Watching — MISSING for {missed} {plural}"
                    status_color = "#e74c3c"
                ctk.CTkLabel(info_frame, text=status_text, anchor="w", text_color=status_color,
                             font=ctk.CTkFont(size=11)).pack(anchor="w", padx=5, pady=(0, 4))

            button_frame = ctk.CTkFrame(row, fg_color="transparent")
            button_frame.pack(side="right", padx=5, pady=4)

            watch_text = "Unwatch" if flag is not None else "Watch"
            watch_color = "gray40" if flag is not None else None
            watch_kwargs = {"fg_color": watch_color} if watch_color else {}
            ctk.CTkButton(
                button_frame, text=watch_text, width=70,
                command=lambda mac=d["mac"], watched=(flag is not None): self._toggle_watch(mac, watched),
                **watch_kwargs,
            ).pack(side="right", padx=(5, 0))

            ctk.CTkButton(button_frame, text="Rename", width=70, command=lambda mac=d["mac"]: self._rename(mac)).pack(
                side="right"
            )

    def _rename(self, mac: str) -> None:
        dialog = ctk.CTkInputDialog(text=f"Custom name for {mac} (this profile only):", title="Rename Device")
        name = dialog.get_input()
        if name:
            self.app.storage.set_device_name(self.app.current_profile_id, mac, name)
            self._load()

    def _toggle_watch(self, mac: str, currently_watched: bool) -> None:
        if currently_watched:
            self.app.storage.unflag_device(self.app.current_profile_id, mac)
        else:
            self.app.storage.flag_device(self.app.current_profile_id, mac)
        self._load()