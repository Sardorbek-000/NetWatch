"""
NetWatch — shared UI color constants.

Pulled out of app.py so any page file that needs them (scan_page,
scan_detail_page, compare_scans_page, settings_page, ...) imports from
here instead of each page redefining its own copies, which would drift
out of sync over time.
"""

NEW_DEVICE_COLOR = "#2ecc71"
DISCONNECTED_COLOR = "#e74c3c"
DANGER_COLOR = "#a83232"
DANGER_HOVER_COLOR = "#822424"
