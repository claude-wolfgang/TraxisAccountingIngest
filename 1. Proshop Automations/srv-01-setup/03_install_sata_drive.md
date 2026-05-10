# srv-01 — Install 2TB SATA SSD (Crucial BX500)

Windows can't see the drive. Either the cable isn't fully seated or BIOS
doesn't have it enabled. Walkthrough below.

---

## A. Physical check (OptiPlex 7060 Micro)

1. Shut down Windows. Unplug power cord.
2. Loosen the **single thumbscrew at the rear** of the chassis. Slide the
   cover toward the back, lift off.
3. The 2.5" drive bay is a black plastic cage mounted **above the
   motherboard**, held by one screw on a blue/black captive tab.
4. Lift the cage out. The drive should be in it, held by 4 rubber-shoulder
   screws on the sides.
5. Find the SATA combo cable (flat ribbon-style) — has both data and power
   in one connector at the drive end. Two things to verify:
   - **Drive end**: L-shaped connector firmly seated on the SSD.
   - **Motherboard end**: this is the one most often loose. Trace the cable
     back to the board and press firmly on the SATA header. Listen for a
     click.
6. If unsure, **reseat both ends**: pull off, push back on. Connectors are
   keyed — only fit one way.
7. Drop the cage back in, screw down, close the cover.

Verify the drive itself is the **2.5" SATA** model, not M.2. The 2.5" looks
like a laptop drive; M.2 looks like a stick of gum.

---

## B. BIOS check

1. Power on. **Press F2 repeatedly** at the Dell splash screen.
2. Find **System Configuration → Drives** (or "Storage" / "SATA Operation"
   depending on BIOS version).
3. The drive should appear as `Crucial CT2000BX500SSD` or similar.

If listed → save & exit, boot to Windows. Tell Claude "BIOS sees the
drive" and I'll initialize it via SSH.

If NOT listed, also check in BIOS:
- **SATA Operation** = `AHCI` (not RAID, not Disabled)
- Any "Enable Secondary SATA" setting → On
- If the BIOS has POST drive-detection messages, look for `Boot Sequence`
  or `Drive Information` for the actual SATA port status.

If BIOS still doesn't see it after reseating + AHCI:
- Try a different SATA combo cable if you have one
- The drive may be DOA (rare on a sealed new BX500)

---

## C. Once Windows sees it (Claude runs this via SSH)

When BIOS detects the drive and Windows boots, Disk Management will show
it as Disk 3 (or similar number), RAW / Unallocated. Single PowerShell
command will initialize, partition, format, and assign `T:\`:

```powershell
$disk = Get-Disk | Where-Object { $_.PartitionStyle -eq 'RAW' -and $_.Size -gt 1.5TB }
Initialize-Disk -Number $disk.Number -PartitionStyle GPT
New-Partition -DiskNumber $disk.Number -UseMaximumSize -DriveLetter T
Format-Volume -DriveLetter T -FileSystem NTFS -NewFileSystemLabel 'traxis' -Confirm:$false
```

`T:` for "Traxis" — easy to remember, won't collide with `C:` (boot) or
`D:` (USB backup).

Then `C:\traxis\` becomes `T:\traxis\` in the install scripts.
