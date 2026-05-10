using Microsoft.Data.Sqlite;

namespace FocasMonitor;

public class Database : IDisposable
{
    private readonly string _connectionString;

    public Database(string dbPath)
    {
        var dir = Path.GetDirectoryName(dbPath);
        if (!string.IsNullOrEmpty(dir) && !Directory.Exists(dir))
            Directory.CreateDirectory(dir);

        _connectionString = $"Data Source={dbPath}";
        Initialize();
    }

    private void Initialize()
    {
        using var conn = Open();

        // Auto-migrate old schema if needed
        MigrateSchema(conn);

        conn.CreateCommand("""
            CREATE TABLE IF NOT EXISTS machine_samples (
                id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp               TEXT NOT NULL,
                machine_id              TEXT NOT NULL,
                machine_name            TEXT,

                -- Connection
                connected               INTEGER NOT NULL,
                error_message           TEXT,

                -- System info (read once on connect, stored each sample for trend)
                cnc_type                TEXT,   -- e.g. "M " or "T "
                mt_type                 TEXT,   -- machine type
                series                  TEXT,   -- e.g. "0MF "
                sw_version              TEXT,   -- software version
                max_axes                INTEGER,
                cnc_id                  TEXT,   -- unique CNC hardware ID

                -- Operating mode
                mode                    TEXT,   -- MDI/MEM/EDIT/JOG/HANDLE
                run_status              TEXT,   -- STOP/HOLD/STRT/MSTR
                motion                  TEXT,   -- ***/MTN/DWL
                edit_status             INTEGER,
                warning                 INTEGER,

                -- Program
                program_number          INTEGER,
                main_program            INTEGER,
                sequence_number         INTEGER, -- current N number
                block_count             INTEGER, -- blocks executed this cycle

                -- Active block
                active_block_content    TEXT,   -- raw G-code line executing
                capture_session_id      TEXT,   -- parsed from (CAPTURE:SESSION=...)
                capture_op_id           TEXT,   -- parsed from (CAPTURE:OP_ID=...)
                capture_tool_id         TEXT,   -- parsed from (CAPTURE:TOOL_ID=...)

                -- Speeds
                spindle_speed           INTEGER, -- actual RPM
                feed_rate               INTEGER, -- actual feed rate
                spindle_override        INTEGER, -- % override
                feedrate_override       INTEGER, -- % override

                -- Spindle load
                spindle_load            INTEGER, -- % of rated load (0-200)

                -- Current tool
                tool_number             INTEGER, -- T number in spindle

                -- Active work coordinate
                active_wcs              INTEGER, -- G54=1, G55=2, etc (from modal)

                -- Status flags
                emergency               INTEGER,
                alarm                   INTEGER,
                alarm_message           TEXT,

                -- Axis positions — absolute (divide by 1000 for mm)
                axis_x                  INTEGER,
                axis_y                  INTEGER,
                axis_z                  INTEGER,
                axis_a                  INTEGER, -- 4th axis if present
                axis_b                  INTEGER, -- 5th axis if present

                -- Axis positions — machine coordinates
                mach_x                  INTEGER,
                mach_y                  INTEGER,
                mach_z                  INTEGER,

                -- Distance to go (remaining in current move)
                dtg_x                   INTEGER,
                dtg_y                   INTEGER,
                dtg_z                   INTEGER,

                -- Servo loads per axis (%)
                servo_load_x            INTEGER,
                servo_load_y            INTEGER,
                servo_load_z            INTEGER,
                servo_load_a            INTEGER,

                -- Machine life counters (diagnosis data, in minutes)
                diag_power_on_min       INTEGER, -- total power-on time (diag 300)
                diag_cutting_min        INTEGER, -- total cutting time  (diag 301)
                diag_cycle_min          INTEGER, -- total cycle time    (diag 302)

                -- Tool life management (parameter 6800)
                tool_life_enabled       INTEGER, -- bit 0 of P6800
                tool_life_type          TEXT     -- "count" or "time"
            );

            CREATE INDEX IF NOT EXISTS idx_ms_timestamp  ON machine_samples(timestamp);
            CREATE INDEX IF NOT EXISTS idx_ms_machine    ON machine_samples(machine_id);
            CREATE INDEX IF NOT EXISTS idx_ms_mach_time  ON machine_samples(machine_id, timestamp);
            CREATE INDEX IF NOT EXISTS idx_ms_session    ON machine_samples(capture_session_id)
                WHERE capture_session_id IS NOT NULL;
            CREATE INDEX IF NOT EXISTS idx_ms_program    ON machine_samples(machine_id, program_number)
                WHERE program_number IS NOT NULL;
        """).ExecuteNonQuery();

        // Tool wear registers — separate table, polled on every sample when running
        conn.CreateCommand("""
            CREATE TABLE IF NOT EXISTS tool_wear_samples (
                id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp               TEXT NOT NULL,
                machine_id              TEXT NOT NULL,
                capture_session_id      TEXT,   -- from active block CAPTURE tag
                capture_op_id           TEXT,
                tool_number             INTEGER, -- T number
                offset_number           INTEGER, -- H/D register number
                length_wear             INTEGER, -- H wear (×0.001mm)
                diameter_wear           INTEGER, -- D wear (×0.001mm)
                length_geometry         INTEGER, -- H geometry
                diameter_geometry       INTEGER  -- D geometry
            );

            CREATE INDEX IF NOT EXISTS idx_tw_machine    ON tool_wear_samples(machine_id);
            CREATE INDEX IF NOT EXISTS idx_tw_timestamp  ON tool_wear_samples(timestamp);
            CREATE INDEX IF NOT EXISTS idx_tw_session    ON tool_wear_samples(capture_session_id)
                WHERE capture_session_id IS NOT NULL;
            CREATE INDEX IF NOT EXISTS idx_tw_tool       ON tool_wear_samples(machine_id, tool_number);
        """).ExecuteNonQuery();

        // Tool life management — polled when tool life is enabled
        conn.CreateCommand("""
            CREATE TABLE IF NOT EXISTS tool_life_samples (
                id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp               TEXT NOT NULL,
                machine_id              TEXT NOT NULL,
                group_number            INTEGER,
                tool_number             INTEGER, -- T number within group
                h_offset                INTEGER, -- H code assigned
                d_offset                INTEGER, -- D code assigned
                life_limit              INTEGER, -- total limit (min or count)
                life_used               INTEGER, -- used so far
                life_remaining_pct      REAL,    -- calculated
                life_type               TEXT,    -- "time" or "count"
                status                  TEXT     -- "available"/"used"/"expired"
            );

            CREATE INDEX IF NOT EXISTS idx_tl_machine    ON tool_life_samples(machine_id);
            CREATE INDEX IF NOT EXISTS idx_tl_timestamp  ON tool_life_samples(timestamp);
            CREATE INDEX IF NOT EXISTS idx_tl_tool       ON tool_life_samples(machine_id, tool_number);
        """).ExecuteNonQuery();

        // Work coordinate offsets — sampled periodically to detect operator changes
        conn.CreateCommand("""
            CREATE TABLE IF NOT EXISTS wco_samples (
                id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp               TEXT NOT NULL,
                machine_id              TEXT NOT NULL,
                wcs_number              INTEGER, -- 1=G54, 2=G55, 3=G56, 4=G57, 5=G58, 6=G59
                wcs_name                TEXT,    -- "G54" etc
                offset_x                INTEGER,
                offset_y                INTEGER,
                offset_z                INTEGER,
                offset_a                INTEGER,
                changed                 INTEGER  -- 1 if different from previous sample
            );

            CREATE INDEX IF NOT EXISTS idx_wco_machine   ON wco_samples(machine_id);
            CREATE INDEX IF NOT EXISTS idx_wco_timestamp ON wco_samples(timestamp);
        """).ExecuteNonQuery();

        // Parameter snapshots — for tool life config and machine audit
        conn.CreateCommand("""
            CREATE TABLE IF NOT EXISTS parameter_snapshots (
                id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp               TEXT NOT NULL,
                machine_id              TEXT NOT NULL,
                param_number            INTEGER,
                axis                    INTEGER, -- 0 = not axis-specific
                value                   INTEGER,
                description             TEXT     -- human-readable label
            );

            CREATE INDEX IF NOT EXISTS idx_ps_machine    ON parameter_snapshots(machine_id);
            CREATE INDEX IF NOT EXISTS idx_ps_param      ON parameter_snapshots(machine_id, param_number);
        """).ExecuteNonQuery();

        // Alarm history — full log of every alarm event
        conn.CreateCommand("""
            CREATE TABLE IF NOT EXISTS alarm_history (
                id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp               TEXT NOT NULL,
                machine_id              TEXT NOT NULL,
                alarm_number            INTEGER,
                alarm_type              INTEGER,
                alarm_axis              INTEGER,
                alarm_message           TEXT,
                capture_session_id      TEXT,
                capture_op_id           TEXT,
                program_number          INTEGER  -- program running when alarm fired
            );

            CREATE INDEX IF NOT EXISTS idx_ah_machine    ON alarm_history(machine_id);
            CREATE INDEX IF NOT EXISTS idx_ah_timestamp  ON alarm_history(timestamp);
            CREATE INDEX IF NOT EXISTS idx_ah_session    ON alarm_history(capture_session_id)
                WHERE capture_session_id IS NOT NULL;
        """).ExecuteNonQuery();

        // Program directory snapshots — what's loaded in each machine's memory
        conn.CreateCommand("""
            CREATE TABLE IF NOT EXISTS program_directory (
                id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp               TEXT NOT NULL,
                machine_id              TEXT NOT NULL,
                program_number          INTEGER,
                program_size_bytes      INTEGER,
                program_comment         TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_pd_machine    ON program_directory(machine_id);
            CREATE INDEX IF NOT EXISTS idx_pd_program    ON program_directory(machine_id, program_number);
        """).ExecuteNonQuery();
    }

