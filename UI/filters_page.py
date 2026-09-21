"""
ETHAN — Device filter page

A CustomTkinter page that lets the user search a profile's scan history with
Storage.get_devices_with_filters(): IP or range, MAC, vendor, hostname (exact
or regex), status, scan number and a custom date range, shown in a table.

Run it on its own from the repo root (the folder that contains database/ and UI/):

    python -m UI.filters_page                     # demo data in a throwaway database
    python -m UI.filters_page --db netwatch.db    # a real database, first profile
    python -m UI.filters_page --db netwatch.db --profile Home
"""

from __future__ import annotations

import argparse
import os
import tempfile
from datetime import datetime, timedelta
from tkinter import ttk

import customtkinter as ctk

from database.storage import Storage

STATUS_CHOICES = ["Any", "online", "offline"]

# (key in the row dict, column heading, width in pixels)
COLUMNS = (
    ("scan_time", "Scan time", 150),
    ("ip", "IP", 120),
    ("mac", "MAC", 140),
    ("vendor", "Vendor", 120),
    ("hostname", "Hostname", 140),
    ("custom_name", "Name", 110),
    ("status", "Status", 70),
    ("scan_id", "Scan #", 60),
)


# --------------------------------------------------------------------------- #
# Form -> Storage arguments. No widgets in here, so it is easy to test.
# --------------------------------------------------------------------------- #
def _parse_when(text: str, end_of_day: bool) -> datetime | None:
    """'2026-09-20' or '2026-09-20 14:30'. A bare date means the start of that day, or its last second for an end bound."""
    text = text.strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(text, fmt)
        except ValueError:
            continue
        if fmt == "%Y-%m-%d" and end_of_day:
            parsed = parsed.replace(hour=23, minute=59, second=59)
        return parsed
    raise ValueError(f"Can't read the date {text!r}. Use YYYY-MM-DD or YYYY-MM-DD HH:MM.")


def build_search_kwargs(raw: dict) -> dict:
    """
    Turns the raw form strings into keyword arguments for
    Storage.get_devices_with_filters(). Blank boxes are left out. Raises
    ValueError with a message that is fine to show the user.
    """
    kwargs: dict = {}

    ip_text = raw.get("ip", "").strip()
    if ip_text:
        # "192.168.1.0/24" is a range, "192.168.1.5" is a single address
        kwargs["ip_range" if "/" in ip_text else "ip"] = ip_text

    for key in ("mac", "vendor", "hostname", "hostname_regex"):
        text = raw.get(key, "").strip()
        if text:
            kwargs[key] = text

    status = raw.get("status", "Any")
    if status and status != "Any":
        kwargs["status"] = status

    scan_text = raw.get("scan_id", "").strip()
    if scan_text:
        try:
            kwargs["scan_id"] = int(scan_text)
        except ValueError:
            raise ValueError("Scan # must be a whole number.") from None

    start = _parse_when(raw.get("start", ""), end_of_day=False)
    end = _parse_when(raw.get("end", ""), end_of_day=True)
    if start is not None and end is not None and start > end:
        raise ValueError("The start date is after the end date.")
    if start is not None:
        kwargs["start"] = start
    if end is not None:
        kwargs["end"] = end

    kwargs["sort_by_ip"] = bool(raw.get("sort_by_ip"))
    return kwargs


