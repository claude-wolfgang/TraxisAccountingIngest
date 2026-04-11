# Hyundai KF5600ii Fanuc Post Processor v1.1.1
## G-Code and M-Code Reference

This document lists all G and M codes that may be output by the post processor depending on what operations are programmed.

---

## G CODES

### Motion Codes (Modal Group 1)
| Code | Description |
|------|-------------|
| G00 | Rapid positioning |
| G01 | Linear interpolation (feed move) |
| G02 | Circular interpolation CW |
| G02.4 | 3D circular interpolation CW (if enabled) |
| G03 | Circular interpolation CCW |
| G03.4 | 3D circular interpolation CCW (if enabled) |

### Plane Selection (Modal Group 2)
| Code | Description |
|------|-------------|
| G17 | XY plane selection |
| G18 | ZX plane selection |
| G19 | YZ plane selection |

### Canned Cycle Codes (Modal Group 9)
| Code | Cycle Type |
|------|------------|
| G73 | High-speed peck drilling (chip breaking) |
| G74 | Left-hand tapping |
| G76 | Fine boring |
| G80 | Cancel canned cycle |
| G81 | Drilling |
| G82 | Counter boring (with dwell) |
| G83 | Deep hole peck drilling |
| G84 | Right-hand tapping |
| G85 | Reaming |
| G86 | Stop boring |
| G87 | Back boring |
| G88 | Manual boring |
| G89 | Boring with dwell |

### Canned Cycle Return Level (Modal Group 10)
| Code | Description |
|------|-------------|
| G98 | Return to initial point (R level) |
| G99 | Return to R point |

### Distance Mode (Modal Group 3)
| Code | Description |
|------|-------------|
| G90 | Absolute positioning |
| G91 | Incremental positioning |

### Feed Rate Mode (Modal Group 5)
| Code | Description |
|------|-------------|
| G93 | Inverse time feed (for multi-axis) |
| G94 | Feed per minute |
| G95 | Feed per revolution |

### Work Coordinate Systems (Modal Group 12)
| Code | Description |
|------|-------------|
| G54 | Work offset 1 |
| G55 | Work offset 2 |
| G56 | Work offset 3 |
| G57 | Work offset 4 |
| G58 | Work offset 5 |
| G59 | Work offset 6 |
| G54.1 P1-P300 | Extended work offsets |

### Tool Length Compensation (Modal Group 8)
| Code | Description |
|------|-------------|
| G43 | Tool length compensation + |
| G43.4 | Tool center point control (multi-axis TCP) |
| G43.5 | Tool center point control (3-axis TCP) |
| G49 | Cancel tool length compensation |

### Cutter Compensation (Modal Group 7)
| Code | Description |
|------|-------------|
| G40 | Cancel cutter compensation |
| G41 | Cutter compensation left |
| G42 | Cutter compensation right |

### Reference Point Return
| Code | Description |
|------|-------------|
| G28 | Return to reference point (through intermediate) |
| G30 | Return to 2nd reference point |
| G53 | Machine coordinate system (non-modal) |
| G53.1 | Machine coordinate rotation |

### Smoothing / AICC (High-Speed Machining)
| Code | Description |
|------|-------------|
| G05.1 Q0 | Smoothing OFF |
| G05.1 Q1 | Smoothing ON (AICC/AIAPC) |
| G05.1 Q1 R1-R10 | Smoothing ON with level |
| G05.1 Q3 | Nano smoothing mode |

### Dwell
| Code | Description |
|------|-------------|
| G04 | Dwell (P = milliseconds) |

### Coordinate Rotation
| Code | Description |
|------|-------------|
| G68 | Coordinate rotation ON |
| G68.2 | Tilted work plane |
| G69 | Coordinate rotation OFF |

### Workpiece Setting Error Compensation
| Code | Description |
|------|-------------|
| G54.4 P0 | Cancel workpiece error compensation |
| G54.4 P1-P6 | Workpiece error compensation for WCS 1-6 |

---

## M CODES

