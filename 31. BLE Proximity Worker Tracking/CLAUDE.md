# P31: BLE Proximity Worker Tracking

Passive BLE-based system to track which worker is at which CNC machine.
Uses Feasycom iBeacon tags (worn by workers) and ESP32 gateways running ESPresense (at machines) to detect proximity via RSSI.

## Hardware
- 2x Feasycom iBeacon tags — on hand, TX power 2.5dB, interval 1000ms
  Each tag broadcasts multiple iBeacon slots simultaneously with different major numbers:
  - Tag-A: MAC DC:0D:30:1F:90:A3, majors 39475, 40604, 10065 (shared)
  - Tag-B: MAC DC:0D:30:48:30:3A, majors 35540, 60285, 10065 (shared)
  - Major 10065 is broadcast by BOTH tags — disambiguate via MAC address
- Asus USB Bluetooth dongle — retired, inadequate (~4 dB RSSI spread)
- 3x ESP32-WROOM-32 dev boards — ESPresense v4.0.6, CP2102 USB-serial
  - M8: IP 10.1.1.38, MAC 70:4B:CA:6D:B7:48, room=m8 — online
  - M1: IP 10.1.1.225, MAC 30:76:F5:E8:D1:FC, room=m1 — online
  - M2: IP 10.1.1.23, MAC 30:76:F5:E8:BE:74, room=m2 — online