    // =====================================================================
    // SCHEMA MIGRATION
    // =====================================================================

    private void MigrateSchema(SqliteConnection conn)
    {
        // Check if machine_samples exists at all
        var tableExists = false;
        using (var cmd = conn.CreateCommand())
        {
            cmd.CommandText = "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='machine_samples'";
            tableExists = Convert.ToInt32(cmd.ExecuteScalar()) > 0;
        }
        if (!tableExists) return; // Fresh install — CREATE TABLE will handle it

        // Get existing columns
        var existingCols = new HashSet<string>();
        using (var cmd = conn.CreateCommand())
        {
            cmd.CommandText = "PRAGMA table_info(machine_samples)";
            using var reader = cmd.ExecuteReader();
            while (reader.Read())
                existingCols.Add(reader.GetString(1));
        }

        // Columns that may be missing from old schema
        var newColumns = new (string name, string type)[]
        {
            ("cnc_type", "TEXT"), ("mt_type", "TEXT"), ("series", "TEXT"),
            ("sw_version", "TEXT"), ("max_axes", "INTEGER"), ("cnc_id", "TEXT"),
            ("edit_status", "INTEGER"), ("warning", "INTEGER"),
            ("sequence_number", "INTEGER"), ("block_count", "INTEGER"),
            ("active_block_content", "TEXT"),
            ("capture_session_id", "TEXT"), ("capture_op_id", "TEXT"), ("capture_tool_id", "TEXT"),
            ("spindle_load", "INTEGER"), ("tool_number", "INTEGER"), ("active_wcs", "INTEGER"),
            ("axis_a", "INTEGER"), ("axis_b", "INTEGER"),
            ("mach_x", "INTEGER"), ("mach_y", "INTEGER"), ("mach_z", "INTEGER"),
            ("dtg_x", "INTEGER"), ("dtg_y", "INTEGER"), ("dtg_z", "INTEGER"),
            ("servo_load_x", "INTEGER"), ("servo_load_y", "INTEGER"),
            ("servo_load_z", "INTEGER"), ("servo_load_a", "INTEGER"),
            ("diag_power_on_min", "INTEGER"), ("diag_cutting_min", "INTEGER"),
            ("diag_cycle_min", "INTEGER"),
            ("tool_life_enabled", "INTEGER"), ("tool_life_type", "TEXT"),
        };

        int added = 0;
        foreach (var (name, type) in newColumns)
        {
            if (!existingCols.Contains(name))
            {
                using var cmd = conn.CreateCommand();
                cmd.CommandText = $"ALTER TABLE machine_samples ADD COLUMN {name} {type}";
                cmd.ExecuteNonQuery();
                added++;
            }
        }

        if (added > 0)
            Console.WriteLine($"Database migration: added {added} columns to machine_samples");
    }

