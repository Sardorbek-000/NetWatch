from __future__ import annotations

from datetime import datetime
from tkinter import messagebox

import customtkinter as ctk


class HistoryPage(ctk.CTkFrame):
    def __init__(self, parent, app: NetWatchApp) -> None:
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self.selected_for_compare: list[int] = []

        ctk.CTkLabel(self, text="History", font=ctk.CTkFont(size=24, weight="bold")).pack(pady=(20, 10))

        filter_row = ctk.CTkFrame(self, fg_color="transparent")
        filter_row.pack(pady=5)
        ctk.CTkLabel(filter_row, text="From (YYYY-MM-DD):").grid(row=0, column=0, padx=5)
        self.start_entry = ctk.CTkEntry(filter_row, width=120)
        self.start_entry.grid(row=0, column=1, padx=5)
        ctk.CTkLabel(filter_row, text="To (YYYY-MM-DD):").grid(row=0, column=2, padx=5)
        self.end_entry = ctk.CTkEntry(filter_row, width=120)
        self.end_entry.grid(row=0, column=3, padx=5)
        ctk.CTkButton(filter_row, text="Filter", width=80, command=self._load_history).grid(row=0, column=4, padx=5)
        ctk.CTkButton(filter_row, text="Clear", width=80, command=self._clear_filter).grid(row=0, column=5, padx=5)

        self.list_frame = ctk.CTkScrollableFrame(self, width=780, height=300)
        self.list_frame.pack(pady=10, fill="both", expand=True)

        self.compare_status = ctk.CTkLabel(self, text="Select up to two scans (checkboxes) to compare.")
        self.compare_status.pack(pady=5)

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(pady=10)
        ctk.CTkButton(btn_row, text="Compare Selected", width=160, command=self._compare).pack(side="left", padx=10)
        ctk.CTkButton(
            btn_row, text="Back to Profile", width=160, fg_color="gray40", hover_color="gray30",
            command=lambda: app.show_frame("ProfilePage"),
        ).pack(side="left", padx=10)

    def on_show(self) -> None:
        self.selected_for_compare = []
        self.start_entry.delete(0, "end")
        self.end_entry.delete(0, "end")
        self.compare_status.configure(text="Select up to two scans (checkboxes) to compare.")
        self._load_history()

    def _clear_filter(self) -> None:
        self.start_entry.delete(0, "end")
        self.end_entry.delete(0, "end")
        self._load_history()

    def _parse_date(self, text: str, end_of_day: bool = False) -> datetime | None:
        text = text.strip()
        if not text:
            return None
        try:
            dt = datetime.strptime(text, "%Y-%m-%d")
        except ValueError:
            messagebox.showwarning("Invalid date", f"'{text}' isn't in YYYY-MM-DD format.")
            return None
        return dt.replace(hour=23, minute=59, second=59) if end_of_day else dt

    def _load_history(self) -> None:
        for child in self.list_frame.winfo_children():
            child.destroy()
        start = self._parse_date(self.start_entry.get())
        end = self._parse_date(self.end_entry.get(), end_of_day=True)
        history = self.app.storage.get_scan_history(self.app.current_profile_id, start, end)
        if not history:
            ctk.CTkLabel(self.list_frame, text="No scans in this range.").pack(pady=10)
            return
        for s in reversed(history):  # newest first
            row = ctk.CTkFrame(self.list_frame)
            row.pack(fill="x", pady=2, padx=2)
            var = ctk.BooleanVar(value=(s["id"] in self.selected_for_compare))
            ctk.CTkCheckBox(
                row, text="", width=20, variable=var, command=lambda sid=s["id"], v=var: self._toggle_compare(sid, v)
            ).pack(side="left", padx=5)
            ctk.CTkLabel(
                row, text=f"#{s['id']}   {s['scan_time']}   {s['scan_type']}   {s['device_count']} device(s)"
            ).pack(side="left", padx=5)
            ctk.CTkButton(row, text="View", width=70, command=lambda sid=s["id"]: self.app.show_frame("ScanDetailPage", scan_id=sid)).pack(
                side="right", padx=5
            )

    def _toggle_compare(self, scan_id: int, var) -> None:
        if var.get():
            if len(self.selected_for_compare) >= 2:
                var.set(False)
                messagebox.showinfo("Limit reached", "You can only compare two scans at a time.")
                return
            self.selected_for_compare.append(scan_id)
        elif scan_id in self.selected_for_compare:
            self.selected_for_compare.remove(scan_id)
        self.compare_status.configure(text=f"Selected: {self.selected_for_compare or 'none'}")

    def _compare(self) -> None:
        if len(self.selected_for_compare) != 2:
            messagebox.showwarning("Select two scans", "Please select exactly two scans to compare.")
            return
        scan_a, scan_b = sorted(self.selected_for_compare)  # lower id = earlier scan
        self.app.show_frame("CompareScansPage", scan_id_a=scan_a, scan_id_b=scan_b)