- 10x MOKOSmart B2 Smart Badges — ordered 2026-04-29 (Order #3765, $171.48 shipped), BLE iBeacon + NFC for door entry

## Key Technical Notes
- Beacon MACs rotate randomly — must identify by iBeacon major/minor, not MAC. Exception: major 10065 requires MAC disambiguation since both tags share it
- ESP32 gateways self-detect each other as iBeacon majors 72, 116, 252 — filter these out
- ESPresense firmware (https://espresense.com/) provides Kalman-filtered RSSI + MQTT output
- Zone thresholds (walk test 2026-04-29, open air):
  - AT MACHINE >-45 dBm (~0-2ft, operator at controls)
  - NEARBY >-58 dBm (~3ft, stepping back)
  - IN AREA >-66 dBm (~6-10ft, adjacent machine)
  - FAR/GONE <-66 dBm (>10ft)
- USB dongle was useless (~4dB spread); ESP32 gateway gives ~50dB dynamic range (0-15ft)
- Feasycom tags configurable via phone app (TX power, advertising interval)
- Label physical tags with their major numbers for identification

## Gateway Configuration
ESPresense settings are stored in SPIFFS. Configuration via HTTP `/wifi` endpoint (GET to
read, POST to write). POST must include ALL parameters or omitted ones get cleared (including
WiFi credentials). The `/wifi` GET response masks the password as `***###***`.

MQTT broker: **10.1.1.178:1883** (Mosquitto on this PC). The previous "broker is on 10.1.1.108"
note was always wrong — that IP is unrelated. All 3 gateways re-pointed to .178 on 2026-05-23
via `/wifi` POST. Mosquitto runs as a user process (`mosquitto.exe -c mosquitto_clean.conf`);
service-mode start needs admin. **Promote to a Windows service** so it survives reboot — see
Next Steps. Long-term home is srv-01 (10.1.1.161) once the SSH regression is fixed.

## B2 Badge Configuration

The B2 is part of MOKO's **MK BUTTON** product line (hardware `MKBN Series`, firmware `V2.0.3`,
software `BXP-B-D`), not the older H3-style BeaconX Pro Nordic line that the spec PDF
suggests. Configuration app is **BeaconX Pro** (iOS + Android) — *not* MokoBeaconX, which is
for a different beacon family. In BeaconX Pro's startup picker, choose **MK BUTTON**.

Connect password: `Moko4321` (factory default; not yet rotated — see Next Steps).

Per-badge UI is organized by alarm-trigger slot (Single press / Double press / Long press /
Abnormal inactivity), each with a Frame Type selector (`Alarm info` MOKO-proprietary,
`UID` Eddystone, or `iBeacon`). The B2 ships with iBeacon UUID/Major/Minor **blank** — we
assign per-badge.

### Traxis B2 batch identity

All 10 badges share one UUID; Major identifies the cohort; Minor is per-badge sequential.

- **iBeacon UUID:** `23FD6BBB-8A96-4C0E-8AB4-0158E9A3D1EF` (hex-only for the app's `0x` field:
  `23FD6BBB8A964C0E8AB40158E9A3D1EF`). Generated 2026-05-23; gateway code should filter on
  this UUID to ignore non-Traxis beacons.
- **Major:** `1` — differentiates from Feasycom (10065/35540/39475/40604/60285) and ESP32
  self-discovery (72/116/252).
- **Minor:** `1` through `10` matching the physical `B2-NN` Sharpie label.

We configure the Single Press slot as iBeacon since it's ON by default. Other 3 slots stay at
factory defaults — they remain available for SOS button programming later.

Per-badge cataloging tracked in `badge_inventory.md`.

## Status
3 ESP32 gateways online + publishing to broker on `10.1.1.178:1883` (2026-05-23). 10 MOKOSmart
B2 badges in hand; 1/10 (B2-01, MAC `F7:4E:DB:34:D8:E4`) configured with iBeacon, **save not
yet verified end-to-end** — walk test returned zero hits, likely because the BeaconX Pro
connection was still active during the walk and BLE peripherals suppress advertisements while
connected. Next session: disconnect from BeaconX Pro fully (or close app / cycle Bluetooth),
re-walk, then proceed with B2-02..B2-10 if confirmed working.

Walk test (2026-04-30): M2→M1→M8 path, 30s at each machine. Feasycom tags at 2.5dB TX power
show only 3-5 dB RSSI contrast between adjacent gateways (~6ft apart) — everything reads FAR.
Expect MOKOSmart B2 badges to provide better signal for zone detection (untested as of
2026-05-23 close).

`proximity_logger.py` runs as background service via `start_logger.bat`, logging to `proximity.db`.

## Next Steps

1. **[NEEDS WOLFGANG] Verify B2-01 iBeacon broadcast end-to-end before scaling.** Disconnect from BeaconX Pro (back arrow, close app, or toggle Bluetooth), then run `python b2_watch.py 1` and confirm the badge appears across one or more gateways. If still nothing, reconnect to B2-01 and confirm Single Press slot still shows Frame=iBeacon and UUID/Major/Minor=`23FD6BBB...` / `1` / `1` (the save may not have persisted).
2. Configure B2-02 through B2-10 once #1 is verified. Same workflow per `badge_inventory.md`: long-press wake → connect → ALARM tab → Single press mode → Frame=iBeacon → UUID `23FD6BBB8A964C0E8AB40158E9A3D1EF` / Major `1` / Minor `N` → save → **disconnect** → power off → label `B2-NN`.
3. Re-walk with all 10 badges and capture the RSSI dynamic range across M1/M2/M8 — that's the apples-to-apples comparison vs the open-air Feasycom 3-5 dB result that drove the badge purchase.
4. **Mosquitto on .178 should be a Windows service**, not a user process. Currently dies on reboot. Either `Start-Service mosquitto` from an admin PowerShell (the service is installed but Stopped/Automatic), or migrate to srv-01 once SSH there is recovered.
5. **Tamper-defense provisioning per badge.** Sacrifice one badge to document the factory-reset button gesture (the H3 spec mentions >10s long-press resets but it's untested on the MK BUTTON line). Change all 10 passwords from `Moko4321` to a per-batch password (BeaconX Pro → SETTING tab has the password field). Confirm whether the SETTING tab exposes a button-disable / button-lock toggle to prevent operators from triggering SOS alarms accidentally.
6. **Re-test zone thresholds** in `CLAUDE.md`'s "Zone thresholds" block with steel machine backdrop — current thresholds are open-air from the Feasycom era and may need adjustment for the B2's different antenna/TX-power profile.
7. **Build assignment engine** (strongest-gateway-wins per worker minor → machine) + server-side anomaly detection (impossible majors, off-hours appearances, MAC inconsistency) as tamper backstop.
8. **Revisit accelerometer config** once the basic proximity loop works. The MK BUTTON ALARM tab exposes "Abnormal inactivity mode" (built-in dead-man check) and the SETTING tab has 3-axis accelerometer params. Potential uses: worn-vs-locker detection, wake-on-motion adv-rate boost (battery savings), tamper signal (accelerometer activity inconsistent with worker history).
9. **MOKOSmart support email reply** — sent to `lora@mokosmart.com` 2026-05-23 (wrong inbox; LoRa team, not BLE). They may forward, or not. If we need an authoritative answer on any remaining MK BUTTON question, the correct address is `Support_BLE@mokotechnology.com` (per H3 user manual page 6).

## Interfaces
Produces: `proximity.db` (SQLite, readings table), worker-machine proximity events via MQTT, Outlook drafts in `tom@traxismfg.com / Purchasing - To Review` (via `draft_mokosmart_email.py` reusing P31 Photo Upload Service's `email_draft.create_draft`)
Consumes: ESPresense MQTT topics `espresense/devices/#` and `espresense/rooms/+/#` on broker `10.1.1.178:1883`, ProShop employee list (planned, not yet integrated), machine inventory, P31 Photo Upload Service's `purchasing/email_draft.py` (Graph API helper, requires `tom@`'s Graph creds in `.traxis.env`)
Contracts: **MQTT broker must run on 10.1.1.178:1883.** All 3 ESP32 gateways (m1/.225, m2/.23, m8/.38) are SPIFFS-configured to publish there as of 2026-05-23 — moving the broker without re-POSTing each gateway's `/wifi` endpoint silently breaks the whole pipeline. POST must include all params (WiFi credentials get cleared otherwise) so the Traxis-MFG WiFi password is part of the contract. **Traxis B2 batch UUID is `23FD6BBB-8A96-4C0E-8AB4-0158E9A3D1EF`** — gateway-side filters and downstream identity mappings depend on this constant. Mosquitto config: `mosquitto_clean.conf` (listener 1883 + allow_anonymous true).
