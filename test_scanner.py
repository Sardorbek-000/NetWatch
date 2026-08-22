#!/usr/bin/env python3

import socket  #tool for working with network
import ipaddress  #tool for working with network
import threading  #multitasking 

from scapy.all import ARP, Ether, srp  #for creating and sending the packets
from mac_vendor_lookup import MacLookup #the names of phones 



# Configuration


SCAN_TIMEOUT = 5  



# Get local IP address 
def get_local_ip():
    #Get the local IPv4 address used for the network connection.    
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            # No real connection is established.
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]

    except OSError:
        return None



# Get local network
def get_local_network(local_ip):

    try:
        network = ipaddress.ip_network(
            f"{local_ip}/24",
            strict=False
        )
        return network

    except ValueError:
        return None



# Get hostname
def get_hostname(ip_address):
    try:
        hostname = socket.gethostbyaddr(ip_address)[0]
        return hostname

    except (socket.herror, socket.gaierror, OSError):
        return "Unknown"


# Get vendor
def get_vendor(mac_address, mac_lookup):
    try:
        return mac_lookup.lookup(mac_address)

    except Exception:
        return "Unknown"


# Scan network
def scan_network(network):
    """
    Send ARP requests to all hosts in the local network.
    """

    print(f"\nScanning network: {network}")
    print("Please wait...\n")

    arp_request = ARP(pdst=str(network))

    ethernet_frame = Ether(
        dst="ff:ff:ff:ff:ff:ff"
    )

    packet = ethernet_frame / arp_request

    try:
        answered, unanswered = srp(
            packet,
            timeout=SCAN_TIMEOUT,
            verbose=False
        )

        devices = []

        for sent_packet, received_packet in answered:
            devices.append({
                "ip": received_packet.psrc,
                "mac": received_packet.hwsrc.upper(),
                "status": "Online"
            })

        return devices

    except PermissionError:
        print("Permission denied.")
        print("Run the program with sudo/or admin rights if terminal.")
        return []

    except OSError as error:
        print(f"Network error: {error}")
        return []

    except Exception as error:
        print(f"Unexpected scanning error: {error}")
        return []




# Process device information
def process_device(device, mac_lookup):
    device["vendor"] = get_vendor(
        device["mac"],
        mac_lookup
    )

    device["hostname"] = get_hostname(
        device["ip"]
    )

    return device


# Multithread device processing
def process_devices(devices):
    """
    Process hostname/vendor lookups using threads.
    """

    mac_lookup = MacLookup()

    results = []
    lock = threading.Lock()

    def worker(device):
        processed = process_device(
            device,
            mac_lookup
        )

        with lock:
            results.append(processed)

    threads = []

    for device in devices:
        thread = threading.Thread(
            target=worker,
            args=(device,)
        )

        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()

    return results



# Display results
def display_devices(devices):
    print("\n" + "=" * 90)
    print("CONNECTED DEVICES")
    print("=" * 90)

    if not devices:
        print("No devices found.")
        return

    # Sort devices by IP address.
    devices.sort(
        key=lambda device: ipaddress.ip_address(device["ip"])
    )

    for device in devices:

        print(
            f"IP: {device['ip']} , "
            f"MAC-Address: {device['mac']} , "
            f"Vendor: {device['vendor']} , "
            f"Status: {device['status']} , "
            f"Hostname: {device['hostname']}"
        )

    print("-" * 90)
    print(f"Total devices found: {len(devices)}")



# Main
def main():

    print("=" * 90)
    print("LOCAL NETWORK SCANNER")
    print("=" * 90)

    local_ip = get_local_ip()

    if not local_ip:
        print("Could not determine local IP address.")
        return

    print(f"Local IP: {local_ip}")

    network = get_local_network(local_ip)

    if not network:
        print("Could not determine local network.")
        return

    devices = scan_network(network)

    if not devices:
        return

    devices = process_devices(devices)

    display_devices(devices)



# Program entry point
if __name__ == "__main__":
    main()
