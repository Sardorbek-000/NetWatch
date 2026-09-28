"""Tests for the watched-device missed-scan threshold (Storage.get_flag_alerts and friends)."""
from datetime import datetime, timedelta

import pytest

from database.storage import DEFAULT_MISSED_SCAN_THRESHOLD, Storage

WATCHED = "AA:AA:AA:AA:AA:01"
OTHER = "AA:AA:AA:AA:AA:02"


@pytest.fixture
def storage(tmp_path):
    return Storage(str(tmp_path / "watch.db"))


@pytest.fixture
def profile(storage):
    return storage.get_or_create_profile("Home")


def _device(mac):
    return {"ip": "192.168.1.10", "mac": mac, "vendor": None, "hostname": None,
            "status": "online", "last_seen": "2026-09-28T10:00:00"}


def run_scans(storage, profile, presence):
    """presence: list of bools, one per scan — is the watched device in that scan? OTHER is always there."""
    t0 = datetime(2026, 9, 28, 10, 0, 0)
    for i, present in enumerate(presence):
        devices = [_device(OTHER)] + ([_device(WATCHED)] if present else [])
        storage.save_scan(devices, t0 + timedelta(minutes=5 * i), profile, "wireless", "192.168.1.0/24")


def events(storage, profile):
    return [(a["mac"], a["event"]) for a in storage.get_flag_alerts(profile)]


# ---- threshold setting ----------------------------------------------------
def test_default_threshold(storage, profile):
    assert storage.get_missed_scan_threshold(profile) == DEFAULT_MISSED_SCAN_THRESHOLD == 2


def test_set_and_update_threshold(storage, profile):
    storage.set_missed_scan_threshold(profile, 4)
    assert storage.get_missed_scan_threshold(profile) == 4
    storage.set_missed_scan_threshold(profile, 3)
    assert storage.get_missed_scan_threshold(profile) == 3


def test_threshold_is_per_profile(storage, profile):
    other = storage.get_or_create_profile("University")
    storage.set_missed_scan_threshold(profile, 5)
    assert storage.get_missed_scan_threshold(other) == DEFAULT_MISSED_SCAN_THRESHOLD


@pytest.mark.parametrize("bad", [0, -1, 1.5, "2", None, True])
def test_invalid_threshold_rejected(storage, profile, bad):
    with pytest.raises(ValueError):
        storage.set_missed_scan_threshold(profile, bad)


def test_deleting_profile_removes_setting(storage, profile):
    storage.set_missed_scan_threshold(profile, 4)
    storage.delete_profile(profile)
    assert storage.get_missed_scan_threshold(profile) == DEFAULT_MISSED_SCAN_THRESHOLD


# ---- disappeared ----------------------------------------------------------
def test_no_alert_when_nothing_flagged(storage, profile):
    run_scans(storage, profile, [True, False, False])
    assert storage.get_flag_alerts(profile) == []


def test_single_miss_is_silent_at_default_threshold(storage, profile):
    storage.flag_device(profile, WATCHED)
    run_scans(storage, profile, [True, True, False])
    assert events(storage, profile) == []


def test_alert_fires_on_nth_consecutive_miss(storage, profile):
    storage.flag_device(profile, WATCHED)
    run_scans(storage, profile, [True, True, False, False])
    alerts = storage.get_flag_alerts(profile)
    assert [(a["mac"], a["event"], a["missed_scans"]) for a in alerts] == [(WATCHED, "disappeared", 2)]
    assert alerts[0]["custom_name"] is None
    assert alerts[0]["scan_time"]


def test_alert_does_not_repeat_on_later_misses(storage, profile):
    storage.flag_device(profile, WATCHED)
    run_scans(storage, profile, [True, False, False, False])
    assert events(storage, profile) == []


def test_threshold_one_alerts_on_first_miss(storage, profile):
    storage.set_missed_scan_threshold(profile, 1)
    storage.flag_device(profile, WATCHED)
    run_scans(storage, profile, [True, False])
    assert events(storage, profile) == [(WATCHED, "disappeared")]


def test_higher_threshold_waits_longer(storage, profile):
    storage.set_missed_scan_threshold(profile, 3)
    storage.flag_device(profile, WATCHED)
    run_scans(storage, profile, [True, False, False])
    assert events(storage, profile) == []
    run_scans(storage, profile, [False])
    assert events(storage, profile) == [(WATCHED, "disappeared")]


def test_not_enough_history_is_silent(storage, profile):
    storage.set_missed_scan_threshold(profile, 3)
    storage.flag_device(profile, WATCHED)
    run_scans(storage, profile, [False, False, False])
    assert events(storage, profile) == []


def test_never_seen_device_never_alerts(storage, profile):
    storage.flag_device(profile, WATCHED)
    run_scans(storage, profile, [False, False, False, False])
    assert events(storage, profile) == []


def test_single_scan_returns_empty(storage, profile):
    storage.flag_device(profile, WATCHED)
    run_scans(storage, profile, [True])
    assert storage.get_flag_alerts(profile) == []


