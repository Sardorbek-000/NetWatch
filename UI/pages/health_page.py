"""
NetWatch — Health page (Module 3 / Ethan's Task 4)
================================================================
Shows the current profile's latest scan stats plus separate trend
graphs (total devices, new devices, missing devices, unknown-vendor
devices) with a 7 days / 30 days / All range selector.

--- ETHAN — redone in response to teacher feedback ---
The original version of this page collapsed new/missing/unknown-vendor
counts into a single 0-100 "health score" and plotted that one number
over time. Feedback: the score conflates several different things, and
if you're going to show an index you need to be able to explain it
clearly — simpler to just show the underlying stats as their own
graphs (new devices vs. devices that disappeared will usually move in
opposite directions, which is exactly what an index would hide).

So this version:
  - Drops the score label / progress bar / color coding entirely.
  - Shows the latest scan's raw counts as plain text instead.
  - Plots device_count, new_devices, missing_devices, and unknown_vendors
    as four separate bar charts (shared, evenly-spaced scan index instead
    of real elapsed time, since scans can be minutes or days apart) with
    each bar labeled with its exact count, instead of one score line.
  - Storage.get_health_trend() now returns those raw counts per scan
    (previously just the blended "score") — see database/storage.py.
  - The health_scores table / solve_health_score() / ensure_health_scores()
    backend is untouched: the composite score is still computed and
    stored (get_health_score() still returns it) in case it's wanted
    again later, this page just no longer displays it.
  - Polish pass: shared font-size scale (FONT_SIZE_* constants) instead
    of ad-hoc sizes, y-axis labels on every subplot, scan-time labels
    shown only under the bottom-most subplot (not repeated on all four),
    and consistent spacing/margins (fixed subplots_adjust() instead of
    tight_layout(), which fought with the explicit hspace between
    subplots).
"""

from datetime import datetime, timedelta

import customtkinter as ctk
from matplotlib.figure import Figure
from matplotlib.ticker import MaxNLocator
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# --- ETHAN ---
# A shared type scale instead of picking sizes ad hoc per label — keeps the
# page's hierarchy consistent (page title > section title > body > caption).
FONT_SIZE_PAGE_TITLE = 16
FONT_SIZE_SECTION_TITLE = 14
FONT_SIZE_BODY = 14
FONT_SIZE_CAPTION = 11
FONT_SIZE_CHART_TITLE = 9
FONT_SIZE_CHART_TICK = 7

# Matches CustomTkinter's dark-mode frame colour so the chart blends cleanly.
CHART_BG = "#2b2b2b"
CHART_FG = "#dce4ee"

# Map range options to days (None means plot all history)
TREND_RANGES = {"7 days": 7, "30 days": 30, "All": None}

# One entry per graph: (dict key in get_health_trend()'s rows, subplot title, line color)
TREND_METRICS = [
    ("device_count", "Total devices", "#3b8ed0"),       # blue — overall network size
    ("new_devices", "New devices", "#2ecc71"),          # green — appearing
    ("missing_devices", "Missing devices", "#e74c3c"),  # red — disappearing
    ("unknown_vendors", "Unknown vendor", "#f1c40f"),    # yellow — data-quality gap
]


