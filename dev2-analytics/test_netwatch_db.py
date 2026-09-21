import netwatch_db as db

db.create_tables(db.connection)

first_scan_id = db.save_scan(db.connection, "2023-10-01 12:00:00", "192.168.1.0/24")
db.save_scan_results(db.connection, first_scan_id, [
    {"ip": "192.168.1.2", "mac": "00:11:22:33:44:55", "vendor": "VendorA", "status": "active", "hostname": "Ethan-PC"},
    {"ip": "192.168.1.3", "mac": "00:11:22:33:44:56", "vendor": "VendorB", "status": "inactive", "hostname": "apple macbook"},
    {"ip": "192.168.1.4", "mac": "00:11:22:33:44:57", "vendor": "VendorC", "status": "active", "hostname": "Oled4k TV"},
])


second_scan_id = db.save_scan(db.connection, "2023-10-02 12:00:00", "192.168.1.0/24")
db.save_scan_results(db.connection, second_scan_id, [
    {"ip": "192.168.1.22", "mac": "00:11:22:33:44:55", "vendor": "VendorA", "status": "active", "hostname": "Ethan-phone"},
    {"ip": "192.168.1.23", "mac": "00:11:22:33:44:56", "vendor": "VendorB", "status": "inactive", "hostname": "apple watch"},
    {"ip": "192.168.1.24", "mac": "00:11:22:33:44:57", "vendor": "VendorC", "status": "active", "hostname": "acer laptop"},
])

third_scan_id = db.save_scan(db.connection, "2023-10-03 12:00:00", "192 .168.1.0/24")
db.save_scan_results(db.connection, third_scan_id, [
    {"ip": "192.168.1.30", "mac": "AA:BB:CC:DD:EE:05", "vendor": "Apple", "status": "online", "hostname": "ethans-macbook"},
])

print("\nDevices from Oct 1 - Oct 1 (should be scan1 only, 3 devices):")
print(db.get_devices_by_date(db.connection, "2023-10-01 00:00:00", "2023-10-01 23:59:59"))

print("\nDevices from Oct 2 - Oct 2 (should be scan2 only, 3 devices):")
print(db.get_devices_by_date(db.connection, "2023-10-02 00:00:00", "2023-10-02 23:59:59"))

print("\nDevices from Oct 3 - Oct 3 (should be scan3 only, 1 device):")
print(db.get_devices_by_date(db.connection, "2023-10-03 00:00:00", "2023-10-03 23:59:59"))

print("\nDevices from Oct 1 - Oct 3 (should be all 7 devices):")
print(db.get_devices_by_date(db.connection, "2023-10-01 00:00:00", "2023-10-03 23:59:59"))