# ---- reappeared -----------------------------------------------------------
def test_reappeared_after_alertable_gap(storage, profile):
    storage.flag_device(profile, WATCHED)
    run_scans(storage, profile, [True, False, False, True])
    alerts = storage.get_flag_alerts(profile)
    assert [(a["event"], a["missed_scans"]) for a in alerts] == [("reappeared", 2)]


def test_reappeared_reports_full_gap_length(storage, profile):
    storage.flag_device(profile, WATCHED)
    run_scans(storage, profile, [True, False, False, False, False, True])
    alerts = storage.get_flag_alerts(profile)
    assert [(a["event"], a["missed_scans"]) for a in alerts] == [("reappeared", 4)]


def test_short_blip_gives_no_reappeared_alert(storage, profile):
    storage.flag_device(profile, WATCHED)
    run_scans(storage, profile, [True, False, True])
    assert events(storage, profile) == []


def test_alert_clears_once_device_stays_back(storage, profile):
    storage.flag_device(profile, WATCHED)
    run_scans(storage, profile, [True, False, False, True, True])
    assert events(storage, profile) == []


# ---- misc -----------------------------------------------------------------
def test_only_watched_devices_alert(storage, profile):
    storage.flag_device(profile, WATCHED)  # OTHER is never flagged
    t0 = datetime(2026, 9, 28, 10, 0, 0)
    for i, devices in enumerate([[_device(WATCHED), _device(OTHER)], [_device(WATCHED)], [_device(WATCHED)]]):
        storage.save_scan(devices, t0 + timedelta(minutes=5 * i), profile)
    assert storage.get_flag_alerts(profile) == []


def test_custom_name_attached(storage, profile):
    storage.flag_device(profile, WATCHED)
    storage.set_device_name(profile, WATCHED, "Dad's laptop")
    run_scans(storage, profile, [True, False, False])
    assert storage.get_flag_alerts(profile)[0]["custom_name"] == "Dad's laptop"


def test_multiple_watched_devices_independent(storage, profile):
    storage.flag_device(profile, WATCHED)
    storage.flag_device(profile, OTHER)
    t0 = datetime(2026, 9, 28, 10, 0, 0)
    scans = [[_device(WATCHED), _device(OTHER)], [_device(OTHER)], [_device(OTHER)]]
    for i, devices in enumerate(scans):
        storage.save_scan(devices, t0 + timedelta(minutes=5 * i), profile)
    assert events(storage, profile) == [(WATCHED, "disappeared")]


# ---- get_watched_timeline (Watched Devices page) ---------------------------
def test_timeline_empty_when_nothing_watched(storage, profile):
    run_scans(storage, profile, [True, False])
    timeline = storage.get_watched_timeline(profile)
    assert timeline["devices"] == {}


def test_timeline_presence_is_oldest_first_and_aligned(storage, profile):
    storage.flag_device(profile, WATCHED)
    run_scans(storage, profile, [True, False, True])
    timeline = storage.get_watched_timeline(profile)
    assert len(timeline["scans"]) == 3
    times = [s["scan_time"] for s in timeline["scans"]]
    assert times == sorted(times)
    assert timeline["devices"][WATCHED]["presence"] == [True, False, True]


def test_timeline_only_covers_the_latest_scans(storage, profile):
    storage.flag_device(profile, WATCHED)
    run_scans(storage, profile, [True, True, True, False, True])
    timeline = storage.get_watched_timeline(profile, scan_limit=2)
    assert timeline["devices"][WATCHED]["presence"] == [False, True]


def test_timeline_outages_and_longest_gap(storage, profile):
    storage.flag_device(profile, WATCHED)
    run_scans(storage, profile, [True, False, False, True, False, True])
    info = storage.get_watched_timeline(profile)["devices"][WATCHED]
    assert info["outages"] == 2
    assert info["longest_gap"] == 2
    assert info["last_seen"] == storage.get_watched_timeline(profile)["scans"][-1]["scan_time"]


def test_timeline_ongoing_gap_counts(storage, profile):
    storage.flag_device(profile, WATCHED)
    run_scans(storage, profile, [True, False, False, False])
    info = storage.get_watched_timeline(profile)["devices"][WATCHED]
    assert (info["outages"], info["longest_gap"]) == (1, 3)


def test_timeline_scans_before_first_appearance_do_not_count(storage, profile):
    storage.flag_device(profile, WATCHED)
    run_scans(storage, profile, [False, False, True, True])
    info = storage.get_watched_timeline(profile)["devices"][WATCHED]
    assert (info["outages"], info["longest_gap"]) == (0, 0)


def test_timeline_never_seen_device(storage, profile):
    storage.flag_device(profile, WATCHED)
    run_scans(storage, profile, [False, False])
    info = storage.get_watched_timeline(profile)["devices"][WATCHED]
    assert info["presence"] == [False, False]
    assert (info["outages"], info["longest_gap"], info["last_seen"]) == (0, 0, None)


def test_timeline_is_scoped_to_profile(storage, profile):
    other = storage.get_or_create_profile("University")
    storage.flag_device(profile, WATCHED)
    run_scans(storage, profile, [True, True])
    timeline = storage.get_watched_timeline(other)
    assert timeline["scans"] == [] and timeline["devices"] == {}