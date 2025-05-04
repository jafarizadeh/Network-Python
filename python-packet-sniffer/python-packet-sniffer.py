from scapy.all import *
import socket
import datetime

def get_local_ip():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]

local_ip = get_local_ip()

def network_monitoring(pkt):
    timestamp = datetime.datetime.now()

    if pkt.haslayer(TCP):
        if pkt.haslayer(IP):
            ip_layer = IP
        elif pkt.haslayer(IPv6):
            ip_layer = IPv6
        else:
            return

        direction = 'IN' if pkt[ip_layer].dst == local_ip else "OUT"
        print(f'[{timestamp}] TCP-{direction}: {len(pkt[TCP])} Bytes '
              f'SRC-MAC: {pkt.src} DST-MAC: {pkt.dst} '
              f'SRC-PORT: {pkt.sport} DST-PORT: {pkt.dport} '
              f'SRC-IP: {pkt[ip_layer].src} DST-IP: {pkt[ip_layer].dst}')

    elif pkt.haslayer(UDP) and pkt.haslayer(IP):
        direction = "IN" if pkt[IP].dst == local_ip else "OUT"
        print(f'[{timestamp}] UDP-{direction}: {len(pkt[UDP])} Bytes '
              f'SRC-MAC: {pkt.src} DST-MAC: {pkt.dst} '
              f'SRC-PORT: {pkt.sport} DST-PORT: {pkt.dport} '
              f'SRC-IP: {pkt[IP].src} DST-IP: {pkt[IP].dst}')

    elif pkt.haslayer(ICMP) and pkt.haslayer(IP):
        direction = "IN" if pkt[IP].dst == local_ip else "OUT"
        print(f"[{timestamp}] ICMP-{direction}: {len(pkt[ICMP])} Bytes "
              f"IP-Version: {pkt[IP].version} "
              f"SRC-MAC: {pkt.src} DST-MAC: {pkt.dst} "
              f"SRC-IP: {pkt[IP].src} DST-IP: {pkt[IP].dst}")

if __name__ == '__main__':
    print(f"Starting network monitoring on local IP: {local_ip}")
    sniff(prn=network_monitoring)