# --------------------------------------------------------------------------- #
# The page
# --------------------------------------------------------------------------- #
class DeviceFiltersPage(ctk.CTkFrame):
    def __init__(self, master, storage: Storage, profile_id: int) -> None:
        super().__init__(master)
        self.storage = storage
        self.profile_id = profile_id
        self.entries: dict[str, ctk.CTkEntry] = {}
        self._build()
        self.search()

    # ---- layout ---------------------------------------------------------- #
    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        ctk.CTkLabel(self, text="Search devices", font=ctk.CTkFont(size=20, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=16, pady=(14, 4))

        form = ctk.CTkFrame(self)
        form.grid(row=1, column=0, sticky="ew", padx=16, pady=4)

        # (key, caption, placeholder, width). Captions stay visible even after a
        # box has been typed in and cleared, which placeholder text alone doesn't.
        row1 = [
            ("ip", "IP or range", "192.168.1.0/24", 200),
            ("mac", "MAC", "aa:bb:cc:dd:ee:ff", 180),
            ("vendor", "Vendor", "e.g. Apple", 130),
            ("hostname", "Hostname (exact)", "e.g. router.lan", 150),
            ("hostname_regex", "Hostname regex", "e.g. ^laptop", 150),
        ]
        row2 = [
            ("scan_id", "Scan #", "", 70),
            ("start", "From", "YYYY-MM-DD", 150),
            ("end", "To", "YYYY-MM-DD", 150),
        ]
        for col, field in enumerate(row1):
            self._add_field(form, *field, row=0, column=col)
        for col, field in enumerate(row2):
            self._add_field(form, *field, row=2, column=col)

        ctk.CTkLabel(form, text="Status", anchor="w", font=ctk.CTkFont(size=12)).grid(
            row=2, column=3, padx=8, pady=(6, 0), sticky="w")
        self.status_var = ctk.StringVar(value="Any")
        ctk.CTkOptionMenu(form, values=STATUS_CHOICES, variable=self.status_var, width=110).grid(
            row=3, column=3, padx=6, pady=(0, 8), sticky="w")

        self.sort_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(form, text="Sort by IP", variable=self.sort_var).grid(
            row=3, column=4, padx=6, pady=(0, 8), sticky="w")

        buttons = ctk.CTkFrame(form, fg_color="transparent")
        buttons.grid(row=3, column=5, padx=6, pady=(0, 8), sticky="e")
        ctk.CTkButton(buttons, text="Search", width=90, command=self.search).pack(side="left", padx=(0, 6))
        ctk.CTkButton(buttons, text="Clear", width=70, fg_color="gray40", hover_color="gray30",
                      command=self.clear).pack(side="left")

        self.message = ctk.CTkLabel(self, text="", anchor="w")
        self.message.grid(row=2, column=0, sticky="ew", padx=18, pady=(4, 0))

        table_frame = ctk.CTkFrame(self)
        table_frame.grid(row=3, column=0, sticky="nsew", padx=16, pady=(4, 14))
        table_frame.grid_columnconfigure(0, weight=1)
        table_frame.grid_rowconfigure(0, weight=1)

        self._style_table()
        self.table = ttk.Treeview(
            table_frame, columns=[c[0] for c in COLUMNS], show="headings", style="Devices.Treeview")
        for key, heading, width in COLUMNS:
            self.table.heading(key, text=heading)
            self.table.column(key, width=width, anchor="w")
        scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.table.yview)
        self.table.configure(yscrollcommand=scroll.set)
        self.table.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")

    def _add_field(self, parent, key: str, caption: str, placeholder: str, width: int,
                   row: int, column: int) -> None:
        ctk.CTkLabel(parent, text=caption, anchor="w", font=ctk.CTkFont(size=12)).grid(
            row=row, column=column, padx=8, pady=(6, 0), sticky="w")
        entry = ctk.CTkEntry(parent, placeholder_text=placeholder, width=width)
        entry.grid(row=row + 1, column=column, padx=6, pady=(0, 8), sticky="w")
        entry.bind("<Return>", lambda _event: self.search())
        self.entries[key] = entry

    def _style_table(self) -> None:
        dark = ctk.get_appearance_mode() == "Dark"
        bg, fg, head_bg, select = (
            ("#2b2b2b", "#e6e6e6", "#3a3a3a", "#1f6aa5") if dark
            else ("#ffffff", "#1a1a1a", "#e3e3e3", "#3b8ed0")
        )
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Devices.Treeview", background=bg, fieldbackground=bg, foreground=fg,
                        rowheight=26, borderwidth=0)
        style.configure("Devices.Treeview.Heading", background=head_bg, foreground=fg,
                        relief="flat", font=("Segoe UI", 10, "bold"))
        style.map("Devices.Treeview", background=[("selected", select)], foreground=[("selected", "#ffffff")])

    # ---- behaviour ------------------------------------------------------- #
    def search(self) -> None:
        raw = {key: entry.get() for key, entry in self.entries.items()}
        raw["status"] = self.status_var.get()
        raw["sort_by_ip"] = self.sort_var.get()
        try:
            kwargs = build_search_kwargs(raw)
            rows = self.storage.get_devices_with_filters(self.profile_id, **kwargs)
        except ValueError as exc:
            self._show_message(str(exc), error=True)
            return
        self._fill_table(rows)

    def clear(self) -> None:
        for entry in self.entries.values():
            entry.delete(0, "end")
        self.status_var.set("Any")
        self.sort_var.set(False)
        self.search()

    def _fill_table(self, rows: list[dict]) -> None:
        self.table.delete(*self.table.get_children())
        for row in rows:
            self.table.insert(
                "", "end",
                values=[self._cell(row, key) for key, _heading, _width in COLUMNS],
            )
        if rows:
            self._show_message(f"{len(rows)} row(s). Each row is one device in one scan.")
        else:
            self._show_message("No devices match these filters.")

    @staticmethod
    def _cell(row: dict, key: str) -> str:
        value = row.get(key)
        if value is None:
            return ""
        return str(value).replace("T", " ") if key == "scan_time" else str(value)

    def _show_message(self, text: str, error: bool = False) -> None:
        self.message.configure(text=text, text_color=("#c0392b", "#ff6b6b") if error else ("gray30", "gray70"))


