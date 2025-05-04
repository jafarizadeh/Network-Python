# NetScope - Python Network Packet Sniffer

NetScope is a professional, class-based network packet sniffer built with Python and Scapy.
It captures, analyzes, and logs TCP, UDP, and ICMP packets in real-time, showing detailed information about direction (IN/OUT), IPs, ports, MAC addresses, and more.

---

## 🔍 Features

* ✅ Real-time packet sniffing using Scapy
* ✅ Detects and logs TCP, UDP, and ICMP protocols
* ✅ Shows packet direction (incoming/outgoing)
* ✅ Displays source/destination IP, port, MAC, and size
* ✅ Written with object-oriented Python for extensibility
* ✅ Easily expandable to log to file or filter by port/protocol

---

## 🛠 Requirements

* Python 3.6+
* [Scapy](https://scapy.net/)

Install Scapy via pip:

```bash
pip install scapy
```

---

## 🚀 How to Run

Clone the repository and run the script with administrator/root privileges:

```bash
python network_sniffer.py
```

> ⚠️ On Windows: Open PowerShell as Administrator
> ⚠️ On Linux/macOS: Run with `sudo` if needed

---

## 📄 Sample Output

```
[2025-05-04 13:04:12.027] TCP-OUT: 60 Bytes
SRC-MAC: d8:43:ae:26:33:2a DST-MAC: 6c:61:f4:0a:24:b8
SRC-PORT: 52344 DST-PORT: 443
SRC-IP: 192.168.1.46 DST-IP: 172.217.169.78
```

---

## 📌 Project Structure

```
network_sniffer.py     # Main script containing the PacketSniffer class
README.md              # Project description and usage guide
```

---

## ✨ Future Improvements

* [ ] Log output to a file
* [ ] GUI interface (Tkinter / PyQt)
* [ ] Protocol filtering (e.g., only TCP)
* [ ] Save packet summary as JSON/CSV

---


## 👨‍💻 Author

Developed by \Mehdi JAFARIZADEH – feel free to contribute or raise an issue!
