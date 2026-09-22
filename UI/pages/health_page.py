"""
NetWatch — Health page (Module 3 / Ethan's Task 4)
================================================================
Shows the current profile's network health score plus a trend chart
over the last TREND_DAYS days. Built once and stacked with every other
page in UI/app.py's PAGES list; on_show() re-queries Storage every time
the page becomes visible instead of caching stale data — same pattern
as ProfilePage.

Ported from the old standalone HealthPanel (dev2-analytics/health_panel.py):
  - self.connection + ip_range          -> self.app.storage + self.app.current_profile_id
  - db.get_health_score(conn, scan_id)  -> self.app.storage.get_health_score(scan_id)
  - db.get_health_trend(conn, start, end) doesn't exist on the merged Storage
    class, so the trend here is built from get_scan_history() + a
    get_health_score() call per scan instead (see _refresh_trend_chart()).
  - offline_devices is gone entirely: the merged health_scores table /
    Storage.get_health_score() never had it (see database/storage.py) —
    the old breakdown label's "Offline: N" segment is dropped, not ported.
"""

from datetime import datetime, timedelta

import customtkinter as ctk
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# --- ETHAN ---
# Matches CustomTkinter's dark-mode frame colour so the chart blends cleanly.
CHART_BG = "#2b2b2b"
CHART_FG = "#dce4ee"

# Map range options to days (None means plot all history)
TREND_RANGES = {"7 days": 7, "30 days": 30, "All": None}


