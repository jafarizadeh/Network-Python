from scapy.all import sniff, TCP, UDP, ICMP, IP, IPv6
import socket
import datetime

class PacketSniffer:
    def __init__(self):
        self.local_ip = self._get_local_ip()

    def _get_local_ip(self):
        # Retrieve the local IP address of the machine.
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(('8.8.8.8', 80))
            return s.getsockname()[0]

    def _get_direction(self, pkt, ip_layer):
        # Determine whether the packet is incoming or outgoing.
        try:
            if pkt[ip_layer].dst == self.local_ip:
                return "IN"
            return "OUT"
        except IndexError:
            return "UNKNOWN"

    def _format_log(self, timestamp, proto, direction, pkt, ip_layer):
        # Generate a formatted string for logging packet details.
        return (
            f'[{timestamp}] {proto.__name__}-{direction}: {len(pkt[proto])} Bytes '
            f'SRC-MAC: {pkt.src} DST-MAC: {pkt.dst} '
            f'SRC-PORT: {pkt.sport} DST-PORT: {pkt.dport} '
            f'SRC-IP: {pkt[ip_layer].src} DST-IP: {pkt[ip_layer].dst}'
        )

    def _log_icmp(self, timestamp, direction, pkt):
        return (
            f"[{timestamp}] ICMP-{direction}: {len(pkt[ICMP])} Bytes "
            f"IP-Version: {pkt[IP].version} "
            f"SRC-MAC: {pkt.src} DST-MAC: {pkt.dst} "
            f"SRC-IP: {pkt[IP].src} DST-IP: {pkt[IP].dst}"
        )

    def process_packet(self, pkt):
        timestamp = datetime.datetime.now()

        if pkt.haslayer(TCP):
            ip_layer = IP if pkt.haslayer(IP) else IPv6 if pkt.haslayer(IPv6) else None
            if not ip_layer:
                return
            direction = self._get_direction(pkt, ip_layer)
            print(self._format_log(timestamp, TCP, direction, pkt, ip_layer))

        elif pkt.haslayer(UDP) and pkt.haslayer(IP):
            direction = self._get_direction(pkt, IP)
            print(self._format_log(timestamp, UDP, direction, pkt, IP))

        elif pkt.haslayer(ICMP) and pkt.haslayer(IP):
            direction = self._get_direction(pkt, IP)
            print(self._log_icmp(timestamp, direction, pkt))

    def start(self):
        print(f'[INFO] Network monitoring started on local IP: {self.local_ip}')
        sniff(prn=self.process_packet)


if __name__ == '__main__':
    sniffer = PacketSniffer()
    sniffer.start()