    // =====================================================================
    // INSERT METHODS
    // =====================================================================

    public void InsertSample(MachineSample s)
    {
        using var conn = Open();
        conn.CreateCommand("""
            INSERT INTO machine_samples (
                timestamp, machine_id, machine_name,
                connected, error_message,
                cnc_type, mt_type, series, sw_version, max_axes, cnc_id,
                mode, run_status, motion, edit_status, warning,
                program_number, main_program, sequence_number, block_count,
                active_block_content, capture_session_id, capture_op_id, capture_tool_id,
                spindle_speed, feed_rate, spindle_override, feedrate_override,
                spindle_load, tool_number, active_wcs,
                emergency, alarm, alarm_message,
                axis_x, axis_y, axis_z, axis_a, axis_b,
                mach_x, mach_y, mach_z,
                dtg_x, dtg_y, dtg_z,
                servo_load_x, servo_load_y, servo_load_z, servo_load_a,
                diag_power_on_min, diag_cutting_min, diag_cycle_min,
                tool_life_enabled, tool_life_type
            ) VALUES (
                @timestamp, @machine_id, @machine_name,
                @connected, @error_message,
                @cnc_type, @mt_type, @series, @sw_version, @max_axes, @cnc_id,
                @mode, @run_status, @motion, @edit_status, @warning,
                @program_number, @main_program, @sequence_number, @block_count,
                @active_block_content, @capture_session_id, @capture_op_id, @capture_tool_id,
                @spindle_speed, @feed_rate, @spindle_override, @feedrate_override,
                @spindle_load, @tool_number, @active_wcs,
                @emergency, @alarm, @alarm_message,
                @axis_x, @axis_y, @axis_z, @axis_a, @axis_b,
                @mach_x, @mach_y, @mach_z,
                @dtg_x, @dtg_y, @dtg_z,
                @servo_load_x, @servo_load_y, @servo_load_z, @servo_load_a,
                @diag_power_on_min, @diag_cutting_min, @diag_cycle_min,
                @tool_life_enabled, @tool_life_type
            )
            """,
            ("@timestamp",            s.Timestamp.ToString("o")),
            ("@machine_id",           s.MachineId),
            ("@machine_name",         s.MachineName),
            ("@connected",            s.Connected ? 1 : 0),
            ("@error_message",        s.ErrorMessage),
            ("@cnc_type",             s.CncType),
            ("@mt_type",              s.MtType),
            ("@series",               s.Series),
            ("@sw_version",           s.SwVersion),
            ("@max_axes",             s.MaxAxes),
            ("@cnc_id",               s.CncId),
            ("@mode",                 s.Mode),
            ("@run_status",           s.RunStatus),
            ("@motion",               s.Motion),
            ("@edit_status",          s.EditStatus),
            ("@warning",              s.Warning),
            ("@program_number",       s.ProgramNumber),
            ("@main_program",         s.MainProgram),
            ("@sequence_number",      s.SequenceNumber),
            ("@block_count",          s.BlockCount),
            ("@active_block_content", s.ActiveBlockContent),
            ("@capture_session_id",   s.CaptureSessionId),
            ("@capture_op_id",        s.CaptureOpId),
            ("@capture_tool_id",      s.CaptureToolId),
            ("@spindle_speed",        s.SpindleSpeed),
            ("@feed_rate",            s.FeedRate),
            ("@spindle_override",     s.SpindleOverride),
            ("@feedrate_override",    s.FeedrateOverride),
            ("@spindle_load",         s.SpindleLoad),
            ("@tool_number",          s.ToolNumber),
            ("@active_wcs",           s.ActiveWcs),
            ("@emergency",            s.Emergency),
            ("@alarm",                s.Alarm),
            ("@alarm_message",        s.AlarmMessage),
            ("@axis_x",               s.AxisX),
            ("@axis_y",               s.AxisY),
            ("@axis_z",               s.AxisZ),
            ("@axis_a",               s.AxisA),
            ("@axis_b",               s.AxisB),
            ("@mach_x",               s.MachX),
            ("@mach_y",               s.MachY),
            ("@mach_z",               s.MachZ),
            ("@dtg_x",                s.DtgX),
            ("@dtg_y",                s.DtgY),
            ("@dtg_z",                s.DtgZ),
            ("@servo_load_x",         s.ServoLoadX),
            ("@servo_load_y",         s.ServoLoadY),
            ("@servo_load_z",         s.ServoLoadZ),
            ("@servo_load_a",         s.ServoLoadA),
            ("@diag_power_on_min",    s.DiagPowerOnMin),
            ("@diag_cutting_min",     s.DiagCuttingMin),
            ("@diag_cycle_min",       s.DiagCycleMin),
            ("@tool_life_enabled",    s.ToolLifeEnabled),
            ("@tool_life_type",       s.ToolLifeType)
        ).ExecuteNonQuery();
    }

