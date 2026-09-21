"""Tests for the health-score methods on Storage (ETHAN)."""
from datetime import datetime, timedelta

import pytest

from database.storage import Storage

T0 = datetime(2026, 9, 1, 10, 0, 0)


def dev(n, vendor="Acme"):
    return {
        "ip": f"192.168.1.{n}",
        "mac": f"AA:AA:AA:AA:AA:{n:02X}",
        "vendor": vendor,
        "hostname": None,
        "status": "online",
        "last_seen": "2026-09-01T10:00:00",
    }


@pytest.fixture
def storage(tmp_path):
    return Storage(str(tmp_path / "test.db"))


@pytest.fixture
def home(storage):
    return storage.get_or_create_profile("Home")


def scan(storage, profile_id, minutes, devices, subnet="192.168.1.0/24"):
    return storage.save_scan(devices, T0 + timedelta(minutes=minutes), profile_id, "wireless", subnet)


def test_first_scan_with_known_vendors_scores_100(storage, home):
    scan_id = scan(storage, home, 0, [dev(1), dev(2), dev(3)])
    assert storage.ensure_health_scores(home) == 1
    row = storage.get_health_score(scan_id)
    assert row["score"] == 100
    assert (row["new_devices"], row["missing_devices"], row["unknown_vendors"]) == (0, 0, 0)


def test_first_scan_only_loses_points_for_unknown_vendors(storage, home):
    scan_id = scan(storage, home, 0, [dev(1, vendor=None), dev(2, vendor=""), dev(3), dev(4)])
    storage.ensure_health_scores(home)
    row = storage.get_health_score(scan_id)
    assert row["unknown_vendors"] == 2
    assert row["new_devices"] == row["missing_devices"] == 0
    assert row["score"] == pytest.approx(100 - 0.5 * 100 / 3, abs=0.01)


def test_new_and_missing_counted_against_previous_scan(storage, home):
    scan(storage, home, 0, [dev(1), dev(2), dev(3)])
    second = scan(storage, home, 5, [dev(1), dev(2), dev(9)])  # 3 left, 9 arrived
    storage.ensure_health_scores(home)
    row = storage.get_health_score(second)
    assert (row["new_devices"], row["missing_devices"]) == (1, 1)
    assert row["score"] == pytest.approx(100 - (1 / 3 + 1 / 3) * 100 / 3, abs=0.01)


def test_identical_repeat_scan_scores_100(storage, home):
    scan(storage, home, 0, [dev(1), dev(2)])
    second = scan(storage, home, 5, [dev(1), dev(2)])
    storage.ensure_health_scores(home)
    assert storage.get_health_score(second)["score"] == 100


def test_previous_scan_ignores_other_profiles_and_other_subnets(storage, home):
    other = storage.get_or_create_profile("Uni")
    scan(storage, other, 0, [dev(50), dev(51)])                         # different profile
    scan(storage, home, 1, [dev(60)], subnet="10.0.0.0/24")             # same profile, other subnet
    first = scan(storage, home, 5, [dev(1), dev(2)])
    storage.ensure_health_scores(home)
    row = storage.get_health_score(first)
    assert (row["new_devices"], row["missing_devices"]) == (0, 0)       # treated as a first scan


def test_scores_are_filled_in_time_order_even_if_scans_were_saved_out_of_order(storage, home):
    later = scan(storage, home, 10, [dev(1), dev(2), dev(3)])
    earlier = scan(storage, home, 0, [dev(1), dev(2)])
    assert storage.ensure_health_scores(home) == 2
    assert storage.get_health_score(earlier)["new_devices"] == 0        # it is the first scan
    assert storage.get_health_score(later)["new_devices"] == 1          # device 3 is new since `earlier`


def test_ensure_is_idempotent_and_only_scores_new_scans(storage, home):
    scan(storage, home, 0, [dev(1)])
    assert storage.ensure_health_scores(home) == 1
    assert storage.ensure_health_scores(home) == 0
    scan(storage, home, 5, [dev(1)])
    assert storage.ensure_health_scores(home) == 1