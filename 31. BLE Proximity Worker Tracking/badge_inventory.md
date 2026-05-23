# B2 Badge Inventory

10x MOKOSmart B2 Smart Badge — Order #3765, received 2026-04-29.
Cataloged via **BeaconX Pro** app on Wolfgang's phone, 2026-05-23.

> **App:** Install **BeaconX Pro** (iOS App Store / Google Play). Do NOT use MokoBeaconX —
> that's a different beacon line and Connect will fail.
> **Firmware family pick at startup: `MK BUTTON`** (the B2 is a 2024 release in MOKO's MK
> Button product line, not the older H3-style BeaconX Pro Nordic line). Hardware version
> reports as `MKBN Series`, Software `BXP-B-D`, Firmware `V2.0.3`.

## Known factory defaults (observed from real badge B2-01, MAC F7:4E:DB:34:D8:E4)
- Connection password: `Moko4321` (1-16 chars, configurable)
- Connection mode: Connectable (no special trigger needed)
- App tabs: ALARM / SETTING / DEVICE
- Four configurable advertising slots (one per alarm mode): Single press / Double press / Long press / Abnormal inactivity
- **Only "Single press mode" slot is ON by default.** Other 3 slots OFF.
- Default frame type on the active slot: `Alarm info` (MOKO proprietary). Options: `Alarm info`, `UID` (Eddystone), `iBeacon`.
- **iBeacon UUID / Major / Minor all BLANK by factory default** — we assign per badge.
- Adv interval: 50 × 20ms = 1000 ms
- Ranging data (calibrated 1m RSSI): 0 dBm
- TX power: 0 dBm (9 grades available: -40, -20, -16, -12, -8, -4, 0, +3, +4 dBm)
- Alarm mode (per slot): OFF by default — button press does not trigger a special payload.
- Effective click interval (window for distinguishing single/double/triple click): 6 × 100ms = 600 ms
- Accelerometer: STMicro LIS3DH (configurable ±2/±4/±8/±16g, 1-100Hz sample rate)

## Traxis B2 batch identity scheme

All 10 badges share one UUID. Major identifies the cohort. Minor is per-badge sequential.

- **iBeacon UUID** (all 10): `23FD6BBB-8A96-4C0E-8AB4-0158E9A3D1EF`
  - Hex-only form for MOKO app's `0x [16bytes]` field: `23FD6BBB8A964C0E8AB40158E9A3D1EF`
  - Generated 2026-05-23; chosen because it is unique to Traxis (ESP32 gateways can filter on this UUID to ignore non-Traxis beacons in the building)
- **Major** (all 10): `1`
  - Differentiates from Feasycom tags (existing majors: 10065, 35540, 39475, 40604, 60285)
  - And from ESP32 self-discovery (majors 72, 116, 252) — see project CLAUDE.md
- **Minor**: sequential `1` through `10` matching the physical `B2-NN` label

We configure the **Single press mode slot** as iBeacon (since it's already the active slot by default). Other 3 slots stay at factory defaults (off / Alarm info) — they remain available for SOS button programming later.

## Procedure
1. Long-press badge button ~3 sec → red LED flashes 3 sec → badge is ON and advertising.
2. Open BeaconX Pro on phone → device appears in scan list as `BeaconX Pro` (closest = strongest RSSI).
3. Tap the entry → enter password `Moko4321` → connect.
4. Read advertised + connected fields and fill the row below.
5. Write physical label on badge: `B2-{slot#}` (Sharpie or label maker).
6. Power off (long-press 3s when on → red LED solid 3s), move to next.

## Inventory

| Slot | Phys Label | MAC | Product | SW/FW/HW | Mfg Date | iBeacon UUID | Major | Minor | TX Power | Adv Interval | Battery | Single-Press Alarm | Password Changed? | Assigned Worker | Notes |
|-----:|:-----------|:----|:--------|:---------|:---------|:-------------|------:|------:|---------:|-------------:|--------:|:-------------------|:------------------|:----------------|:------|
| 1    | B2-01      | F7:4E:DB:34:D8:E4 | BUTTON | BXP-B-D / V2.0.3 / MKBN | 2024.12.01 | 23FD6BBB8A964C0E8AB40158E9A3D1EF | 1 | 1 | 0 dBm | 1000 ms | 98% (3162mV) | ON (default) | no                |                 |       |
| 2    | B2-02      |     |             |              |       |       |                   |              |        |         |          |     |             | no                |                 |       |
| 3    | B2-03      |     |             |              |       |       |                   |              |        |         |          |     |             | no                |                 |       |
| 4    | B2-04      |     |             |              |       |       |                   |              |        |         |          |     |             | no                |                 |       |
| 5    | B2-05      |     |             |              |       |       |                   |              |        |         |          |     |             | no                |                 |       |
| 6    | B2-06      |     |             |              |       |       |                   |              |        |         |          |     |             | no                |                 |       |
| 7    | B2-07      |     |             |              |       |       |                   |              |        |         |          |     |             | no                |                 |       |
| 8    | B2-08      |     |             |              |       |       |                   |              |        |         |          |     |             | no                |                 |       |
| 9    | B2-09      |     |             |              |       |       |                   |              |        |         |          |     |             | no                |                 |       |
| 10   | B2-10      |     |             |              |       |       |                   |              |        |         |          |     |             | no                |                 |       |

## What to watch for across the batch
- **UUID/major/minor uniformity** — are all 10 factory-defaulted to the same UUID+major, distinguished only by minor? Or is each fully unique? Determines whether we need to overwrite anything.
- **MAC pattern** — should all be in MOKOSmart's OUI range. Note if any look anomalous.
- **TX power variation** — if calibrated 1m RSSI varies more than ~3 dB across identical hardware, flag the outliers (may need recalibration later).
- **NFC enabled by default** — Y/N matters for the tamper plan (lock payload read-only if used).
- **Firmware versions** — if mixed firmware in the batch, note it; some features may differ.

## After cataloging — provisioning checklist
- [ ] Sacrifice one badge to document factory-reset button combo
- [ ] Change all 10 passwords from `Moko4321` to batch password (or per-badge)
- [ ] Enable button-lock / button-disable if app exposes it
- [ ] If using NFC: write per-badge payload, then lock read-only
- [ ] Decide assignment-to-worker policy (sticky vs check-out-each-shift)
- [ ] Pick zone for re-walk test (M1, M2, or M8 — pick one with steel backdrop)
