import customtkinter as ctk
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from datetime import datetime, timedelta

import netwatch_db as db


class HealthPanel(ctk.CTkFrame):
    """
    A self-contained panel showing:
      - the latest scan's health score as a progress bar + breakdown text
      - a trend chart of health scores over a date range

    Usage:
        panel = HealthPanel(parent, connection, ip_range="192.168.1.0/24")
        panel.pack(fill="both", expand=True)
        panel.refresh()   # call after a new scan completes
    """

    def __init__(self, master, connection, ip_range, trend_days=14, **kwargs):
        super().__init__(master, **kwargs)
        self.connection = connection
        self.ip_range = ip_range
        self.trend_days = trend_days

        self._build_score_section()
        self._build_trend_section()
        self.refresh()


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

        trend_title = ctk.CTkLabel(trend_frame, text=f"Trend (last {self.trend_days} days)",
                                    font=ctk.CTkFont(size=14, weight="bold"))
        trend_title.pack(anchor="w", padx=10, pady=(10, 0))

        # dark-friendly matplotlib figure, transparent background so it blends with CTk
        self.figure = Figure(figsize=(5, 3), dpi=100)
        self.figure.patch.set_alpha(0)
        self.ax = self.figure.add_subplot(111)

        self.canvas = FigureCanvasTkAgg(self.figure, master=trend_frame)
        self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=10, pady=10)



    def refresh(self):
        """Re-pull the latest score and trend data and redraw both widgets."""
        self._refresh_current_score()
        self._refresh_trend_chart()

    def _get_latest_scan_id(self):
        cursor = self.connection.cursor()
        cursor.execute(
            "SELECT id FROM scans WHERE ip_range = ? ORDER BY timestamp DESC LIMIT 1",
            (self.ip_range,)
        )
        row = cursor.fetchone()
        return row[0] if row else None

    def _refresh_current_score(self):
        latest_scan_id = self._get_latest_scan_id()
        if latest_scan_id is None:
            self.score_label.configure(text="No scans yet")
            self.progress_bar.set(0)
            self.breakdown_label.configure(text="")
            return

        row = db.get_health_score(self.connection, latest_scan_id)
        if row is None:
            self.score_label.configure(text="No score yet")
            self.progress_bar.set(0)
            self.breakdown_label.configure(text="Run a scan to generate a health score.")
            return

       
        _, _, score, new_devices, missing_devices, unknown_vendors, offline_devices = row

        self.score_label.configure(text=f"{score:.0f} / 100")
        self.progress_bar.set(score / 100)
        self.progress_bar.configure(progress_color=self._color_for_score(score))

        self.breakdown_label.configure(
            text=(
                f"New devices: {new_devices}   "
                f"Missing: {missing_devices}   "
                f"Unknown vendor: {unknown_vendors}   "
                f"Offline: {offline_devices}"
            )
        )

    def _refresh_trend_chart(self):
        end_date = datetime.now()
        start_date = end_date - timedelta(days=self.trend_days)
        rows = db.get_health_trend(
            self.connection,
            start_date.strftime("%Y-%m-%d %H:%M:%S"),
            end_date.strftime("%Y-%m-%d %H:%M:%S")
        )

        self.ax.clear()

        if not rows:
            self.ax.text(0.5, 0.5, "No data yet", ha="center", va="center", transform=self.ax.transAxes)
        else:
            timestamps = [r[0] for r in rows]
            scores = [r[1] for r in rows]
            self.ax.plot(timestamps, scores, marker="o", linewidth=1.5)
            self.ax.set_ylim(0, 100)
            self.ax.set_ylabel("Score")
            self.ax.tick_params(axis="x", rotation=45, labelsize=7)
            self.figure.tight_layout()

        self.canvas.draw()

    @staticmethod
    def _color_for_score(score):
        if score >= 80:
            return "#2ecc71"   # green
        elif score >= 50:
            return "#f1c40f"   # yellow
        else:
            return "#e74c3c"   # red


# ---------- standalone test/demo ----------

if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    conn = db.create_connection("netwatch.db")
    db.create_tables(conn)

    root = ctk.CTk()
    root.title("NetWatch - Health")
    root.geometry("600x500")

    panel = HealthPanel(root, conn, ip_range="192.168.1.0/24")
    panel.pack(fill="both", expand=True)

    root.mainloop()
