using System.Runtime.InteropServices;

namespace FocasMonitor;

/// <summary>
/// P/Invoke wrapper for FANUC FOCAS library (Fwlib32.dll)
/// Complete 0i-MF function set — collect everything, use what's needed
/// </summary>
public static class Focas
{
    private const string FWLIB = "Fwlib32.dll";

    // =====================================================================
    // CONNECTION
    // =====================================================================

    [DllImport(FWLIB)]
    public static extern short cnc_allclibhndl3(string ip, ushort port, int timeout, out ushort handle);

    [DllImport(FWLIB)]
    public static extern short cnc_freelibhndl(ushort handle);

    // =====================================================================
    // SYSTEM INFO
    // =====================================================================

    [DllImport(FWLIB)]
    public static extern short cnc_sysinfo(ushort handle, out ODBSYS sysinfo);

    [DllImport(FWLIB)]
    public static extern short cnc_rdcncid(ushort handle, [Out] uint[] cncid);

    [DllImport(FWLIB)]
    public static extern short cnc_statinfo(ushort handle, out ODBST statinfo);

    [DllImport(FWLIB)]
    public static extern short cnc_statinfo2(ushort handle, out ODBST2 statinfo);

    // =====================================================================
    // PROGRAM EXECUTION
    // =====================================================================

    [DllImport(FWLIB)]
    public static extern short cnc_rdprgnum(ushort handle, out ODBPRO prgnum);

    [DllImport(FWLIB)]
    public static extern short cnc_rdseqnum(ushort handle, out ODBSEQ seqnum);

    [DllImport(FWLIB)]
    public static extern short cnc_rdblkcount(ushort handle, out int blkcount);

    /// <summary>Read currently executing block content (the G-code line)</summary>
    [DllImport(FWLIB)]
    public static extern short cnc_rdexecprog(ushort handle, ref ushort length, out short blknum, byte[] buf);

    /// <summary>Read program directory (list of programs in controller memory)</summary>
    [DllImport(FWLIB)]
    public static extern short cnc_rdprogdir2(ushort handle, short type, ref short num, PRGDIR2[] dir);

    /// <summary>
    /// Read program directory v3 — preferred on 0i-class controls.
    /// type=0: enumerate from top_prog onward (returns up to num_prog entries).
    /// type=1: look up a single program by number (top_prog is the program number, num_prog must be 1).
    /// type=2: enumerate skipping comment-less programs.
    /// </summary>
    [DllImport(FWLIB)]
    public static extern short cnc_rdprogdir3(
        ushort handle,
        short type,
        ref int top_prog,
        ref short num_prog,
        [Out] PRGDIR3[] buf
    );

    /// <summary>Upload program from controller — initiate</summary>
    [DllImport(FWLIB)]
    public static extern short cnc_upstart(ushort handle, short type, int prog_no);

    /// <summary>Upload program from controller — read data</summary>
    [DllImport(FWLIB)]
    public static extern short cnc_upload(ushort handle, ref ODBUP buf, ref ushort length);

    /// <summary>Upload program from controller — end</summary>
    [DllImport(FWLIB)]
    public static extern short cnc_upend(ushort handle);

    // =====================================================================
    // SPEEDS AND FEEDS
    // =====================================================================

    [DllImport(FWLIB)]
    public static extern short cnc_rdspeed(ushort handle, short type, out ODBSPEED speed);

    [DllImport(FWLIB)]
    public static extern short cnc_rdfeedoveride(ushort handle, short grp, out short ovr);

    [DllImport(FWLIB)]
    public static extern short cnc_rdspindleid(ushort handle, short grp, out short ovr);

    /// <summary>Spindle load % — 0 to 200 (100 = rated load)</summary>
    [DllImport(FWLIB)]
    public static extern short cnc_rdspload(ushort handle, short spindle_no, out ODBSPLOAD spload);

    /// <summary>Spindle meter — load and speed for all spindles</summary>
    [DllImport(FWLIB)]
    public static extern short cnc_rdspmeter(ushort handle, short type, ref short spindle_no, ODBSPEED[] meter);