class HealthPage(ctk.CTkFrame):
    """Current profile's health score + trend."""
    ...
    TREND_DAYS = 14

    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app

        self._build_score_section()
        self._build_trend_section()
        self._build_nav_section()

    def _build_score_section(self):
        score_frame = ctk.CTkFrame(self)
        score_frame.pack(fill="x", padx=10, pady=(10, 5))

        title = ctk.CTkLabel(score_frame, text="Network Health", font=ctk.CTkFont(size=16, weight="bold"))
        title.pack(anchor="w", padx=10, pady=(10, 0))

        self.score_label = ctk.CTkLabel(score_frame, text="--", font=ctk.CTkFont(size=28, weight="bold"))
        self.score_label.pack(anchor="w", padx=10)

        self.progress_bar = ctk.CTkProgressBar(score_frame, height=18)
        self.progress_bar.pack(fill="x", padx=10, pady=(0, 10))
        self.progress_bar.set(0)

        self.breakdown_label = ctk.CTkLabel(score_frame, text="", justify="left", anchor="w")
        self.breakdown_label.pack(anchor="w", padx=10, pady=(0, 10))

        self.refresh_button = ctk.CTkButton(score_frame, text="Refresh", command=self.refresh, width=90)
        self.refresh_button.pack(anchor="e", padx=10, pady=(0, 10))

    def _build_trend_section(self):
        trend_frame = ctk.CTkFrame(self)
        trend_frame.pack(fill="both", expand=True, padx=10, pady=(5, 10))

        header_frame = ctk.CTkFrame(trend_frame, fg_color="transparent")
        header_frame.pack(fill="x", padx=10, pady=(10, 0))

        trend_title = ctk.CTkLabel(header_frame, text="Trend", font=ctk.CTkFont(size=14, weight="bold"))
        trend_title.pack(side="left")

        # Step 12 Date Range Selector
        self.range_selector = ctk.CTkSegmentedButton(
            header_frame,
            values=list(TREND_RANGES),
            command=lambda _choice: self._refresh_trend_chart()
        )
        self.range_selector.set("30 days")
        self.range_selector.pack(side="right")

        # Figure with dark facecolor matching CHART_BG
        self.figure = Figure(figsize=(5, 2.4), dpi=100, facecolor=CHART_BG)
        self.ax = self.figure.add_subplot(111)

        self.canvas = FigureCanvasTkAgg(self.figure, master=trend_frame)
        self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=10, pady=10)
    def _build_nav_section(self):
        ctk.CTkButton(self, text="Back to Profile", width=220,
                      command=lambda: self.app.show_frame("ProfilePage")).pack(pady=(0, 10))

    # ------------------------------------------------------------------ #
    # on_show — this codebase's "screen became visible" hook (see app.py's
    # docstring / show_frame()). Guard mirrors ProfilePage.on_show(): a
    # profile must be selected first, or bounce back to MainMenuPage.
    # ------------------------------------------------------------------ #
    def on_show(self, **kwargs):
        if self.app.current_profile_id is None:
            self.app.show_frame("MainMenuPage")
            return
        # Cheap/idempotent — only scores scans added since the last call.
        self.app.storage.ensure_health_scores(self.app.current_profile_id)
        self.refresh()

    def refresh(self):
        if self.app.current_profile_id is None:
            return
        self._refresh_current_score()
        self._refresh_trend_chart()

    def _refresh_current_score(self):
        profile_id = self.app.current_profile_id
        history = self.app.storage.get_scan_history(profile_id)
        if not history:
            self.score_label.configure(text="No scans yet")
            self.progress_bar.set(0)
            self.progress_bar.configure(progress_color=("gray75", "gray25"))
            self.breakdown_label.configure(text="Run a scan to generate a health score.")
            return

        latest_scan_id = history[-1]["id"]  # get_scan_history() is oldest-first
        row = self.app.storage.get_health_score(latest_scan_id)
        if row is None:
            # Shouldn't happen since on_show() just called ensure_health_scores(),
            # but don't crash the page if it somehow does (e.g. refresh() called
            # directly without on_show() having run first).
            self.score_label.configure(text="No score yet")
            self.progress_bar.set(0)
            self.breakdown_label.configure(text="")
            return

        score = row["score"]
        self.score_label.configure(text=f"{score:.0f} / 100")
        self.progress_bar.set(score / 100)
        self.progress_bar.configure(progress_color=self._color_for_score(score))
        self.breakdown_label.configure(
            text=(
                f"New devices: {row['new_devices']}   "
                f"Missing: {row['missing_devices']}   "
                f"Unknown vendor: {row['unknown_vendors']}"
            )
        )

    def _style_axes(self):
        """Applies dark-mode styling to matplotlib axes."""
        self.ax.set_facecolor(CHART_BG)
        self.ax.tick_params(colors=CHART_FG)
        for spine in self.ax.spines.values():
            spine.set_color("#6b6b6b")

    def _refresh_trend_chart(self):
        profile_id = self.app.current_profile_id
        if profile_id is None:
            return

        # Read selected days from range selector
        days = TREND_RANGES[self.range_selector.get()]
        start = datetime.now() - timedelta(days=days) if days is not None else None
        
        history = self.app.storage.get_scan_history(profile_id, start=start)

        points = []
        for scan in history:
            score_row = self.app.storage.get_health_score(scan["id"])
            if score_row is not None:
                points.append((datetime.fromisoformat(scan["scan_time"]), score_row["score"]))

        self.ax.clear()
        self._style_axes()

        if not points:
            self.ax.text(0.5, 0.5, "No data in this range", ha="center", va="center",
                         color=CHART_FG, transform=self.ax.transAxes)
            self.ax.set_xticks([])
            self.ax.set_yticks([])
        else:
            timestamps, scores = zip(*points)
            self.ax.plot(timestamps, scores, marker="o", linewidth=1.5, color="#3b8ed0")
            self.ax.set_ylim(0, 100)
            self.ax.set_ylabel("Score", color=CHART_FG)
            self.ax.tick_params(axis="x", rotation=45, labelsize=7)
            self.figure.autofmt_xdate()
            self.figure.tight_layout()

        self.canvas.draw()

    
    def _build_nav_section(self):
        ctk.CTkButton(
            self, 
            text="Go Back to Main Menu", 
            width=220,
            command=lambda: self.app.show_frame("MainMenuPage")
        ).pack(pady=(0, 10))

    @staticmethod
    def _color_for_score(score):
        if score >= 80:
            return "#2ecc71"   # green
        elif score >= 50:
            return "#f1c40f"   # yellow
        else:
            return "#e74c3c"   # red