import os
import tempfile
import unittest
from datetime import datetime

from database.storage import Storage


def dev(ip, mac, vendor, hostname, status="online", seen="2026-09-04T10:00:00"):
    return {"ip": ip, "mac": mac, "vendor": vendor, "hostname": hostname,
            "status": status, "last_seen": seen}


class TestGetDevicesWithFilters(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.storage = Storage(os.path.join(self._tmp.name, "test.db"))
        self.home = self.storage.get_or_create_profile("Home")
        self.other = self.storage.get_or_create_profile("University")

        # Scan 1 (10:00): router, a laptop at .10, a phone at .2
        self.scan1 = self.storage.save_scan(
            [
                dev("192.168.1.1", "AA:AA:AA:AA:AA:01", "TP-Link", "router.lan"),
                dev("192.168.1.10", "AA:AA:AA:AA:AA:02", "Dell", "Laptop-01"),
                dev("192.168.1.2", "AA:AA:AA:AA:AA:03", "Apple", "iPhone"),
            ],
            datetime(2026, 9, 4, 10, 0, 0), self.home, "wireless", "192.168.1.0/24",
        )
        # Scan 2 (11:00): router again, a device outside the /24, one with no hostname/vendor,
        # and one that reports status "offline"
        self.scan2 = self.storage.save_scan(
            [
                dev("192.168.1.1", "AA:AA:AA:AA:AA:01", "TP-Link", "router.lan", seen="2026-09-04T11:00:00"),
                dev("10.0.0.5", "BB:BB:BB:BB:BB:05", None, None, seen="2026-09-04T11:00:00"),
                dev("192.168.1.20", "AA:AA:AA:AA:AA:04", "Sony", "PS5", status="offline", seen="2026-09-04T11:00:00"),
            ],
            datetime(2026, 9, 4, 11, 0, 0), self.home, "wireless", "192.168.1.0/24",
        )
        # A scan in a different profile that must never leak into Home's results
        self.other_scan = self.storage.save_scan(
            [dev("192.168.1.1", "CC:CC:CC:CC:CC:01", "Netgear", "router.lan")],
            datetime(2026, 9, 4, 10, 30, 0), self.other, "wired", "192.168.1.0/24",
        )

    def tearDown(self):
        self._tmp.cleanup()

    def ips(self, rows):
        return [r["ip"] for r in rows]

    # ---- scoping and shape ------------------------------------------------
    def test_no_filters_returns_only_this_profiles_rows(self):
        rows = self.storage.get_devices_with_filters(self.home)
        self.assertEqual(len(rows), 6)
        self.assertNotIn("CC:CC:CC:CC:CC:01", [r["mac"] for r in rows])

    def test_unknown_profile_returns_empty_list(self):
        self.assertEqual(self.storage.get_devices_with_filters(9999), [])

    def test_rows_are_dicts_with_scan_info_and_default_scan_time_order(self):
        rows = self.storage.get_devices_with_filters(self.home)
        self.assertEqual(
            set(rows[0]),
            {"scan_id", "scan_time", "ip", "mac", "vendor", "hostname", "status", "last_seen", "custom_name"},
        )
        self.assertEqual([r["scan_id"] for r in rows], [self.scan1] * 3 + [self.scan2] * 3)

    def test_custom_name_is_included(self):
        self.storage.set_device_name(self.home, "AA:AA:AA:AA:AA:01", "Main router")
        rows = self.storage.get_devices_with_filters(self.home, ip="192.168.1.1")
        self.assertEqual({r["custom_name"] for r in rows}, {"Main router"})

    # ---- individual filters -----------------------------------------------
    def test_scan_id(self):
        rows = self.storage.get_devices_with_filters(self.home, scan_id=self.scan2)
        self.assertEqual(sorted(self.ips(rows)), ["10.0.0.5", "192.168.1.1", "192.168.1.20"])

    def test_scan_id_from_another_profile_returns_nothing(self):
        self.assertEqual(self.storage.get_devices_with_filters(self.home, scan_id=self.other_scan), [])

    def test_status(self):
        rows = self.storage.get_devices_with_filters(self.home, status="offline")
        self.assertEqual(self.ips(rows), ["192.168.1.20"])

    def test_ip_exact(self):
        rows = self.storage.get_devices_with_filters(self.home, ip="192.168.1.1")
        self.assertEqual(len(rows), 2)  # seen in both scans

    def test_ip_range_uses_real_subnet_math(self):
        rows = self.storage.get_devices_with_filters(self.home, ip_range="192.168.1.0/24")
        self.assertNotIn("10.0.0.5", self.ips(rows))
        self.assertEqual(len(rows), 5)

    def test_ip_range_narrow_prefix(self):
        # /28 covers .0-.15: keeps .1, .2, .10 but not .20
        rows = self.storage.get_devices_with_filters(self.home, ip_range="192.168.1.0/28")
        self.assertEqual(sorted(set(self.ips(rows))), ["192.168.1.1", "192.168.1.10", "192.168.1.2"])

    def test_ip_range_ignores_host_bits(self):
        rows = self.storage.get_devices_with_filters(self.home, ip_range="10.0.0.99/24")
        self.assertEqual(self.ips(rows), ["10.0.0.5"])

    def test_vendor_is_case_insensitive(self):
        rows = self.storage.get_devices_with_filters(self.home, vendor="tp-link")
        self.assertEqual(len(rows), 2)

    def test_mac_ignores_case_and_separator(self):
        for query in ["aa:aa:aa:aa:aa:02", "AA-AA-AA-AA-AA-02", "aa-aa-aa-aa-aa-02"]:
            with self.subTest(query=query):
                rows = self.storage.get_devices_with_filters(self.home, mac=query)
                self.assertEqual(self.ips(rows), ["192.168.1.10"])

    def test_hostname_exact_case_insensitive(self):
        rows = self.storage.get_devices_with_filters(self.home, hostname="LAPTOP-01")
        self.assertEqual(self.ips(rows), ["192.168.1.10"])

    def test_hostname_is_exact_not_substring(self):
        self.assertEqual(self.storage.get_devices_with_filters(self.home, hostname="Laptop"), [])

    def test_hostname_regex(self):
        rows = self.storage.get_devices_with_filters(self.home, hostname_regex=r"^(laptop|ps5)")
        self.assertEqual(sorted(self.ips(rows)), ["192.168.1.10", "192.168.1.20"])

    def test_hostname_regex_skips_devices_without_hostname(self):
        rows = self.storage.get_devices_with_filters(self.home, hostname_regex=".*")
        self.assertNotIn("10.0.0.5", self.ips(rows))

    def test_date_range(self):
        rows = self.storage.get_devices_with_filters(
            self.home, start=datetime(2026, 9, 4, 10, 30), end=datetime(2026, 9, 4, 12, 0))
        self.assertEqual({r["scan_id"] for r in rows}, {self.scan2})

    def test_date_bounds_are_inclusive(self):
        rows = self.storage.get_devices_with_filters(
            self.home, start=datetime(2026, 9, 4, 10, 0, 0), end=datetime(2026, 9, 4, 10, 0, 0))
        self.assertEqual({r["scan_id"] for r in rows}, {self.scan1})

    # ---- combining, sorting ------------------------------------------------
    def test_filters_combine_with_and(self):
        rows = self.storage.get_devices_with_filters(
            self.home, ip_range="192.168.1.0/24", status="online", vendor="TP-Link", scan_id=self.scan2)
        self.assertEqual(self.ips(rows), ["192.168.1.1"])

    def test_sort_by_ip_is_numeric_not_lexical(self):
        rows = self.storage.get_devices_with_filters(self.home, scan_id=self.scan1, sort_by_ip=True)
        self.assertEqual(self.ips(rows), ["192.168.1.1", "192.168.1.2", "192.168.1.10"])

    def test_sort_by_ip_keeps_scan_order_for_the_same_ip(self):
        rows = self.storage.get_devices_with_filters(self.home, ip="192.168.1.1", sort_by_ip=True)
        self.assertEqual([r["scan_id"] for r in rows], [self.scan1, self.scan2])

    # ---- bad input raises instead of returning [] --------------------------
    def test_invalid_inputs_raise_value_error(self):
        bad_calls = [
            {"ip": "999.1.1.1"},
            {"ip": "192.168.1"},
            {"mac": "not-a-mac"},
            {"ip_range": "192.168.1.0"},       # no prefix length
            {"ip_range": "192.168.1.0/33"},
            {"hostname_regex": "(unclosed"},
        ]
        for kwargs in bad_calls:
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    self.storage.get_devices_with_filters(self.home, **kwargs)


if __name__ == "__main__":
    unittest.main()