    public void InsertToolWearSample(ToolWearSample s)
    {
        using var conn = Open();
        conn.CreateCommand("""
            INSERT INTO tool_wear_samples (
                timestamp, machine_id, capture_session_id, capture_op_id,
                tool_number, offset_number,
                length_wear, diameter_wear, length_geometry, diameter_geometry
            ) VALUES (
                @timestamp, @machine_id, @capture_session_id, @capture_op_id,
                @tool_number, @offset_number,
                @length_wear, @diameter_wear, @length_geometry, @diameter_geometry
            )
            """,
            ("@timestamp",          s.Timestamp.ToString("o")),
            ("@machine_id",         s.MachineId),
            ("@capture_session_id", s.CaptureSessionId),
            ("@capture_op_id",      s.CaptureOpId),
            ("@tool_number",        s.ToolNumber),
            ("@offset_number",      s.OffsetNumber),
            ("@length_wear",        s.LengthWear),
            ("@diameter_wear",      s.DiameterWear),
            ("@length_geometry",    s.LengthGeometry),
            ("@diameter_geometry",  s.DiameterGeometry)
        ).ExecuteNonQuery();
    }

    public void InsertToolLifeSample(ToolLifeSample s)
    {
        using var conn = Open();
        conn.CreateCommand("""
            INSERT INTO tool_life_samples (
                timestamp, machine_id, group_number, tool_number,
                h_offset, d_offset, life_limit, life_used,
                life_remaining_pct, life_type, status
            ) VALUES (
                @timestamp, @machine_id, @group_number, @tool_number,
                @h_offset, @d_offset, @life_limit, @life_used,
                @life_remaining_pct, @life_type, @status
            )
            """,
            ("@timestamp",          s.Timestamp.ToString("o")),
            ("@machine_id",         s.MachineId),
            ("@group_number",       s.GroupNumber),
            ("@tool_number",        s.ToolNumber),
            ("@h_offset",           s.HOffset),
            ("@d_offset",           s.DOffset),
            ("@life_limit",         s.LifeLimit),
            ("@life_used",          s.LifeUsed),
            ("@life_remaining_pct", s.LifeRemainingPct),
            ("@life_type",          s.LifeType),
            ("@status",             s.Status)
        ).ExecuteNonQuery();
    }

