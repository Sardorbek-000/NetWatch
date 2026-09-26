"""
NetWatch — Health page (Module 3 / Ethan's Task 4)
================================================================
Shows the current profile's latest scan stats plus separate trend
graphs (total devices, new devices, missing devices, unknown-vendor
devices) with a 7 days / 30 days / All range selector. Bars are
clickable — picking one opens a popup listing the actual devices
behind that count for that scan.

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
  - Explainability pass (per teacher feedback, take 2): a caption under
    the graphs spells out what "new"/"missing" mean and that bars are
    clickable; the "Total devices" snapshot number now shows its change
    since the previous scan (new_devices/missing_devices are ALREADY a
    period-over-period comparison to the previous scan by definition —
    see _compute_health_score() in storage.py — so a separate "+2 since
    last scan" line for those would just repeat numbers already on
    screen; device_count is the one metric that's a running total rather
    than a per-scan delta, so it's the one that benefits from showing
    its own change).
  - Click-to-detail: clicking a bar opens a small popup listing the
    devices behind that count, using the SAME previous-scan definition
    the score itself uses (Storage.get_previous_scan_id(), same subnet)
    rather than an approximation, so the popup's device list always
    matches the number on the bar.
  - Export: a "Save chart" button writes the current four-graph figure
    to a PNG the user picks a location for.
"""

from datetime import datetime, timedelta
from tkinter import filedialog

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

CAPTION_TEXT = (
    "Each bar is one scan. \"New\" / \"Missing\" compare a scan only to the "
    "scan immediately before it, not to the whole history. Click a bar to "
    "see which devices it's counting."
)


class HealthPage(ctk.CTkFrame):
    """Current profile's latest scan stats + four clickable metric-trend bar charts."""

    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self._current_rows = []  # rows behind the currently-drawn bars, same order as the x-axis

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
        self.range_selector.pack(side="right", padx=(8, 0))

        self.export_button = ctk.CTkButton(header_frame, text="Save chart", width=90,
                                            command=self._export_chart)
        self.export_button.pack(side="right")

        # Stacked subplots, one per metric, sharing an x-axis so e.g. the
        # "new" vs "missing" graphs can be visually compared scan-to-scan.
        self.figure = Figure(figsize=(5, 6.8), dpi=100, facecolor=CHART_BG)
        self.axes = self.figure.subplots(nrows=len(TREND_METRICS), ncols=1, sharex=True)
        # Extra vertical gap between subplots so titles/tick labels don't
        # crowd the chart above/below them.
        self.figure.subplots_adjust(hspace=0.55)

        self.canvas = FigureCanvasTkAgg(self.figure, master=trend_frame)
        self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=14, pady=(6, 4))
        # Bars are clickable — see _on_bar_click() for what happens.
        self.canvas.mpl_connect("button_press_event", self._on_bar_click)

        self.caption_label = ctk.CTkLabel(
            trend_frame, text=CAPTION_TEXT, font=ctk.CTkFont(size=FONT_SIZE_CAPTION),
            text_color="gray60", justify="left", anchor="w", wraplength=700
        )
        self.caption_label.pack(fill="x", padx=14, pady=(0, 14))

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

        latest_count = history[-1]["device_count"]
        # device_count is a running total, not a delta, so — unlike
        # new_devices/missing_devices, which already ARE the change since
        # the previous scan — it's the one number here worth diffing
        # against the previous scan itself. len(history) > 1 guards the
        # very first scan, which has nothing before it to compare to.
        if len(history) > 1:
            previous_count = history[-2]["device_count"]
            delta = latest_count - previous_count
            delta_text = f" ({'+' if delta >= 0 else ''}{delta} since last scan)"
        else:
            delta_text = ""

        self.snapshot_label.configure(
            text=(
                f"Total devices: {latest_count}{delta_text}     "
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
        self._current_rows = rows  # remembered for _on_bar_click()

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

    # ------------------------------------------------------------------ #
    # Click-to-detail
    # ------------------------------------------------------------------ #
    def _on_bar_click(self, event):
        if event.inaxes not in self.axes or not self._current_rows:
            return

        metric_index = list(self.axes).index(event.inaxes)
        key, title, _color = TREND_METRICS[metric_index]

        # Find which bar (if any) was actually clicked, rather than
        # guessing from event.xdata alone — robust to the bar width and
        # to clicks that land in the gap between bars (those are ignored).
        clicked_row_index = None
        for i, bar in enumerate(event.inaxes.patches):
            if bar.contains(event)[0]:
                clicked_row_index = i
                break
        if clicked_row_index is None or clicked_row_index >= len(self._current_rows):
            return

        row = self._current_rows[clicked_row_index]
        self._show_detail_popup(key, title, row)

    def _show_detail_popup(self, key, title, row):
        scan_id = row["scan_id"]
        storage = self.app.storage

        if key == "device_count":
            devices = storage.get_devices_for_scan(scan_id)
        elif key == "unknown_vendors":
            devices = [d for d in storage.get_devices_for_scan(scan_id) if not d["vendor"]]
        else:
            # new_devices / missing_devices: same "previous scan" definition
            # the score itself was computed from (same profile, same
            # subnet), so the popup's list always matches the bar's number.
            previous_scan_id = storage.get_previous_scan_id(scan_id)
            if previous_scan_id is None:
                devices = []
            else:
                comparison = storage.compare_scans(previous_scan_id, scan_id)
                devices = comparison["new_devices"] if key == "new_devices" else comparison["disconnected_devices"]

        popup = ctk.CTkToplevel(self)
        popup.title(f"{title} — scan at {row['scan_time']}")
        popup.geometry("480x360")
        # Keep the popup above the main window and focused, same pattern
        # CustomTkinter apps typically use for detail dialogs.
        popup.transient(self.winfo_toplevel())
        popup.grab_set()

        header = ctk.CTkLabel(popup, text=f"{title} ({len(devices)})",
                               font=ctk.CTkFont(size=FONT_SIZE_SECTION_TITLE, weight="bold"))
        header.pack(anchor="w", padx=14, pady=(14, 4))

        if not devices:
            ctk.CTkLabel(popup, text="No devices in this category for this scan.",
                         text_color="gray60").pack(anchor="w", padx=14, pady=(0, 14))
        else:
            list_frame = ctk.CTkScrollableFrame(popup)
            list_frame.pack(fill="both", expand=True, padx=14, pady=(0, 14))
            for device in devices:
                label = device["custom_name"] or device["hostname"] or "(unnamed device)"
                text = f"{label}   {device['ip']}   {device['mac']}"
                if device["vendor"]:
                    text += f"   {device['vendor']}"
                ctk.CTkLabel(list_frame, text=text, anchor="w", justify="left").pack(fill="x", pady=2)

        ctk.CTkButton(popup, text="Close", width=90, command=popup.destroy).pack(pady=(0, 14))

    # ------------------------------------------------------------------ #
    # Export
    # ------------------------------------------------------------------ #
    def _export_chart(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("PNG image", "*.png")],
            title="Save chart as",
        )
        if not path:
            return  # user cancelled
        try:
            self.figure.savefig(path, facecolor=CHART_BG)
        except OSError as e:
            # Don't crash the page over a bad path/permissions issue —
            # just report it inline the same way other pages surface errors.
            ctk.CTkLabel(self, text=f"Couldn't save chart: {e}", text_color="#e74c3c").pack(pady=(0, 6))