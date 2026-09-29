from __future__ import annotations

import customtkinter as ctk

# ETHAN — dedicated page for the devices the user is Watching: live status,
# per-device stats, and a scan-by-scan presence strip. The data comes from
# Storage.get_flagged_devices() (status/uptime) and Storage.get_watched_timeline()
# (recent history); the "alert after N missed scans" setting is the same one
# Storage.get_flag_alerts() uses for the Profile page banner.

GREEN = "#2ecc71"
RED = "#e74c3c"
ORANGE = "#f39c12"
GRAY = "#555555"

SCAN_WINDOWS = ["10", "30", "60"]
DEFAULT_WINDOW = "30"
STRIP_WIDTH = 560
STRIP_HEIGHT = 16


class WatchPage(ctk.CTkFrame):
    def __init__(self, parent, app) -> None:
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self.scan_window = int(DEFAULT_WINDOW)

        ctk.CTkLabel(self, text="Watched Devices", font=ctk.CTkFont(size=24, weight="bold")).pack(pady=(20, 4))
        ctk.CTkLabel(
            self,
            text="Live status and history for the devices you're watching. "
                 "Add or remove devices from Manage Devices.",
        ).pack(pady=(0, 8))

        # --- settings row: alert threshold + how many scans to show ---
        settings = ctk.CTkFrame(self, fg_color="transparent")
        settings.pack(pady=(0, 6))
        ctk.CTkLabel(settings, text="Alert after").pack(side="left", padx=(0, 6))
        self.threshold_menu = ctk.CTkOptionMenu(
            settings, values=[str(n) for n in range(1, 11)], width=70, command=self._on_threshold_change
        )
        self.threshold_menu.pack(side="left")
        ctk.CTkLabel(settings, text="missed scans in a row").pack(side="left", padx=(6, 24))
        ctk.CTkLabel(settings, text="Show last").pack(side="left", padx=(0, 6))
        self.window_selector = ctk.CTkSegmentedButton(
            settings, values=SCAN_WINDOWS, command=self._on_window_change, width=150
        )
        self.window_selector.set(DEFAULT_WINDOW)
        self.window_selector.pack(side="left")
        ctk.CTkLabel(settings, text="scans").pack(side="left", padx=(6, 0))

        # --- summary boxes ---
        summary = ctk.CTkFrame(self, fg_color="transparent")
        summary.pack(pady=(4, 6))
        self.watched_value = self._stat_box(summary, "Watched")
        self.online_value = self._stat_box(summary, "Online")
        self.missing_value = self._stat_box(summary, "Missing")
        self.alerting_value = self._stat_box(summary, "Alerting")

        # --- what changed on the latest scan ---
        self.events_label = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=13), wraplength=700, justify="center")
        self.events_label.pack(pady=(0, 4))

        # --- legend for the presence strips ---
        legend = ctk.CTkFrame(self, fg_color="transparent")
        legend.pack(pady=(0, 2))
        for color, text in ((GREEN, "seen"), (RED, "missing"), (GRAY, "not on network yet")):
            ctk.CTkLabel(legend, text="■", text_color=color, font=ctk.CTkFont(size=12)).pack(side="left")
            ctk.CTkLabel(legend, text=text + "   ", font=ctk.CTkFont(size=11)).pack(side="left")
        ctk.CTkLabel(legend, text="(oldest → newest scan)", font=ctk.CTkFont(size=11)).pack(side="left")

        # Buttons are packed first, pinned to the bottom, so they never get pushed
        # off-screen in the app's small default window; the list takes what's left.
        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.pack(side="bottom", pady=8)

        self.list_frame = ctk.CTkScrollableFrame(self, width=780, height=150)
        self.list_frame.pack(pady=6, fill="both", expand=True)
        ctk.CTkButton(
            buttons, text="Manage Devices", command=lambda: app.show_frame("DeviceManagerPage")
        ).pack(side="left", padx=6)
        ctk.CTkButton(
            buttons, text="Back to Profile", fg_color="gray40", hover_color="gray30",
            command=lambda: app.show_frame("ProfilePage"),
        ).pack(side="left", padx=6)

    # ------------------------------------------------------------------ #
    def on_show(self, **kwargs) -> None:
        if self.app.current_profile_id is None:
            self.app.show_frame("MainMenuPage")
            return
        self._refresh()

    def _on_threshold_change(self, value: str) -> None:
        self.app.storage.set_missed_scan_threshold(self.app.current_profile_id, int(value))
        self._refresh()

    def _on_window_change(self, value: str) -> None:
        self.scan_window = int(value)
        self._refresh()

    def _unwatch(self, mac: str) -> None:
        self.app.storage.unflag_device(self.app.current_profile_id, mac)
        self._refresh()

    # ------------------------------------------------------------------ #
    @staticmethod
    def _stat_box(parent, title: str) -> ctk.CTkLabel:
        box = ctk.CTkFrame(parent, width=120)
        box.pack(side="left", padx=6)
        value = ctk.CTkLabel(box, text="0", font=ctk.CTkFont(size=22, weight="bold"), width=110)
        value.pack(padx=8, pady=(6, 0))
        ctk.CTkLabel(box, text=title, font=ctk.CTkFont(size=11)).pack(padx=8, pady=(0, 6))
        return value

    def _refresh(self) -> None:
        storage = self.app.storage
        profile_id = self.app.current_profile_id

        threshold = storage.get_missed_scan_threshold(profile_id)
        self.threshold_menu.set(str(threshold))
        self.window_selector.set(str(self.scan_window) if str(self.scan_window) in SCAN_WINDOWS else DEFAULT_WINDOW)

        watched = storage.get_flagged_devices(profile_id)
        timeline = storage.get_watched_timeline(profile_id, self.scan_window)

        for child in self.list_frame.winfo_children():
            child.destroy()

        online = sum(1 for d in watched if d["is_online"])
        missing = len(watched) - online
        alerting = sum(1 for d in watched if not d["is_online"] and d["consecutive_missing_scans"] >= threshold)
        self.watched_value.configure(text=str(len(watched)))
        normal = ctk.ThemeManager.theme["CTkLabel"]["text_color"]  # configure() rejects None, so restore the theme colour
        self.online_value.configure(text=str(online), text_color=GREEN if online else normal)
        self.missing_value.configure(text=str(missing), text_color=ORANGE if missing else normal)
        self.alerting_value.configure(text=str(alerting), text_color=RED if alerting else normal)

        self._refresh_events(profile_id, bool(watched))

        if not watched:
            ctk.CTkLabel(
                self.list_frame,
                text="You're not watching any devices yet.\nOpen Manage Devices and click Watch on one.",
            ).pack(pady=20)
            return

        # Devices needing attention first, then missing, then online; name/MAC within each group.
        def sort_key(d: dict):
            gone_long = not d["is_online"] and d["consecutive_missing_scans"] >= threshold
            return (0 if gone_long else 1 if not d["is_online"] else 2, (d["custom_name"] or d["mac"]).lower())

        for device in sorted(watched, key=sort_key):
            self._build_card(device, timeline["devices"].get(device["mac"]), len(timeline["scans"]), threshold)

    def _refresh_events(self, profile_id: int, has_watched: bool) -> None:
        if not has_watched:
            self.events_label.configure(text="")
            return
        alerts = self.app.storage.get_flag_alerts(profile_id)
        if not alerts:
            self.events_label.configure(text="No new watch events on the latest scan.", text_color=("gray30", "gray70"))
            return
        lines = []
        for alert in alerts:
            label = alert["custom_name"] or alert["mac"]
            if alert["event"] == "reappeared":
                lines.append(f"⚠ {label} is back online after {alert['missed_scans']} missed scans")
            else:
                lines.append(f"⚠ {label} has disappeared ({alert['missed_scans']} missed scans in a row)")
        self.events_label.configure(text="\n".join(lines), text_color=RED)

    def _build_card(self, device: dict, history: dict | None, scan_count: int, threshold: int) -> None:
        card = ctk.CTkFrame(self.list_frame)
        card.pack(fill="x", pady=4, padx=2)

        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=8, pady=(6, 0))

        name = device["custom_name"] or device["mac"]
        ctk.CTkLabel(top, text=name, font=ctk.CTkFont(size=15, weight="bold"), anchor="w").pack(side="left")

        ctk.CTkButton(
            top, text="Unwatch", width=70, fg_color="gray40", hover_color="gray30",
            command=lambda mac=device["mac"]: self._unwatch(mac),
        ).pack(side="right")

        missed = device["consecutive_missing_scans"]
        plural = "scan" if missed == 1 else "scans"
        if device["is_online"]:
            status_text, status_color = "● Online", GREEN
        elif missed < threshold:
            status_text, status_color = f"● Missing {missed} {plural} (alerts at {threshold})", ORANGE
        else:
            status_text, status_color = f"● MISSING {missed} {plural}", RED
        ctk.CTkLabel(top, text=status_text, text_color=status_color, font=ctk.CTkFont(size=12, weight="bold")).pack(
            side="right", padx=12
        )

        ctk.CTkLabel(
            card,
            text=f"{device['mac']}   last IP: {device['ip'] or '—'}   {device['vendor'] or 'Unknown vendor'}"
                 f"   hostname: {device['hostname'] or '—'}",
            anchor="w", font=ctk.CTkFont(size=11),
        ).pack(anchor="w", padx=8)

        uptime = device["uptime_percent"]
        uptime_text = f"{uptime:.1f}%" if isinstance(uptime, (int, float)) else "—"
        watching_since = (device["flagged_at"] or "")[:10] or "—"
        ctk.CTkLabel(
            card, anchor="w", font=ctk.CTkFont(size=11),
            text=f"Uptime {uptime_text} overall   ·   watching since {watching_since}",
        ).pack(anchor="w", padx=8)

        if history is not None and scan_count:
            last_seen = history["last_seen"] or f"not seen in the last {scan_count} scans"
            ctk.CTkLabel(
                card, anchor="w", font=ctk.CTkFont(size=11),
                text=f"Last {scan_count} scans: went missing {history['outages']}×   ·   "
                     f"longest gap {history['longest_gap']}   ·   last seen {last_seen}",
            ).pack(anchor="w", padx=8)
            self._draw_strip(card, history["presence"])

        ctk.CTkFrame(card, height=4, fg_color="transparent").pack()

    @staticmethod
    def _draw_strip(card: ctk.CTkFrame, presence: list[bool]) -> None:
        """One coloured cell per scan, oldest → newest: seen / missing / not on the network yet."""
        canvas = ctk.CTkCanvas(
            card, width=STRIP_WIDTH, height=STRIP_HEIGHT, highlightthickness=0,
            bg=card._apply_appearance_mode(card.cget("fg_color")),
        )
        canvas.pack(anchor="w", padx=8, pady=(4, 0))
        first_seen = presence.index(True) if True in presence else len(presence)
        cell = STRIP_WIDTH / len(presence)
        for i, present in enumerate(presence):
            color = GREEN if present else (GRAY if i < first_seen else RED)
            x0 = i * cell
            canvas.create_rectangle(x0, 0, x0 + max(cell - 1, 1), STRIP_HEIGHT, fill=color, outline="")