    public void InsertWcoSample(WcoSample s)
    {
        using var conn = Open();
        conn.CreateCommand("""
            INSERT INTO wco_samples (
                timestamp, machine_id, wcs_number, wcs_name,
                offset_x, offset_y, offset_z, offset_a, changed
            ) VALUES (
                @timestamp, @machine_id, @wcs_number, @wcs_name,
                @offset_x, @offset_y, @offset_z, @offset_a, @changed
            )
            """,
            ("@timestamp",  s.Timestamp.ToString("o")),
            ("@machine_id", s.MachineId),
            ("@wcs_number", s.WcsNumber),
            ("@wcs_name",   s.WcsName),
            ("@offset_x",   s.OffsetX),
            ("@offset_y",   s.OffsetY),
            ("@offset_z",   s.OffsetZ),
            ("@offset_a",   s.OffsetA),
            ("@changed",    s.Changed ? 1 : 0)
        ).ExecuteNonQuery();
    }

    public void InsertAlarmHistory(AlarmHistorySample s)
    {
        using var conn = Open();
        conn.CreateCommand("""
            INSERT INTO alarm_history (
                timestamp, machine_id, alarm_number, alarm_type, alarm_axis,
                alarm_message, capture_session_id, capture_op_id, program_number
            ) VALUES (
                @timestamp, @machine_id, @alarm_number, @alarm_type, @alarm_axis,
                @alarm_message, @capture_session_id, @capture_op_id, @program_number
            )
            """,
            ("@timestamp",          s.Timestamp.ToString("o")),
            ("@machine_id",         s.MachineId),
            ("@alarm_number",       s.AlarmNumber),
            ("@alarm_type",         s.AlarmType),
            ("@alarm_axis",         s.AlarmAxis),
            ("@alarm_message",      s.AlarmMessage),
            ("@capture_session_id", s.CaptureSessionId),
            ("@capture_op_id",      s.CaptureOpId),
            ("@program_number",     s.ProgramNumber)
        ).ExecuteNonQuery();
    }