    // =====================================================================
    // AXIS POSITIONS
    // =====================================================================

    [DllImport(FWLIB)]
    public static extern short cnc_absolute2(ushort handle, short axis, short length, out ODBAXIS pos);

    [DllImport(FWLIB)]
    public static extern short cnc_relative2(ushort handle, short axis, short length, out ODBAXIS pos);

    [DllImport(FWLIB)]
    public static extern short cnc_machine2(ushort handle, short axis, short length, out ODBAXIS pos);

    [DllImport(FWLIB)]
    public static extern short cnc_distance2(ushort handle, short axis, short length, out ODBAXIS pos);

    // =====================================================================
    // SERVO MOTOR DATA
    // =====================================================================

    /// <summary>Servo motor load % per axis</summary>
    [DllImport(FWLIB)]
    public static extern short cnc_rdsvmeter(ushort handle, ref short axis_no, [In, Out] ODBSVLOAD[] meter);

    // =====================================================================
    // TOOLING
    // =====================================================================

    /// <summary>Current tool number T in spindle</summary>
    [DllImport(FWLIB)]
    public static extern short cnc_rdtool(ushort handle, out ODBTOOL tool);

    /// <summary>Tool offset values — all H (length) and D (diameter) wear registers</summary>
    [DllImport(FWLIB)]
    public static extern short cnc_rdtofs(ushort handle, short s_number, short e_number, short type, ODBTOFS[] tofs);

    /// <summary>Tool offset info — how many offsets are configured</summary>
    [DllImport(FWLIB)]
    public static extern short cnc_rdtofsinfo(ushort handle, out ODBTOFSINFO tofsinfo);

    /// <summary>Tool life management info — number of groups configured</summary>
    [DllImport(FWLIB)]
    public static extern short cnc_rdtlinfo(ushort handle, out ODBTLINFO tlinfo);

    /// <summary>Tool life management — used/remaining for a specific group</summary>
    [DllImport(FWLIB)]
    public static extern short cnc_rdtlife(ushort handle, short grp_no, out ODBTLIFE tlife);

    /// <summary>Tool life management — individual tool data within a group</summary>
    [DllImport(FWLIB)]
    public static extern short cnc_rdtlifd(ushort handle, short grp_no, short tool_no, out ODBTLIFD tlifd);

    /// <summary>Tool life group detail</summary>
    [DllImport(FWLIB)]
    public static extern short cnc_rdtlgrp(ushort handle, short grp_no, out ODBTLGRP tlgrp);

    // =====================================================================
    // ALARMS
    // =====================================================================

    [DllImport(FWLIB)]
    public static extern short cnc_alarm(ushort handle, out ODBALM alarm);

    [DllImport(FWLIB)]
    public static extern short cnc_rdalmmsg(ushort handle, short type, ref short num, [Out] ODBALMMSG[] msgs);

    // =====================================================================
    // WORK COORDINATES
    // =====================================================================

    /// <summary>Work coordinate offsets — G54 through G59 and extended (G54.1 Pn)</summary>
    [DllImport(FWLIB)]
    public static extern short cnc_rdwkcofs(ushort handle, short type, short s_number, short e_number, ODBWKOFS[] wkcofs);

    /// <summary>Workpiece coordinate shift value</summary>
    [DllImport(FWLIB)]
    public static extern short cnc_rdwkcdshft(ushort handle, short axis, out ODBWKCDSHFT wkcdshft);

    // =====================================================================
    // MODAL G-CODES
    // =====================================================================

    /// <summary>Currently active modal G codes (G54/G55, G90/G91, G94/G95, etc)</summary>
    [DllImport(FWLIB)]
    public static extern short cnc_modal(ushort handle, short type, short length, ODBMDL modal);

    // =====================================================================
    // MACRO VARIABLES
    // =====================================================================

    /// <summary>Read a single macro variable (#100-#199 local, #500-#999 common)</summary>
    [DllImport(FWLIB)]
    public static extern short cnc_rdmacro(ushort handle, short var_no, out ODBM macro);

