# Collector PC (10.1.1.71) — Network Troubleshooting

## 2026-04-26: The Cable Incident

### Symptom
Port 8060 (Overseer dashboard) not reachable from other LAN machines after a reboot.

### Wrong Assumption
Firewall / GPO was blocking traffic. Spent time on firewall rules and GPO workarounds.

### Actual Root Cause
**The ethernet cable was bumped loose.** The PC had no wired network connection at all — `ipconfig` showed every adapter as "Media disconnected" except VirtualBox.

### Secondary Issue
Once the cable was reconnected, DHCP assigned **10.1.1.72** instead of .71 because the lease expired while unplugged. Fixed by setting a **static IP**.

### Fix Applied
1. Reseated ethernet cable
2. Set static IP via command line (Windows Settings UI failed silently):
   ```
   netsh interface ip set address "Ethernet 2" static 10.1.1.71 255.255.255.0 10.1.1.1
   netsh interface ip set dns "Ethernet 2" static 9.9.9.9
   ```

### Lessons
- **Always check physical first** — run `ping` before touching firewall rules
- **DHCP on a server is a liability** — static IP prevents address drift after outages
- **Windows Settings UI** for static IP can fail silently — use `netsh` from admin cmd
- The firewall bat file (`open_traxis_firewall.bat`) and scheduled task are still useful for when the firewall IS the issue, but check connectivity first

## Firewall Setup (for reference)

The bat file `open_traxis_firewall.bat` opens ports 5000-8101 TCP and ICMP for the LAN subnet (10.1.1.0/24) and creates a scheduled task to re-apply after GPO refresh. Run as admin when needed.

## Static IP Config
| Field | Value |
|-------|-------|
| IP | 10.1.1.71 |
| Subnet | 255.255.255.0 |
| Gateway | 10.1.1.1 |
| DNS | 9.9.9.9 |
| Adapter | Ethernet 2 (Intel I219-V) |