class HealthPage(ctk.CTkFrame):
    """Current profile's latest scan stats + three separate metric trends."""

    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app

        self._build_snapshot_section()
        self._build_trend_section()
        self._build_nav_section()

    def _build_snapshot_section(self):
        snapshot_frame = ctk.CTkFrame(self)
        snapshot_frame.pack(fill="x", padx=12, pady=(12, 6))

        title = ctk.CTkLabel(snapshot_frame, text="Network Health",
                              font=ctk.CTkFont(size=FONT_SIZE_PAGE_TITLE, weight="bold"))
        title.pack(anchor="w", padx=14, pady=(14, 2))

        # Plain per-metric numbers for the latest scan — deliberately NOT a
        # single blended score. See module docstring.
        self.snapshot_label = ctk.CTkLabel(
            snapshot_frame, text="--", font=ctk.CTkFont(size=FONT_SIZE_BODY), justify="left", anchor="w"
        )
        self.snapshot_label.pack(anchor="w", padx=14, pady=(6, 2))

        self.snapshot_time_label = ctk.CTkLabel(
            snapshot_frame, text="", font=ctk.CTkFont(size=FONT_SIZE_CAPTION), text_color="gray60", anchor="w"
        )
        self.snapshot_time_label.pack(anchor="w", padx=14, pady=(0, 14))

        self.refresh_button = ctk.CTkButton(snapshot_frame, text="Refresh", command=self.refresh, width=90)
        self.refresh_button.pack(anchor="e", padx=14, pady=(0, 14))

    def _build_trend_section(self):
        trend_frame = ctk.CTkFrame(self)
        trend_frame.pack(fill="both", expand=True, padx=12, pady=(6, 12))

        header_frame = ctk.CTkFrame(trend_frame, fg_color="transparent")
        header_frame.pack(fill="x", padx=14, pady=(14, 4))

        trend_title = ctk.CTkLabel(header_frame, text="Trends",
                                    font=ctk.CTkFont(size=FONT_SIZE_SECTION_TITLE, weight="bold"))
        trend_title.pack(side="left")

        # Date range selector — same as before, now drives all four subplots at once.
        self.range_selector = ctk.CTkSegmentedButton(
            header_frame,
            values=list(TREND_RANGES),
            command=lambda _choice: self._refresh_trend_charts()
        )
        self.range_selector.set("30 days")
        self.range_selector.pack(side="right")

        # Stacked subplots, one per metric, sharing an x-axis so e.g. the
        # "new" vs "missing" graphs can be visually compared scan-to-scan.
        self.figure = Figure(figsize=(5, 6.8), dpi=100, facecolor=CHART_BG)
        self.axes = self.figure.subplots(nrows=len(TREND_METRICS), ncols=1, sharex=True)
        # Extra vertical gap between subplots so titles/tick labels don't
        # crowd the chart above/below them.
        self.figure.subplots_adjust(hspace=0.55)

        self.canvas = FigureCanvasTkAgg(self.figure, master=trend_frame)
        self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=14, pady=(6, 14))

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
        self._refresh_snapshot()
        self._refresh_trend_charts()

    def _refresh_snapshot(self):
        profile_id = self.app.current_profile_id
        history = self.app.storage.get_scan_history(profile_id)
        if not history:
            self.snapshot_label.configure(text="No scans yet — run a scan to see stats here.")
            self.snapshot_time_label.configure(text="")
            return

        latest_scan_id = history[-1]["id"]  # get_scan_history() is oldest-first
        row = self.app.storage.get_health_score(latest_scan_id)
        if row is None:
            # Shouldn't happen since on_show() just called ensure_health_scores(),
            # but don't crash the page if it somehow does (e.g. refresh() called
            # directly without on_show() having run first).
            self.snapshot_label.configure(text="No stats yet for the latest scan.")
            self.snapshot_time_label.configure(text="")
            return

        self.snapshot_label.configure(
            text=(
                f"Total devices: {history[-1]['device_count']}     "
                f"New devices: {row['new_devices']}     "
                f"Missing: {row['missing_devices']}     "
                f"Unknown vendor: {row['unknown_vendors']}"
            )
        )
        self.snapshot_time_label.configure(text=f"As of scan at {row['scan_time']}")

    def _style_axes(self, ax, title):
        """Applies dark-mode styling to one matplotlib axes."""
        ax.set_facecolor(CHART_BG)
        ax.tick_params(colors=CHART_FG, labelsize=FONT_SIZE_CHART_TICK)
        ax.set_title(title, color=CHART_FG, fontsize=FONT_SIZE_CHART_TITLE, loc="left", pad=6)
        # Units on the axis, not just a bare number scale — makes each
        # graph readable on its own without relying on the title alone.
        ax.set_ylabel("Devices", color=CHART_FG, fontsize=FONT_SIZE_CHART_TICK)
        for spine in ax.spines.values():
            spine.set_color("#6b6b6b")
        # Lighter, less visually noisy gridlines than matplotlib's default.
        ax.grid(True, color="#444444", linewidth=0.5, alpha=0.5)
        # Counts are always whole devices — no fractional ticks like "0.2".
        ax.yaxis.set_major_locator(MaxNLocator(integer=True, nbins=5))

    def _refresh_trend_charts(self):
        profile_id = self.app.current_profile_id
        if profile_id is None:
            return

        # Read selected days from range selector
        days = TREND_RANGES[self.range_selector.get()]
        start = datetime.now() - timedelta(days=days) if days is not None else None

        rows = self.app.storage.get_health_trend(profile_id, start=start)
        # Categorical (index-based) x-axis instead of real elapsed time:
        # scans can be minutes or days apart, and a bar chart's bar widths
        # would either look inconsistent or need constant retuning if tied
        # to actual timestamps. Evenly-spaced bars keep every scan equally
        # readable regardless of the gap before/after it.
        x_positions = list(range(len(rows)))
        tick_labels = [datetime.fromisoformat(r["scan_time"]).strftime("%m-%d\n%H:%M") for r in rows]

        for i, (ax, (key, title, color)) in enumerate(zip(self.axes, TREND_METRICS)):
            ax.clear()
            self._style_axes(ax, title)

            if not rows:
                ax.text(0.5, 0.5, "No data in this range", ha="center", va="center",
                         color=CHART_FG, transform=ax.transAxes, fontsize=FONT_SIZE_CHART_TITLE)
                ax.set_xticks([])
                ax.set_yticks([])
                continue

            values = [r[key] for r in rows]
            bars = ax.bar(x_positions, values, width=0.6, color=color)
            # Print the exact count above each bar — with only a handful of
            # scans there's room for it, and it reads more precise than
            # making someone trace a gridline back to the axis.
            ax.bar_label(bars, fmt="%d", color=CHART_FG, fontsize=FONT_SIZE_CHART_TICK, padding=2)
            # Headroom above the tallest bar so its label isn't clipped.
            top = max(values) if values else 0
            ax.set_ylim(0, top * 1.25 + 1)

            ax.set_xticks(x_positions)
            if i == len(self.axes) - 1:
                # Only the bottom-most subplot shows scan-time labels —
                # repeating them under every subplot was redundant clutter
                # since all four share the same scans.
                ax.set_xticklabels(tick_labels, fontsize=FONT_SIZE_CHART_TICK, color=CHART_FG, rotation=0)
            else:
                ax.tick_params(axis="x", labelbottom=False)

        # Fixed margins instead of tight_layout(): tight_layout()
        # recalculates spacing adaptively and would fight with the explicit
        # hspace set above, making the gap between subplots inconsistent
        # across refreshes. Static margins keep it predictable, and leave
        # room on the left for the "Devices" y-axis labels.
        self.figure.subplots_adjust(left=0.12, right=0.97, top=0.95, bottom=0.12, hspace=0.55)
        self.canvas.draw()