    /// <summary>Read range of macro variables</summary>
    [DllImport(FWLIB)]
    public static extern short cnc_rdmacror(ushort handle, short s_number, short e_number, ref short length, ODBM[] macro);

    // =====================================================================
    // PARAMETERS
    // =====================================================================

    /// <summary>Read a single parameter by number — handles all types</summary>
    [DllImport(FWLIB)]
    public static extern short cnc_rdparam(ushort handle, short number, short axis, short length, out IODBPSD param);

    /// <summary>Read a range of parameters</summary>
    [DllImport(FWLIB)]
    public static extern short cnc_rdparar(ushort handle, ref short s_number, short axis, ref short e_number, IODBPSD[] param);

    // =====================================================================
    // DIAGNOSIS DATA (machine counters and temperatures)
    // =====================================================================

    /// <summary>
    /// Read diagnosis data (cnc_rddiag not in this DLL — use cnc_diagnoss instead)
    /// Key numbers: 300=power-on time, 301=cutting time, 302=cycle time (all in minutes)
    /// 400-499 = servo diagnostic data
    /// </summary>
    [DllImport(FWLIB)]
    public static extern short cnc_diagnoss(ushort handle, short number, short axis, short length, out IODBPSD diag);

    [DllImport(FWLIB, EntryPoint = "cnc_diagnoss")]
    public static extern short cnc_diagnoss_raw(ushort handle, short number, short axis, short length, byte[] buf);

    // =====================================================================
    // OPERATION HISTORY
    // =====================================================================

    /// <summary>Read operation history — MDI inputs, mode changes, alarms with timestamps</summary>
    [DllImport(FWLIB)]
    public static extern short cnc_rdophist(ushort handle, ushort dev_no, ref ushort length, byte[] buf);

    // =====================================================================
    // PMC I/O (PLC signals)
    // =====================================================================

    /// <summary>
    /// Read PMC signals by address
    /// adr_type: 0=G(CNC→PLC), 1=F(PLC→CNC), 2=Y(outputs), 3=X(inputs), 4=A, 5=R(relay), 9=D(data)
    /// data_type: 0=byte, 1=word(2-byte), 2=long(4-byte)
    /// length: 8 + (adr_end - adr_start + 1) * element_size
    /// </summary>
    [DllImport(FWLIB)]
    public static extern short pmc_rdpmcrng(ushort handle, short adr_type, short data_type, short adr_start, short adr_end, ushort length, byte[] buf);

