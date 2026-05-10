using System;
using System.Runtime.InteropServices;
using System.Net.NetworkInformation;

namespace FocasTest
{
    class Program
    {
        // ============================================================
        // CONFIGURATION - EDIT THIS SECTION
        // ============================================================
        
        // Machine IP address - change this to your machine's IP
        const string MACHINE_IP = "192.168.1.100";
        
        // FOCAS port - default is 8193, rarely needs changing
        const ushort MACHINE_PORT = 8193;
        
        // Connection timeout in seconds
        const int TIMEOUT = 10;

        // ============================================================
        // FOCAS DLL IMPORTS
        // ============================================================
        
        [DllImport("Fwlib32.dll", EntryPoint = "cnc_allclibhndl3")]
        public static extern short cnc_allclibhndl3(
            string ipAddr, 
            ushort port, 
            int timeout, 
            out ushort handle);

        [DllImport("Fwlib32.dll", EntryPoint = "cnc_freelibhndl")]
        public static extern short cnc_freelibhndl(ushort handle);

        [DllImport("Fwlib32.dll", EntryPoint = "cnc_rdcncid")]
        public static extern short cnc_rdcncid(ushort handle, uint[] cncId);

        [DllImport("Fwlib32.dll", EntryPoint = "cnc_statinfo")]
        public static extern short cnc_statinfo(ushort handle, out ODBST statinfo);

        [DllImport("Fwlib32.dll", EntryPoint = "cnc_rdprgnum")]
        public static extern short cnc_rdprgnum(ushort handle, out ODBPRO prgnum);

        [DllImport("Fwlib32.dll", EntryPoint = "cnc_acts")]
        public static extern short cnc_acts(ushort handle, out ODBACT actualSpeed);

        [DllImport("Fwlib32.dll", EntryPoint = "cnc_absolute")]
        public static extern short cnc_absolute(ushort handle, short axis, short length, out ODBAXIS absPos);

        [DllImport("Fwlib32.dll", EntryPoint = "cnc_sysinfo")]
        public static extern short cnc_sysinfo(ushort handle, out ODBSYS sysinfo);

        // ============================================================
        // FOCAS STRUCTURES
        // ============================================================

        [StructLayout(LayoutKind.Sequential, Pack = 4)]
        public struct ODBST
        {
            public short dummy1;
            public short dummy2;
            public short aut;       // Auto mode: 0=MDI, 1=MEM, 2=EDIT, etc.
            public short manual;    // Manual mode
            public short run;       // Run status: 0=STOP, 1=HOLD, 2=START, 3=MSTR, 4=RSTR
            public short edit;      // Edit status
            public short motion;    // Motion status: 0=***, 1=MTN, 2=DWL
            public short mstb;      // M/S/T/B status
            public short emergency; // Emergency: 0=OFF, 1=EMG, 2=RESET
            public short write;     // Write status
            public short labelskip; // Label skip
            public short alarm;     // Alarm status: 0=No alarm, 1=Alarm
            public short warning;   // Warning status
            public short battery;   // Battery status
        }

        [StructLayout(LayoutKind.Sequential, Pack = 4)]
        public struct ODBPRO
        {
            public short dummy1;
            public short dummy2;
            public short data;      // Running program number
            public short mdata;     // Main program number
        }

        [StructLayout(LayoutKind.Sequential, Pack = 4)]
        public struct ODBACT
        {
            public short dummy1;
            public short dummy2;
            public int data;        // Actual spindle speed
        }

        [StructLayout(LayoutKind.Sequential, Pack = 4)]
        public struct ODBAXIS
        {
            public short dummy1;
            public short dummy2;
            public int data;        // Axis position (units depend on machine config)
        }

        [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Ansi, Pack = 4)]
        public struct ODBSYS
        {
            public short addinfo;
            public short max_axis;
            [MarshalAs(UnmanagedType.ByValArray, SizeConst = 2)]
            public char[] cnc_type;
            [MarshalAs(UnmanagedType.ByValArray, SizeConst = 2)]
            public char[] mt_type;
            [MarshalAs(UnmanagedType.ByValArray, SizeConst = 4)]
            public char[] series;
            [MarshalAs(UnmanagedType.ByValArray, SizeConst = 4)]
            public char[] version;
            [MarshalAs(UnmanagedType.ByValArray, SizeConst = 2)]
            public char[] axes;
        }