### Program Control
| Code | Description |
|------|-------------|
| M00 | Program stop |
| M01 | Optional stop |
| M02 | Program end |
| M30 | Program end and rewind |
| M98 | Subprogram call |
| M99 | Subprogram return / end |

### Spindle Control
| Code | Description |
|------|-------------|
| M03 | Spindle on CW |
| M04 | Spindle on CCW |
| M05 | Spindle stop |
| M19 | Spindle orientation |
| M28 | Rigid tap mode cancel (optional) |
| M29 | Rigid tapping mode |

### Tool Change
| Code | Description |
|------|-------------|
| M06 | Tool change |

### Coolant Control
| Code | Description |
|------|-------------|
| M07 | Mist coolant ON (optional) |
| M08 | Flood coolant ON |
| M09 | Coolant OFF |
| M49 | Through-spindle coolant ON |
| M50 | Through-spindle coolant OFF |
| M56 | Air through spindle ON |
| M57 | Air through spindle OFF |

### Chip Conveyor
| Code | Description |
|------|-------------|
| M36 | Screw chip conveyor ON |
| M37 | Screw chip conveyor OFF |

### Axis Clamp (Multi-Axis Machines)
| Code | Description |
|------|-------------|
| M10 | 4th axis clamp (optional) |
| M11 | 4th axis unclamp (optional) |

### Probing Macros (Renishaw)
| Code | Description |
|------|-------------|
| M1165 | Macro call (custom probe macro call) |
| P9810 | Protected positioning move |
| P9811 | Probe single surface (Z) |
| P9812 | Probe web/pocket X |
| P9812 (with S) | Probe web/pocket Y |
| P9814 | Probe boss X |
| P9814 (with S) | Probe boss Y |
| P9817 | Probe internal corner |
| P9818 | Probe external corner |
| P9819 | Probe PCD hole/boss |
| P9832 | Probe on (spin) |
| P9833 | Probe off |
| P9858 | Tool breakage detection |

### Other Machine M-Codes (Reference Only - Not in Post)
| Code | Description |
|------|-------------|
| M13 | Spindle CW + Flood (M03 & M08) |
| M14 | Spindle CCW + Flood (M04 & M08) |
| M15 | Spindle Stop + Coolant Off (M05 & M09) |
| M90 | Auto door open (optional) |
| M91 | Auto door close (optional) |
| M140 | Tool air blow start |
| M141 | Tool air blow stop |
| M1001 | Auto tool breakage detecting macro (optional) |

### Inspection Output
| Code | Description |
|------|-------------|
| POPEN | Open output file |
| PCLOS | Close output file |
| DPRNT[] | Print data to file |

---

## NOTES

### Coolant Combinations
The post supports combining coolant codes:
- **M08 + M07**: Flood + Mist
- **M08 + M49**: Flood + Through-spindle

### Tapping
- Standard tapping uses G84 (right-hand) or G74 (left-hand)
- Rigid tapping outputs M29 before the tapping cycle
- Peck tapping uses Q parameter for incremental peck depth
- M28 cancels rigid tap mode (optional)

### Feed Modes
- G94 (feed/min) is default
- G95 (feed/rev) can be enabled via post property
- G93 (inverse time) is used automatically for multi-axis simultaneous moves

### Smoothing Levels
When using "Level 1-10" smoothing, the R value corresponds to:
- R1 = Tightest tolerance (finest finish)
- R10 = Loosest tolerance (fastest machining)

### Work Coordinates
- Standard: G54-G59 (6 offsets)
- Extended: G54.1 P1 through G54.1 P300

### Machine-Specific Notes
- M14/M15 are combination codes (spindle + coolant) on this machine - not used by post
- M24/M25 are JIG clamp codes on this machine - chip conveyor uses M36/M37
- M132/M133 are ATC maintenance codes - not suction
- Items marked (optional) in M-code list require machine options to be installed

---

*Generated from hyundai_kf5600ii_fanuc_v1_1_2.cps - Updated to match machine manual*
