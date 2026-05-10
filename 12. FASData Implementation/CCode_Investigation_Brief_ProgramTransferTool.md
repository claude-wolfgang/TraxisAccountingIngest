# Investigation Brief — Traxis MFG CNC Program Transfer Tool
## Instructions for Claude Code

You are helping design a **new CNC program transfer tool** for Traxis Manufacturing. This tool will replace/complement the Fanuc Program Transfer Tool currently in use, and will support multiple machine types and connection methods from a single interface.

Your job is to **investigate, research, and produce a complete feature specification** before any code is written. Do not write the application yet — produce a thorough requirements and design document.

---

## Background

Traxis Manufacturing has approximately 8 CNC machines. Each workstation computer needs a **simple, local UI** to transfer NC programs to the machine physically nearest to it. Operators are not technical — the UI must be extremely simple.

### Current State
- **Fanuc machines:** Currently use Fanuc Program Transfer Tool (PTT) for file transfer over Ethernet
- **Haas VF-5/40 (2014, Classic Haas Control M18.22B):** Now connected via Raspberry Pi Zero 2 WH at `10.1.1.149`, which emulates a USB flash drive over a USB OTG cable. Program transfer uses SSH + SCP from the workstation PC.
- **Future Haas NGC machines:** Will connect via direct Ethernet (SMB/Q-code)

### The Pi Zero Transfer Mechanism (Haas CHC)
The Pi Zero acts as a virtual USB drive. Transfer requires three steps:
1. `ssh haasmill1@10.1.1.149 "/home/haasmill1/pre-copy.sh"` — disconnects drive from Haas, mounts for transfer
2. `scp "file.nc" haasmill1@10.1.1.149:/mnt/usb_share/` — copies file to virtual drive
3. `ssh haasmill1@10.1.1.149 "/home/haasmill1/post-copy.sh"` — remounts drive to Haas

This should be **completely transparent to the operator** — they should just pick a file and click Send.

---

## Investigation Tasks