    // =====================================================================
    // STRUCTURES
    // =====================================================================

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Ansi)]
    public struct ODBSYS
    {
        public short addinfo;
        public short max_axis;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 2)]
        public string cnc_type;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 2)]
        public string mt_type;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 4)]
        public string series;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 4)]
        public string version;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 2)]
        public string axes;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct ODBST
    {
        public short hdck;
        public short tmmode;
        public short aut;       // 0=MDI, 1=MEM, 3=EDIT, 4=HANDLE, 5=JOG, 6=TJOG, 7=THND
        public short run;       // 0=***, 1=STOP, 2=HOLD, 3=STRT, 4=MSTR
        public short motion;    // 0=***, 1=MTN, 2=DWL
        public short mstb;
        public short emergency;
        public short alarm;
        public short edit;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct ODBST2
    {
        public short hdck;
        public short tmmode;
        public short aut;
        public short run;
        public short motion;
        public short mstb;
        public short emergency;
        public short alarm;
        public short edit;
        public short warning;   // warning status (additional to alarm)
        public short bldact;
        public short feed_hold;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct ODBPRO
    {
        public short dummy1;
        public short dummy2;
        public short data;      // running program number
        public short mdata;     // main program number
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct ODBSEQ
    {
        public short dummy1;
        public short dummy2;
        public int data;        // current sequence number (N number) — long in FOCAS = int in C#
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct ODBSPEED
    {
        public SPEEDELM actf;
        public SPEEDELM acts;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct SPEEDELM
    {
        public int data;        // actual value (×10^-dec)
        public short dec;       // decimal places
        public short unit;      // 0=mm/min, 1=inch/min, 2=rpm
        public short disp;      // display digits
        public byte name;       // name character ('F' or 'S')
        public byte suff;       // suffix character
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct ODBSPLOAD
    {
        public short datano;
        public short type;
        [MarshalAs(UnmanagedType.ByValArray, SizeConst = 4)]
        public short[] data;    // spindle load data (up to 4 spindles)
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct ODBSVLOAD
    {
        public int data;        // servo load value
        public short dec;       // decimal places
        public short unit;      // unit
        public byte name;       // axis name character ('X','Y','Z','A')
        public byte suff1;
        public byte suff2;
        public byte reserve;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct ODBAXIS
    {
        public short dummy;
        public short type;
        [MarshalAs(UnmanagedType.ByValArray, SizeConst = 32)]
        public int[] data;      // MAX_AXIS = 32
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct ODBALM
    {
        public short dummy1;
        public short dummy2;
        public int data;        // alarm status (long in FOCAS = int in C#)
    }

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Ansi)]
    public struct ODBALMMSG
    {
        public short alm_no;
        public short type;
        public short axis;
        public short dummy;
        public short msg_len;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)]
        public string alm_msg;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct ODBTOOL
    {
        public short dummy;
        public short tool_no;   // T number in spindle
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct ODBTOFS
    {
        public short number;    // offset number
        [MarshalAs(UnmanagedType.ByValArray, SizeConst = 4)]
        public int[] data;      // [0]=length wear H, [1]=diameter wear D, [2]=length geom, [3]=diameter geom
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct ODBTOFSINFO
    {
        public short ofs_type;  // offset type (1=A, 2=B, 3=C)
        public short use_no;    // number of offsets in use
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct ODBTLINFO
    {
        public short use_grp;   // number of groups in use
        public short max_grp;   // maximum groups
        public short max_tool;  // maximum tools per group
        public short type;      // life type: 0=count, 1=time(min)
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct ODBTLIFE
    {
        public short grp_no;
        public short dummy;
        public int life;        // life limit (minutes or count)
        public int count;       // life used so far
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct ODBTLIFD
    {
        public short tool_no;   // T number
        public short dummy;
        public short h_code;    // H offset number
        public short d_code;    // D offset number
        public short status;    // 0=available, 1=used, 2=life expired
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct ODBTLGRP
    {
        public short grp_no;
        public short tool_num;  // number of tools in group
        public int life;        // life limit
        public int count;       // life used
        public short type;      // life type 0=count, 1=time
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct ODBWKOFS
    {
        public short datano;    // work coordinate number (1=G54, 2=G55, etc)
        public short type;
        [MarshalAs(UnmanagedType.ByValArray, SizeConst = 8)]
        public int[] data;      // offset values per axis
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct ODBWKCDSHFT
    {
        public short dummy;
        public short type;
        [MarshalAs(UnmanagedType.ByValArray, SizeConst = 8)]
        public int[] data;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct ODBMDL
    {
        // Active modal G codes — indexed by group
        // Group 1=motion(G00/G01/G02/G03), Group 14=WCS(G54-G59), etc
        [MarshalAs(UnmanagedType.ByValArray, SizeConst = 30)]
        public short[] g_data;
        [MarshalAs(UnmanagedType.ByValArray, SizeConst = 8)]
        public int[] aux_data;  // M, S, T, B values
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct ODBM
    {
        public short var_no;
        public short dummy;
        public int mcr_val;     // value (multiply by 10^(-dec_val) for actual)
        public short dec_val;   // decimal places; -1 = vacant/undefined
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct IODBPSD
    {
        public short parameter;
        public short type;      // parameter type: 0=byte, 1=word, 2=2word, 3=real
        public short axis;
        public short dummy;
        // Union — read as appropriate type
        public int idata;       // integer value
        public double rdata;    // real value (for type=3)
    }

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Ansi)]
    public struct PRGDIR2
    {
        public int number;      // program number
        public int length;      // program size in bytes
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 51)]
        public string comment;  // program comment (first line)
    }

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Ansi)]
    public struct PRGDATE
    {
        public short year;
        public short month;
        public short day;
        public short hour;
        public short minute;
        public short second;
    }

    /// <summary>
    /// Program directory entry returned by cnc_rdprogdir3.
    /// Layout matches FANUC's PRGDIR3 — different from PRGDIR2 (extra page/dates fields).
    /// </summary>
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Ansi)]
    public struct PRGDIR3
    {
        public int number;          // program number
        public int length;          // program size in bytes/chars
        public int page;            // unused on 0i series
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 52)]
        public string comment;      // program comment (up to 48 chars + parens + null)
        public PRGDATE mdate;       // last modification date
        public PRGDATE cdate;       // creation date
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct ODBUP
    {
        public short dummy;
        public short type;
        [MarshalAs(UnmanagedType.ByValArray, SizeConst = 256)]
        public byte[] data;
    }

    // =====================================================================
    // RAW-BUFFER OVERLOADS (for struct diagnostics — oversized byte[] prevents overflow)
    // =====================================================================

    [DllImport(FWLIB, EntryPoint = "cnc_statinfo")]
    public static extern short cnc_statinfo_raw(ushort handle, byte[] buf);

    [DllImport(FWLIB, EntryPoint = "cnc_statinfo2")]
    public static extern short cnc_statinfo2_raw(ushort handle, byte[] buf);

    [DllImport(FWLIB, EntryPoint = "cnc_rdprgnum")]
    public static extern short cnc_rdprgnum_raw(ushort handle, byte[] buf);

    [DllImport(FWLIB, EntryPoint = "cnc_rdseqnum")]
    public static extern short cnc_rdseqnum_raw(ushort handle, byte[] buf);

    [DllImport(FWLIB, EntryPoint = "cnc_rdblkcount")]
    public static extern short cnc_rdblkcount_raw(ushort handle, byte[] buf);

    [DllImport(FWLIB, EntryPoint = "cnc_rdspeed")]
    public static extern short cnc_rdspeed_raw(ushort handle, short type, byte[] buf);

    [DllImport(FWLIB, EntryPoint = "cnc_rdspload")]
    public static extern short cnc_rdspload_raw(ushort handle, short sp_no, byte[] buf);

    [DllImport(FWLIB, EntryPoint = "cnc_rdspmeter")]
    public static extern short cnc_rdspmeter_raw(ushort handle, short type, ref short spindle_no, byte[] buf);

    [DllImport(FWLIB, EntryPoint = "cnc_rdtool")]
    public static extern short cnc_rdtool_raw(ushort handle, byte[] buf);

    [DllImport(FWLIB, EntryPoint = "cnc_absolute2")]
    public static extern short cnc_absolute2_raw(ushort handle, short axis, short length, byte[] buf);

    [DllImport(FWLIB, EntryPoint = "cnc_machine2")]
    public static extern short cnc_machine2_raw(ushort handle, short axis, short length, byte[] buf);

    [DllImport(FWLIB, EntryPoint = "cnc_distance2")]
    public static extern short cnc_distance2_raw(ushort handle, short axis, short length, byte[] buf);

    [DllImport(FWLIB, EntryPoint = "cnc_rdsvmeter")]
    public static extern short cnc_rdsvmeter_raw(ushort handle, ref short num, byte[] buf);

    [DllImport(FWLIB, EntryPoint = "cnc_alarm")]
    public static extern short cnc_alarm_raw(ushort handle, byte[] buf);

    [DllImport(FWLIB, EntryPoint = "cnc_rdalmmsg")]
    public static extern short cnc_rdalmmsg_raw(ushort handle, short type, ref short num, byte[] buf);

    [DllImport(FWLIB, EntryPoint = "cnc_modal")]
    public static extern short cnc_modal_raw(ushort handle, short type, short length, byte[] buf);

    [DllImport(FWLIB, EntryPoint = "cnc_rdtool_f2")]
    public static extern short cnc_rdtool_f2_raw(ushort handle, short sp_no, byte[] buf);

    [DllImport(FWLIB, EntryPoint = "cnc_rdmacro")]
    public static extern short cnc_rdmacro_raw(ushort handle, short var_no, byte[] buf);

    [DllImport(FWLIB, EntryPoint = "cnc_rdntool")]
    public static extern short cnc_rdntool_raw(ushort handle, short sp_no, byte[] buf);

    // =====================================================================
    // HELPER METHODS
    // =====================================================================

    public static string GetModeString(short aut) => aut switch
    {
        0 => "MDI",
        1 => "MEM",
        3 => "EDIT",
        4 => "HANDLE",
        5 => "JOG",
        6 => "TJOG",
        7 => "THND",
        8 => "INC",
        9 => "REF",
        _ => $"UNK({aut})"
    };

    public static string GetRunStatusString(short run) => run switch
    {
        0 => "***",
        1 => "STOP",
        2 => "HOLD",
        3 => "STRT",
        4 => "MSTR",
        _ => $"UNK({run})"
    };

    public static string GetMotionString(short motion) => motion switch
    {
        0 => "***",
        1 => "MTN",
        2 => "DWL",
        _ => $"UNK({motion})"
    };

    /// <summary>
    /// Parse CAPTURE tags from an active block comment string.
    /// Returns null if no CAPTURE tags found.
    /// Expected format: (CAPTURE:KEY=VALUE)
    /// </summary>
    public static Dictionary<string, string>? ParseCaptureTags(string blockContent)
    {
        if (!blockContent.Contains("CAPTURE:")) return null;

        var tags = new Dictionary<string, string>();
        // Find all (CAPTURE:KEY=VALUE) patterns
        int start = 0;
        while ((start = blockContent.IndexOf("(CAPTURE:", start)) >= 0)
        {
            int end = blockContent.IndexOf(')', start);
            if (end < 0) break;
            var tag = blockContent.Substring(start + 9, end - start - 9); // strip "(CAPTURE:"
            var eq = tag.IndexOf('=');
            if (eq > 0)
            {
                tags[tag[..eq].Trim()] = tag[(eq + 1)..].Trim();
            }
            start = end + 1;
        }
        return tags.Count > 0 ? tags : null;
    }

    /// <summary>
    /// Read active block comment as string.
    /// Returns null if machine not running or read fails.
    /// </summary>
    public static string? ReadActiveBlockComment(ushort handle)
    {
        try
        {
            ushort length = 256;
            var buf = new byte[256];
            short ret = cnc_rdexecprog(handle, ref length, out _, buf);
            if (ret != 0 || length == 0) return null;
            return System.Text.Encoding.ASCII.GetString(buf, 0, length).Trim('\0');
        }
        catch { return null; }
    }

    /// <summary>
    /// Read a single integer parameter safely.
    /// Returns null on failure.
    /// </summary>
    public static int? ReadParameter(ushort handle, short paramNumber)
    {
        try
        {
            short ret = cnc_rdparam(handle, paramNumber, 0, 8, out var param);
            return ret == 0 ? param.idata : null;
        }
        catch { return null; }
    }

    /// <summary>
    /// Read diagnosis counter safely (power-on time, cutting time, cycle time).
    /// Uses cnc_diagnoss (cnc_rddiag not available in this DLL).
    /// Returns null on failure.
    /// </summary>
    public static int? ReadDiagnosis(ushort handle, short diagNumber)
    {
        try
        {
            // Try raw buffer first to reliably read the 4-byte int value
            var buf = new byte[32];
            short ret = cnc_diagnoss_raw(handle, diagNumber, 0, 8 + 8, buf);
            if (ret == 0)
            {
                // IODBPSD layout: short datano(2) + short type(2) + short axis(2) + short dummy(2) + int idata(4)
                return BitConverter.ToInt32(buf, 8);
            }
            return null;
        }
        catch { return null; }
    }
}
