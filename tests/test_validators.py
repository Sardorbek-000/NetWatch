import unittest

from core.validators import is_valid_ip, is_valid_ip_range, is_valid_mac


class TestIsValidIp(unittest.TestCase):
    def test_valid(self):
        for value in ["192.168.1.1", "0.0.0.0", "255.255.255.255", "10.0.0.254"]:
            with self.subTest(value=value):
                self.assertTrue(is_valid_ip(value))

    def test_invalid(self):
        for value in [
            "256.1.1.1",       # octet out of range
            "192.168.1",       # too few octets
            "192.168.1.1.1",   # too many octets
            "192.168.01.1",    # leading zero
            " 192.168.1.1",    # whitespace
            "192.168.1.1\n",   # trailing newline
            "a.b.c.d",
            "::1",             # IPv6 not supported
            "",
            None,
            3232235777,        # int, not a string
        ]:
            with self.subTest(value=value):
                self.assertFalse(is_valid_ip(value))


class TestIsValidMac(unittest.TestCase):
    def test_valid(self):
        for value in [
            "aa:bb:cc:dd:ee:ff",
            "AA:BB:CC:DD:EE:FF",
            "aa-bb-cc-dd-ee-ff",   # Windows arp -a style
            "00:1A:2b:3C:4d:5E",
        ]:
            with self.subTest(value=value):
                self.assertTrue(is_valid_mac(value))

    def test_invalid(self):
        for value in [
            "aa:bb:cc:dd:ee",        # too short
            "aa:bb:cc:dd:ee:ff:00",  # too long
            "aa:bb-cc:dd-ee:ff",     # mixed separators
            "gg:bb:cc:dd:ee:ff",     # non-hex
            "aabb.ccdd.eeff",        # Cisco style, not supported
            "aabbccddeeff",
            "aa:bb:cc:dd:ee:ff\n",
            "",
            None,
        ]:
            with self.subTest(value=value):
                self.assertFalse(is_valid_mac(value))


class TestIsValidIpRange(unittest.TestCase):
    def test_valid(self):
        for value in ["192.168.1.0/24", "10.0.0.0/8", "172.16.0.0/12", "192.168.1.1/32"]:
            with self.subTest(value=value):
                self.assertTrue(is_valid_ip_range(value))

    def test_host_bits_lenient_by_default(self):
        self.assertTrue(is_valid_ip_range("192.168.1.5/24"))

    def test_host_bits_rejected_when_strict(self):
        self.assertFalse(is_valid_ip_range("192.168.1.5/24", strict=True))
        self.assertTrue(is_valid_ip_range("192.168.1.0/24", strict=True))

    def test_invalid(self):
        for value in [
            "192.168.1.0",       # no prefix length
            "192.168.1.0/33",    # prefix too large
            "192.168.1.0/",      # empty prefix
            "192.168.1.0/-1",
            "192.168.1.0/abc",
            "300.168.1.0/24",    # bad address
            "/24",
            "",
            None,
        ]:
            with self.subTest(value=value):
                self.assertFalse(is_valid_ip_range(value))


if __name__ == "__main__":
    unittest.main()