### Task 1 — Investigate the FASData Folder Structure
Look at the folder: `D:\Users\MainPC\Documents\` and related directories on this machine.

Specifically find and document:
- Where NC program files are stored (file paths, naming conventions)
- How programs are organized (by machine? by job? by customer? by operation?)
- What file extensions are used (.nc, .txt, .tap, .cnc, other?)
- Whether there are any existing naming conventions or job numbering systems
- The `NC Files For Transfer` folder — what's in it, how is it used, is it manually maintained?
- Any existing folder called FASData or similar — what does it contain?
- Are there any existing databases, spreadsheets, or logs tracking program versions or machine assignments?
- How programs currently get from the CAM system to the transfer folder

Document everything you find. This tells us what the tool needs to integrate with.

### Task 2 — Investigate Fanuc Program Transfer Tool
Research how the Fanuc Program Transfer Tool works:
- What protocol does it use to talk to Fanuc CNCs? (FOCAS? FTP? Both?)
- What is the FOCAS library — is there a Python or Node.js wrapper available?
- What does the UI look like — what workflow does an operator follow?
- What are its limitations (file naming, program number format, etc.)?
- Is the Fanuc PTT licensed per machine or per PC?
- Can it be scripted or called from another application?
- Are there open source alternatives that speak FOCAS?

Check:
- fanucamerica.com
- GitHub for "focas python" or "fanuc focas"
- Any Python library called `pyfocas` or `focas2`

Document the communication protocol details thoroughly — we need to replicate or wrap this functionality.

### Task 3 — Research Connection Methods for All Machine Types

For each machine type below, document the exact connection method, protocol, required credentials, and any Python/Node libraries available:

| Machine Type | Connection | Notes |
|---|---|---|
| Fanuc CNC (various) | Ethernet FOCAS/FTP | Current method via PTT |
| Haas CHC (2014 VF-5/40) | Pi Zero SSH+SCP | Already working |
| Haas NGC (2016+) | Ethernet SMB | Direct network share |
| Generic RS-232 | Serial via USB adapter | Fallback for older machines |

For each, find:
- Python libraries available
- Authentication requirements
- File format requirements (does the machine need a specific file format/header?)
- Transfer speed limitations
- Known gotchas

### Task 4 — Define the Machine List for Traxis
Based on what you find in the file system, shop documentation, or any existing machine lists, try to identify:
- How many machines are currently networked
- What control types they have (Fanuc model, Haas CHC vs NGC, other)
- Their IP addresses if findable
- Which machines each workstation PC is near/assigned to

If you can't determine this from files, flag it as information that needs to be gathered from the shop floor.

### Task 5 — Research Best Practices for Shop Floor DNC Software UI
Research what makes a good shop floor program transfer UI:
- What do operators actually need vs what programmers need?
- What are the most common operator errors in program transfer?
- What safety features are most important (overwrite protection, version confirmation, etc.)?
- Look at CIMCO Edit/DNC, Predator DNC, and any other modern DNC tools for UI inspiration
- What screen size / input method is typical at a machine workstation?

---

## Feature Requirements to Evaluate

For each feature below, determine: **Must Have / Nice to Have / Not Needed** based on your research into the shop environment and operator needs.

### Core Transfer Features
- [ ] Send NC file from PC to machine (upload)
- [ ] Receive NC file from machine to PC (download/backup)
- [ ] Browse programs currently stored on machine
- [ ] Delete program from machine
- [ ] Rename program on machine
- [ ] Overwrite confirmation prompt
- [ ] Transfer progress indicator
- [ ] Success/failure feedback

### Machine Management
- [ ] Machine list showing online/offline status
- [ ] Per-workstation configuration (this PC → this machine only)
- [ ] Multi-machine support from one interface
- [ ] Machine nickname / friendly name display
- [ ] Connection health monitoring

### File Management
- [ ] Integration with NC Files For Transfer folder
- [ ] Auto-detect new files in a watched folder
- [ ] Program search by name or content
- [ ] Recent files list
- [ ] Favorites / pinned programs

### Safety & Audit
- [ ] Version history (which file went to which machine when)
- [ ] Operator login / who sent what
- [ ] Backup before overwrite
- [ ] Read-only mode (browse without transfer ability)
- [ ] Confirmation of program number before send

### Advanced
- [ ] Drip feed / DNC mode (run program directly from PC without loading to memory)
- [ ] Tool offset transfer
- [ ] Work offset transfer
- [ ] Machine parameter backup
- [ ] Remote program edit

---

## Output Required

Produce a document called `Program_Transfer_Tool_Spec.md` containing:

1. **Executive Summary** — what we're building and why
2. **Shop Environment Summary** — what you found in the file system and about current workflows
3. **Machine Inventory** — all machines, their controls, IPs, and connection methods
4. **Connection Protocol Details** — exactly how to talk to each machine type
5. **Feature List with Priority** — Must/Nice/No for each feature above
6. **Recommended UI Design** — describe the operator-facing interface (screens, workflow, key interactions)
7. **Recommended Technology Stack** — Python? Electron? Web app? Desktop app? Justify your choice.
8. **Open Questions** — things that need human input before building starts
9. **Risk List** — what could go wrong, what needs testing first

---

## Known Constraints

- Must run on **Windows 10/11** workstation PCs
- Must be usable by **non-technical operators** — minimal training
- **Per-workstation config** — each install points to only one machine
- Must handle the **Pi Zero SSH/SCP** path transparently for the Haas CHC
- Should be **installable without admin rights** if possible
- No cloud dependency — everything stays on the local `10.1.1.x` network
- **No budget defined yet** — open source preferred but commercial libraries acceptable if justified

---

## References

- Haas VF-5/40 Pi Zero setup: see `Haas_VF5_40_Comms_Masterplan.md`
- Pi Zero credentials: `haasmill1@10.1.1.149`
- Pi Zero transfer scripts: `/home/haasmill1/pre-copy.sh`, `/home/haasmill1/post-copy.sh`
- Haas machine IP: `10.1.1.220`
- Shop network: `10.1.1.x` subnet

---

*This brief was prepared 2026-03-18 for Traxis Manufacturing CNC communications project.*
*Do not begin coding until the specification document is complete and reviewed.*