    public void InsertParameterSnapshot(ParameterSnapshot s)
    {
        using var conn = Open();
        conn.CreateCommand("""
            INSERT INTO parameter_snapshots (
                timestamp, machine_id, param_number, axis, value, description
            ) VALUES (
                @timestamp, @machine_id, @param_number, @axis, @value, @description
            )
            """,
            ("@timestamp",   s.Timestamp.ToString("o")),
            ("@machine_id",  s.MachineId),
            ("@param_number",s.ParamNumber),
            ("@axis",        s.Axis),
            ("@value",       s.Value),
            ("@description", s.Description)
        ).ExecuteNonQuery();
    }

    public void InsertProgramDirectory(string machineId, Focas.PRGDIR2[] programs, int count)
    {
        using var conn = Open();
        var ts = DateTime.Now.ToString("o");
        foreach (var p in programs.Take(count))
        {
            InsertOneEntry(conn, ts, machineId, p.number, p.length, p.comment);
        }
    }

    public void InsertProgramDirectory(string machineId, Focas.PRGDIR3[] programs, int count)
    {
        using var conn = Open();
        var ts = DateTime.Now.ToString("o");
        foreach (var p in programs.Take(count))
        {
            InsertOneEntry(conn, ts, machineId, p.number, p.length, p.comment);
        }
    }

    /// <summary>Insert a single program_directory row (manages its own connection).</summary>
    public void InsertProgramDirectoryEntry(
        string machineId, int programNumber, int sizeBytes, string? comment)
    {
        using var conn = Open();
        InsertOneEntry(conn, DateTime.Now.ToString("o"), machineId, programNumber, sizeBytes, comment);
    }

