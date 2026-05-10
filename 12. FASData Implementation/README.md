# FOCAS Connection Test - Traxis Manufacturing

This test verifies FOCAS connectivity to your FANUC CNC machines.

## Prerequisites

1. **Windows PC** on the same network as your CNCs
2. **.NET 6.0 SDK** (x86 version) - Download from:
   https://dotnet.microsoft.com/download/dotnet/6.0
   
   **Important:** Download the **x86** version (not x64) to match the 32-bit FOCAS DLLs.

## Quick Start

### Step 1: Edit the IP Address

Open `Program.cs` in Notepad and change line 15:

```csharp
const string MACHINE_IP = "192.168.1.100";  // ← Change to your machine's IP
```

Save the file.

### Step 2: Build and Run

Open Command Prompt in this folder and run:

```
dotnet build
dotnet run
```

Or to test a specific IP without editing:

```
dotnet run 192.168.1.50
```

## Expected Output (Success)

```
╔════════════════════════════════════════════════════════════╗
║           FANUC FOCAS Connection Test                      ║
║           Traxis Manufacturing                             ║
╚════════════════════════════════════════════════════════════╝

Target Machine: 192.168.1.100:8193
------------------------------------------------------------

[1] Network Ping Test...
    ✓ Machine responds to ping

[2] FOCAS Connection...
    ✓ Connected! Handle: 1

[3] Reading CNC ID...
    ✓ CNC ID: 12345678-ABCD1234-56789ABC-DEF01234

[4] Reading System Info...
    ✓ CNC Type: 0F
    ✓ Machine Type: M
    ✓ Series: 0i-F
    ✓ Max Axes: 3

[5] Reading Machine Status...
    ✓ Mode: MEM (Auto)
    ✓ Run Status: STOP (***)
    ✓ Motion: *** (No motion)
    ✓ Emergency: OFF
    ✓ Alarm: None

[6] Reading Program Number...
    ✓ Running Program: O0001
    ✓ Main Program: O0001

[7] Reading Spindle Speed...
    ✓ Actual Spindle Speed: 0 RPM

============================================================
TEST COMPLETE - ALL CHECKS PASSED ✓
============================================================
```

## Troubleshooting

### Error -16: Connection refused

The most common issue. Check on the CNC:

1. Press **[SYSTEM]** → **[EMBED PORT]** or **[ETHER]**
2. Verify the **IP address** is correct
3. Press **[FOCAS2]** tab
4. **TCP PORT NUMBER** must be **8193** (if it shows 0, FOCAS is disabled!)

### Error -15: DLL not found

Make sure all these DLLs are in the same folder as the .exe:
- Fwlib32.dll
- fwlibe1.dll  
- fwlib30i.dll (for 0i-MF, 0i-MC, 0i-F)
- Fwlib160.dll (for 16i)

### Ping works but FOCAS fails

- Check Windows Firewall isn't blocking the app
- Try: `Test-NetConnection -ComputerName 192.168.1.100 -Port 8193` in PowerShell
- If port test fails, FOCAS is not enabled on the CNC

### "Platform target x86" errors

Make sure you installed the **x86** version of .NET SDK, not x64.

## CNC Configuration Reference

To enable FOCAS on your FANUC control:

1. **[SYSTEM]** → **[EMBED PORT]** (or ETHER BOARD)
2. Under **[COMMON]**: Set IP address, subnet mask, gateway
3. Under **[FOCAS2]**: 
   - **TCP PORT NUMBER** = **8193**
   - (Must not be 0!)

## Files Included

| File | Purpose |
|------|---------|
| Program.cs | Test application source code |
| FocasTest.csproj | Project configuration |
| Fwlib32.dll | Main FOCAS library |
| fwlibe1.dll | Ethernet support |
| fwlib30i.dll | 30i/31i/0i-F series support |
| Fwlib160.dll | 16i/18i series support |
| Fwlib0i.dll | 0i-A series support |
| Fwlib0iB.dll | 0i-B series support |
| fwlib0iD.dll | 0i-D series support |

## Your Machine Inventory

| Machine | Control | Required DLL | IP Address |
|---------|---------|--------------|------------|
| Mill-2 (Smec) | 0i-MF | fwlib30i.dll | __________ |
| Mill-3 (Smec) | 0i-MF | fwlib30i.dll | __________ |
| Mill-4 (Black Robodrill) | 0i-MC | fwlib30i.dll | __________ |
| Mill-5 (White Robodrill) | 16i | Fwlib160.dll | __________ |
| Mill-6 (Chevalier) | 0i-MF | fwlib30i.dll | __________ |
| Mill-7 (5-axis Robodrill) | FANUC | fwlib30i.dll | __________ |
| Mill-8 (Hyundai-Wia) | i-series | fwlib30i.dll | __________ |
| T2 (YCM Lathe) | 0i-MF | fwlib30i.dll | __________ |

Fill in the IP addresses as you test each machine.

## Next Steps

Once all machines pass this test:
1. Record the IP addresses and CNC IDs
2. We can build the production monitoring system
3. Integrate with your clock feedback display

---
*Test prepared for Traxis Manufacturing - January 2026*
