# Bug Fix: Chip Conveyor M36 Interfering with Probing Cycles

**Date:** 2026-04-02
**Post:** `hyundai_kf5600ii_fanuc_v1_1_5.cps` (Test Posts version)
**Severity:** Machine freeze during probing

---

## Problem

Probing operations would freeze approximately 2 inches above the part surface. The probe would move toward the part, reach the approach height, and then the machine would hang.

## Root Cause

The post processor outputs `M36` (chip conveyor start) at the beginning of every operation section — including probing cycles. The M36 was being issued immediately before the probe protected positioning macro (`M1165 P9810`), interfering with the probing cycle execution.

The broken NC output looked like:
```
G54
M36              <-- conveyor ON, disrupts probing cycle
G00 X2.0071 Y-1.9728
G43 Z2.2 H30     <-- machine freezes here, +2" above part
M1165 P9832       <-- probe ON never executes properly
M1165 P9810 Z0.2 F15.
M1165 P9811 Z0. Q0.4 M0.08 S1.
```

The working file (10876P2) did not exhibit this because its `conveyorEnable` post property was set differently, so M36 was never output.

## Investigation

Compared two Fusion 360 programs (`.f3z` archives) that shared the same post processor and machine:
- **Working:** `10876P2 BASEPLATE, PENETRATOR, CONNECTORIZED` — probe cycle for XY circular hole (P9814), no M36 in output
- **Broken:** `10019 and 10097` — probe Z surface cycles (P9811), M36 output before every section including probes

Extracted and diffed the CAM document XML (`theIronDoc.irondoc`) and the posted NC files. The M36 before each probe section was the only functional difference that could cause a freeze.

## Fix

**File:** `CAMPosts/Test Posts/hyundai_kf5600ii_fanuc_v1_1_5.cps`
**Line:** ~989 (in `onSection` function)

Added `!isProbeOperation()` check to the conveyor startup logic:

```javascript
// BEFORE (broken):
if (getProperty("conveyorEnable") && !getProperty("conveyorCycleEnable")) {
    onCommand(COMMAND_START_CHIP_TRANSPORT);
}

// AFTER (fixed):
if (getProperty("conveyorEnable") && !getProperty("conveyorCycleEnable") && !isProbeOperation()) {
    onCommand(COMMAND_START_CHIP_TRANSPORT);
}
```

This suppresses M36 output during any probing operation while leaving conveyor behavior unchanged for all other machining operations.

## Action Items

- [x] Fix applied to `Test Posts/hyundai_kf5600ii_fanuc_v1_1_5.cps`
- [x] Test Posts version (with Traxis header, tool ID, and probe fix) copied over main `CAMPosts/hyundai_kf5600ii_fanuc_v1_1_5.cps` — both copies now identical
- [ ] Repost `10019 and 10097 100M` and verify probe cycles run cleanly
- [ ] Consider whether conveyor cycling (`conveyorCycleEnable`) path also needs a probe guard (lines 1025-1026, 3207, 3232, 3348)
