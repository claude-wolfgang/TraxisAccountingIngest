using System.Runtime.InteropServices;

namespace FocasMonitor;

/// <summary>
/// P/Invoke wrapper for FANUC FOCAS library (Fwlib32.dll)
/// </summary>
public static class Focas
{
    private const string FWLIB = "Fwlib32.dll";

    // Connection
    [DllImport(FWLIB)]
    public static extern short cnc_allclibhndl3(string ip, ushort port, int timeout, out ushort handle);

    [DllImport(FWLIB)]
    public static extern short cnc_freelibhndl(ushort handle);

    // System Info
    [DllImport(FWLIB)]
    public static extern short cnc_sysinfo(ushort handle, out ODBSYS sysinfo);

    // CNC ID
    [DllImport(FWLIB)]
    public static extern short cnc_rdcncid(ushort handle, uint[] cncid);

    // Status
    [DllImport(FWLIB)]
    public static extern short cnc_statinfo(ushort handle, out ODBST statinfo);

    // Program Number
    [DllImport(FWLIB)]
    public static extern short cnc_rdprgnum(ushort handle, out ODBPRO prgnum);

    // Spindle Speed
    [DllImport(FWLIB)]
    public static extern short cnc_rdspeed(ushort handle, short type, out ODBSPEED speed);

    // Spindle Override
    [DllImport(FWLIB)]
    public static extern short cnc_rdspindleid(ushort handle, short grp, out short ovr);

    // Feedrate Override
    [DllImport(FWLIB)]
    public static extern short cnc_rdfeedoveride(ushort handle, short grp, out short ovr);

    // Axis Position
    [DllImport(FWLIB)]
    public static extern short cnc_absolute2(ushort handle, short axis, short length, out ODBAXIS pos);

    // Alarm Status
    [DllImport(FWLIB)]
    public static extern short cnc_alarm(ushort handle, out ODBALM alarm);

    // Alarm Messages
    [DllImport(FWLIB)]
    public static extern short cnc_rdalmmsg(ushort handle, short type, ref short num, ODBALMMSG[] msgs);

    // Program Directory (reads program comment)
    [DllImport(FWLIB)]
    public static extern short cnc_rdprogdir3(
        ushort handle,
        short type,
        ref int top_prog,
        ref short num_prog,
        [Out] PRGDIR3[] buf
    );

    // --- Structures ---

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
        public short hdck;      // handwheel check
        public short tmmode;    // T/M mode select
        public short aut;       // AUTO/MAN mode: 0=MDI, 1=MEM, 3=EDIT, 4=HANDLE, 5=JOG, 6=TJOG, 7=THND
        public short run;       // run status: 0=***, 1=STOP, 2=HOLD, 3=STRT, 4=MSTR
        public short motion;    // axis motion: 0=***, 1=MTN, 2=DWL
        public short mstb;      // M/S/T/B status
        public short emergency; // emergency stop: 0=off, 1=on
        public short alarm;     // alarm status: 0=none, 1=alarm, 2=battery
        public short edit;      // edit status
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
    public struct ODBSPEED
    {
        public SPEEDELM actf;   // actual feed
        public SPEEDELM acts;   // actual spindle
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct SPEEDELM
    {
        public int data;        // speed data
        public short dec;       // decimal point
        public short unit;      // unit (0=mm/min, 1=inch/min, 2=rpm)
        public short reserve;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 5)]
        public string name;
        public char suff;       // suffix
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct ODBAXIS
    {
        public short dummy;
        public short type;
        [MarshalAs(UnmanagedType.ByValArray, SizeConst = 8)]
        public int[] data;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct ODBALM
    {
        public short dummy1;
        public short data;      // alarm type
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

    // Program directory entry (type=1: number + comment)
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Ansi)]
    public struct PRGDIR3
    {
        public int number;          // Program number
        public int length;          // Program size in characters
        public int page;            // Not used on 0i series
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 52)]
        public string comment;      // Comment string (up to 48 chars + parens + null)
        public PRGDATE mdate;       // Modification date
        public PRGDATE cdate;       // Creation date
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct PRGDATE
    {
        public short year;
        public short month;
        public short day;
        public short hour;
        public short minute;
        public short dummy;
    }

    // --- Helper Methods ---

    public static string GetModeString(short aut) => aut switch
    {
        0 => "MDI",
        1 => "MEM",
        3 => "EDIT",
        4 => "HANDLE",
        5 => "JOG",
        6 => "TJOG",
        7 => "THND",
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
}