    private static void InsertOneEntry(
        SqliteConnection conn,
        string timestamp,
        string machineId,
        int programNumber,
        int sizeBytes,
        string? comment)
    {
        conn.CreateCommand("""
            INSERT INTO program_directory (timestamp, machine_id, program_number, program_size_bytes, program_comment)
            VALUES (@timestamp, @machine_id, @program_number, @program_size_bytes, @program_comment)
            """,
            ("@timestamp",          timestamp),
            ("@machine_id",         machineId),
            ("@program_number",     programNumber),
            ("@program_size_bytes", sizeBytes),
            ("@program_comment",    comment?.Trim())
        ).ExecuteNonQuery();
    }

    // =====================================================================
    // QUERY HELPERS
    // =====================================================================

    /// <summary>Get last WCO values for a machine — used to detect changes</summary>
    public Dictionary<int, int[]> GetLastWcoValues(string machineId)
    {
        using var conn = Open();
        var result = new Dictionary<int, int[]>();
        using var cmd = conn.CreateCommand();
        cmd.CommandText = """
            SELECT wcs_number, offset_x, offset_y, offset_z, offset_a
            FROM wco_samples
            WHERE machine_id = @machine_id
              AND id IN (
                SELECT MAX(id) FROM wco_samples
                WHERE machine_id = @machine_id
                GROUP BY wcs_number
              )
            """;
        cmd.Parameters.AddWithValue("@machine_id", machineId);
        using var reader = cmd.ExecuteReader();
        while (reader.Read())
        {
            result[reader.GetInt32(0)] = new[]
            {
                reader.IsDBNull(1) ? 0 : reader.GetInt32(1),
                reader.IsDBNull(2) ? 0 : reader.GetInt32(2),
                reader.IsDBNull(3) ? 0 : reader.GetInt32(3),
                reader.IsDBNull(4) ? 0 : reader.GetInt32(4),
            };
        }
        return result;
    }

    /// <summary>Check if an alarm was already recorded (avoid duplicates)</summary>
    public bool AlarmAlreadyRecorded(string machineId, int alarmNumber, DateTime since)
    {
        using var conn = Open();
        using var cmd = conn.CreateCommand();
        cmd.CommandText = """
            SELECT COUNT(*) FROM alarm_history
            WHERE machine_id = @machine_id
              AND alarm_number = @alarm_number
              AND timestamp > @since
            """;
        cmd.Parameters.AddWithValue("@machine_id",   machineId);
        cmd.Parameters.AddWithValue("@alarm_number", alarmNumber);
        cmd.Parameters.AddWithValue("@since",        since.ToString("o"));
        return Convert.ToInt32(cmd.ExecuteScalar()) > 0;
    }

    // =====================================================================
    // HELPERS
    // =====================================================================

    private SqliteConnection Open()
    {
        var conn = new SqliteConnection(_connectionString);
        conn.Open();
        return conn;
    }

    public void Dispose() { }
}

// Extension to reduce boilerplate
file static class SqliteExtensions
{
    public static SqliteCommand CreateCommand(this SqliteConnection conn, string sql,
        params (string name, object? value)[] parameters)
    {
        var cmd = conn.CreateCommand();
        cmd.CommandText = sql;
        foreach (var (name, value) in parameters)
            cmd.Parameters.AddWithValue(name, value ?? DBNull.Value);
        return cmd;
    }
}

// =====================================================================
// DATA MODELS
// =====================================================================

public class MachineSample
{
    public DateTime Timestamp { get; set; }
    public string MachineId { get; set; } = "";
    public string? MachineName { get; set; }
    public bool Connected { get; set; }
    public string? ErrorMessage { get; set; }

    // System info
    public string? CncType { get; set; }
    public string? MtType { get; set; }
    public string? Series { get; set; }
    public string? SwVersion { get; set; }
    public int? MaxAxes { get; set; }
    public string? CncId { get; set; }

    // Mode
    public string? Mode { get; set; }
    public string? RunStatus { get; set; }
    public string? Motion { get; set; }
    public int? EditStatus { get; set; }
    public int? Warning { get; set; }