        // ============================================================
        // MAIN PROGRAM
        // ============================================================

        static void Main(string[] args)
        {
            Console.WriteLine("╔════════════════════════════════════════════════════════════╗");
            Console.WriteLine("║           FANUC FOCAS Connection Test                      ║");
            Console.WriteLine("║           Traxis Manufacturing                             ║");
            Console.WriteLine("╚════════════════════════════════════════════════════════════╝");
            Console.WriteLine();

            // Allow command line override of IP
            string machineIp = MACHINE_IP;
            if (args.Length > 0)
            {
                machineIp = args[0];
            }

            Console.WriteLine($"Target Machine: {machineIp}:{MACHINE_PORT}");
            Console.WriteLine(new string('-', 60));

            // Step 1: Ping test
            Console.WriteLine("\n[1] Network Ping Test...");
            if (!PingHost(machineIp))
            {
                Console.WriteLine("    ❌ FAILED - Cannot ping machine");
                Console.WriteLine("    Check: Network cable, IP address, machine powered on");
                WaitForKey();
                return;
            }
            Console.WriteLine("    ✓ Machine responds to ping");

            // Step 2: Connect via FOCAS
            Console.WriteLine("\n[2] FOCAS Connection...");
            ushort handle = 0;
            short ret = cnc_allclibhndl3(machineIp, MACHINE_PORT, TIMEOUT, out handle);
            
            if (ret != 0)
            {
                Console.WriteLine($"    ❌ FAILED - Error code: {ret}");
                PrintConnectionError(ret);
                WaitForKey();
                return;
            }
            Console.WriteLine($"    ✓ Connected! Handle: {handle}");

            try
            {
                // Step 3: Read CNC ID
                Console.WriteLine("\n[3] Reading CNC ID...");
                uint[] cncId = new uint[4];
                ret = cnc_rdcncid(handle, cncId);
                if (ret == 0)
                {
                    string id = $"{cncId[0]:X8}-{cncId[1]:X8}-{cncId[2]:X8}-{cncId[3]:X8}";
                    Console.WriteLine($"    ✓ CNC ID: {id}");
                }
                else
                {
                    Console.WriteLine($"    ⚠ Could not read CNC ID (error {ret})");
                }

                // Step 4: Read System Info
                Console.WriteLine("\n[4] Reading System Info...");
                ODBSYS sysinfo;
                ret = cnc_sysinfo(handle, out sysinfo);
                if (ret == 0)
                {
                    string cncType = new string(sysinfo.cnc_type).Trim('\0');
                    string mtType = new string(sysinfo.mt_type).Trim('\0');
                    string series = new string(sysinfo.series).Trim('\0');
                    string version = new string(sysinfo.version).Trim('\0');
                    Console.WriteLine($"    ✓ CNC Type: {cncType}");
                    Console.WriteLine($"    ✓ Machine Type: {mtType}");
                    Console.WriteLine($"    ✓ Series: {series}");
                    Console.WriteLine($"    ✓ Version: {version}");
                    Console.WriteLine($"    ✓ Max Axes: {sysinfo.max_axis}");
                }
                else
                {
                    Console.WriteLine($"    ⚠ Could not read system info (error {ret})");
                }

                // Step 5: Read Machine Status
                Console.WriteLine("\n[5] Reading Machine Status...");
                ODBST status;
                ret = cnc_statinfo(handle, out status);
                if (ret == 0)
                {
                    Console.WriteLine($"    ✓ Mode: {GetModeString(status.aut)}");
                    Console.WriteLine($"    ✓ Run Status: {GetRunString(status.run)}");
                    Console.WriteLine($"    ✓ Motion: {GetMotionString(status.motion)}");
                    Console.WriteLine($"    ✓ Emergency: {(status.emergency == 0 ? "OFF" : "⚠ ACTIVE")}");
                    Console.WriteLine($"    ✓ Alarm: {(status.alarm == 0 ? "None" : "⚠ ALARM ACTIVE")}");
                }
                else
                {
                    Console.WriteLine($"    ⚠ Could not read status (error {ret})");
                }

                // Step 6: Read Program Number
                Console.WriteLine("\n[6] Reading Program Number...");
                ODBPRO prgnum;
                ret = cnc_rdprgnum(handle, out prgnum);
                if (ret == 0)
                {
                    Console.WriteLine($"    ✓ Running Program: O{prgnum.data:D4}");
                    Console.WriteLine($"    ✓ Main Program: O{prgnum.mdata:D4}");
                }
                else
                {
                    Console.WriteLine($"    ⚠ Could not read program number (error {ret})");
                }

                // Step 7: Read Spindle Speed
                Console.WriteLine("\n[7] Reading Spindle Speed...");
                ODBACT spindle;
                ret = cnc_acts(handle, out spindle);
                if (ret == 0)
                {
                    Console.WriteLine($"    ✓ Actual Spindle Speed: {spindle.data} RPM");
                }
                else
                {
                    Console.WriteLine($"    ⚠ Could not read spindle speed (error {ret})");
                }

                // Summary
                Console.WriteLine("\n" + new string('=', 60));
                Console.WriteLine("TEST COMPLETE - ALL CHECKS PASSED ✓");
                Console.WriteLine(new string('=', 60));
                Console.WriteLine("\nThis machine is ready for FOCAS monitoring!");
            }
            finally
            {
                // Always disconnect
                Console.WriteLine("\n[8] Disconnecting...");
                ret = cnc_freelibhndl(handle);
                if (ret == 0)
                    Console.WriteLine("    ✓ Disconnected cleanly");
                else
                    Console.WriteLine($"    ⚠ Disconnect warning (error {ret})");
            }

            WaitForKey();
        }