# --------------------------------------------------------------------------- #
# Running it on its own
# --------------------------------------------------------------------------- #
def _seed_demo(storage: Storage) -> int:
    """Fills a throwaway database with a few scans so every filter has something to find."""
    profile_id = storage.get_or_create_profile("Demo")
    now = datetime.now().replace(microsecond=0)

    def dev(ip, mac, vendor, hostname, status="online"):
        return {"ip": ip, "mac": mac, "vendor": vendor, "hostname": hostname,
                "status": status, "last_seen": now.isoformat(timespec="seconds")}

    router = dev("192.168.1.1", "AA:BB:CC:00:00:01", "TP-Link", "router.lan")
    laptop = dev("192.168.1.10", "AA:BB:CC:00:00:02", "Dell", "Laptop-01")
    phone = dev("192.168.1.2", "AA:BB:CC:00:00:03", "Apple", "iPhone")
    tv = dev("192.168.1.30", "AA:BB:CC:00:00:04", "Samsung", "Living-Room-TV")
    printer = dev("192.168.1.50", "AA:BB:CC:00:00:05", "HP", "printer-hp")
    unknown = dev("192.168.1.77", "AA:BB:CC:00:00:06", None, None)
    guest = dev("10.0.0.5", "DD:EE:FF:00:00:07", "Xiaomi", "guest-phone")
    console = dev("192.168.1.20", "AA:BB:CC:00:00:08", "Sony", "PS5", status="offline")

    storage.save_scan([router, laptop, phone, tv], now - timedelta(days=2), profile_id, "wireless", "192.168.1.0/24")
    storage.save_scan([router, laptop, phone, printer, unknown], now - timedelta(days=1), profile_id, "wireless", "192.168.1.0/24")
    storage.save_scan([router, laptop, tv, unknown, guest, console], now, profile_id, "wireless", "192.168.1.0/24")
    storage.set_device_name(profile_id, "AA:BB:CC:00:00:02", "Ethan's laptop")
    return profile_id


def _pick_profile(storage: Storage, wanted: str | None) -> int:
    profiles = storage.list_profiles()
    if not profiles:
        raise SystemExit("That database has no profiles yet, so there is nothing to show.")
    if wanted is None:
        return profiles[0]["id"]
    for profile in profiles:
        if profile["name"].lower() == wanted.lower():
            return profile["id"]
    names = ", ".join(p["name"] for p in profiles)
    raise SystemExit(f"No profile called {wanted!r}. This database has: {names}")


def _run(storage: Storage, profile_id: int) -> None:
    ctk.set_appearance_mode("dark")
    window = ctk.CTk()
    window.title("NetWatch - Search devices")
    window.geometry("1150x600")
    page = DeviceFiltersPage(window, storage, profile_id)
    page.pack(fill="both", expand=True)
    window.mainloop()


def main() -> None:
    parser = argparse.ArgumentParser(description="Standalone viewer for the device filter page.")
    parser.add_argument("--db", help="path to a NetWatch database; omit to use demo data")
    parser.add_argument("--profile", help="profile name to show (default: the first one)")
    args = parser.parse_args()

    if args.db:
        if not os.path.exists(args.db):
            raise SystemExit(f"Database file not found: {args.db}")
        storage = Storage(args.db)
        _run(storage, _pick_profile(storage, args.profile))
    else:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(os.path.join(tmp, "demo.db"))
            _run(storage, _seed_demo(storage))


if __name__ == "__main__":
    main()