    // Program
    public int? ProgramNumber { get; set; }
    public int? MainProgram { get; set; }
    public int? SequenceNumber { get; set; }
    public int? BlockCount { get; set; }

    // Active block
    public string? ActiveBlockContent { get; set; }
    public string? CaptureSessionId { get; set; }
    public string? CaptureOpId { get; set; }
    public string? CaptureToolId { get; set; }

    // Speeds
    public int? SpindleSpeed { get; set; }
    public int? FeedRate { get; set; }
    public int? SpindleOverride { get; set; }
    public int? FeedrateOverride { get; set; }
    public int? SpindleLoad { get; set; }

    // Tooling
    public int? ToolNumber { get; set; }
    public int? ActiveWcs { get; set; }

    // Status
    public int? Emergency { get; set; }
    public int? Alarm { get; set; }
    public string? AlarmMessage { get; set; }

    // Positions — absolute
    public int? AxisX { get; set; }
    public int? AxisY { get; set; }
    public int? AxisZ { get; set; }
    public int? AxisA { get; set; }
    public int? AxisB { get; set; }

    // Positions — machine
    public int? MachX { get; set; }
    public int? MachY { get; set; }
    public int? MachZ { get; set; }

    // Distance to go
    public int? DtgX { get; set; }
    public int? DtgY { get; set; }
    public int? DtgZ { get; set; }

    // Servo loads
    public int? ServoLoadX { get; set; }
    public int? ServoLoadY { get; set; }
    public int? ServoLoadZ { get; set; }
    public int? ServoLoadA { get; set; }

    // Diagnosis counters
    public int? DiagPowerOnMin { get; set; }
    public int? DiagCuttingMin { get; set; }
    public int? DiagCycleMin { get; set; }

    // Tool life config
    public int? ToolLifeEnabled { get; set; }
    public string? ToolLifeType { get; set; }
}

public class ToolWearSample
{
    public DateTime Timestamp { get; set; }
    public string MachineId { get; set; } = "";
    public string? CaptureSessionId { get; set; }
    public string? CaptureOpId { get; set; }
    public int? ToolNumber { get; set; }
    public int OffsetNumber { get; set; }
    public int? LengthWear { get; set; }
    public int? DiameterWear { get; set; }
    public int? LengthGeometry { get; set; }
    public int? DiameterGeometry { get; set; }
}

public class ToolLifeSample
{
    public DateTime Timestamp { get; set; }
    public string MachineId { get; set; } = "";
    public int GroupNumber { get; set; }
    public int? ToolNumber { get; set; }
    public int? HOffset { get; set; }
    public int? DOffset { get; set; }
    public int? LifeLimit { get; set; }
    public int? LifeUsed { get; set; }
    public double? LifeRemainingPct { get; set; }
    public string? LifeType { get; set; }
    public string? Status { get; set; }
}

public class WcoSample
{
    public DateTime Timestamp { get; set; }
    public string MachineId { get; set; } = "";
    public int WcsNumber { get; set; }
    public string? WcsName { get; set; }
    public int? OffsetX { get; set; }
    public int? OffsetY { get; set; }
    public int? OffsetZ { get; set; }
    public int? OffsetA { get; set; }
    public bool Changed { get; set; }
}

public class AlarmHistorySample
{
    public DateTime Timestamp { get; set; }
    public string MachineId { get; set; } = "";
    public int? AlarmNumber { get; set; }
    public int? AlarmType { get; set; }
    public int? AlarmAxis { get; set; }
    public string? AlarmMessage { get; set; }
    public string? CaptureSessionId { get; set; }
    public string? CaptureOpId { get; set; }
    public int? ProgramNumber { get; set; }
}

public class ParameterSnapshot
{
    public DateTime Timestamp { get; set; }
    public string MachineId { get; set; } = "";
    public int ParamNumber { get; set; }
    public int Axis { get; set; }
    public int? Value { get; set; }
    public string? Description { get; set; }
}