        // ============================================================
        // HELPER FUNCTIONS
        // ============================================================

        static bool PingHost(string host)
        {
            try
            {
                using (Ping ping = new Ping())
                {
                    PingReply reply = ping.Send(host, 3000);
                    return reply.Status == IPStatus.Success;
                }
            }
            catch
            {
                return false;
            }
        }

        static string GetModeString(short mode)
        {
            return mode switch
            {
                0 => "MDI",
                1 => "MEM (Auto)",
                2 => "EDIT",
                3 => "HANDLE",
                4 => "JOG",
                5 => "TJOG",
                6 => "THND",
                7 => "INC",
                8 => "REF",
                9 => "RMT",
                _ => $"Unknown ({mode})"
            };
        }

        static string GetRunString(short run)
        {
            return run switch
            {
                0 => "STOP (***)",
                1 => "HOLD",
                2 => "START (Running)",
                3 => "MSTR (M/S/T/B executing)",
                4 => "RSTR (Restart)",
                _ => $"Unknown ({run})"
            };
        }

        static string GetMotionString(short motion)
        {
            return motion switch
            {
                0 => "*** (No motion)",
                1 => "MTN (Axis moving)",
                2 => "DWL (Dwell)",
                _ => $"Unknown ({motion})"
            };
        }

        static void PrintConnectionError(short errorCode)
        {
            Console.WriteLine();
            Console.WriteLine("    Troubleshooting:");
            switch (errorCode)
            {
                case -2:
                    Console.WriteLine("    → Socket error - check network connection");
                    break;
                case -7:
                    Console.WriteLine("    → Version mismatch - DLL may not match control");
                    break;
                case -8:
                    Console.WriteLine("    → Socket creation error");
                    break;
                case -15:
                    Console.WriteLine("    → DLL not found for this CNC series");
                    Console.WriteLine("    → Make sure fwlib30i.dll is in the same folder");
                    break;
                case -16:
                    Console.WriteLine("    → Connection refused or timed out");
                    Console.WriteLine("    → Check: FOCAS port 8193 enabled on CNC?");
                    Console.WriteLine("    → Check: Firewall blocking connection?");
                    break;
                default:
                    Console.WriteLine($"    → See FOCAS documentation for error {errorCode}");
                    break;
            }
            Console.WriteLine();
            Console.WriteLine("    Steps to verify on CNC:");
            Console.WriteLine("    1. Press [SYSTEM] → [EMBED PORT] or [ETHER BOARD]");
            Console.WriteLine("    2. Check IP address matches what you entered");
            Console.WriteLine("    3. Press [FOCAS2] → TCP PORT must be 8193 (not 0!)");
        }

        static void WaitForKey()
        {
            Console.WriteLine("\nPress any key to exit...");
            Console.ReadKey();
        }
    }
}
