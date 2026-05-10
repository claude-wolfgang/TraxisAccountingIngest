using Microsoft.Data.Sqlite;

namespace FocasMonitor;

public class Database : IDisposable
{
    private readonly string _connectionString;
    private SqliteConnection? _connection;

    public Database(string dbPath)
    {
        // Ensure directory exists
        var dir = Path.GetDirectoryName(dbPath);
        if (!string.IsNullOrEmpty(dir) && !Directory.Exists(dir))
        {
            Directory.CreateDirectory(dir);
        }

        _connectionString = $"Data Source={dbPath}";
        Initialize();
    }

    private void Initialize()
    {
        using var conn = new SqliteConnection(_connectionString);
        conn.Open();

        var cmd = conn.CreateCommand();
        cmd.CommandText = @"
            CREATE TABLE IF NOT EXISTS machine_samples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                machine_id TEXT NOT NULL,
                machine_name TEXT,
                
                -- Connection status
                connected INTEGER NOT NULL,
                error_message TEXT,
                
                -- Operating mode
                mode TEXT,
                run_status TEXT,
                motion TEXT,
                
                -- Program info
                program_number INTEGER,
                main_program INTEGER,
                
                -- Speeds
                spindle_speed INTEGER,
                feed_rate INTEGER,
                
                -- Overrides (percentage)
                spindle_override INTEGER,
                feedrate_override INTEGER,
                
                -- Status flags
                emergency INTEGER,
                alarm INTEGER,
                alarm_message TEXT,
                
                -- Axis positions (stored as integers, divide by 1000 for mm)
                axis_x INTEGER,
                axis_y INTEGER,
                axis_z INTEGER
            );
            
            CREATE INDEX IF NOT EXISTS idx_timestamp ON machine_samples(timestamp);
            CREATE INDEX IF NOT EXISTS idx_machine ON machine_samples(machine_id);
            CREATE INDEX IF NOT EXISTS idx_machine_time ON machine_samples(machine_id, timestamp);
        ";
        cmd.ExecuteNonQuery();

        // Migration: add program_comment column if missing
        try
        {
            var migCmd = conn.CreateCommand();
            migCmd.CommandText = "ALTER TABLE machine_samples ADD COLUMN program_comment TEXT";
            migCmd.ExecuteNonQuery();
        }
        catch (SqliteException) { /* column already exists */ }
    }

    public void InsertSample(MachineSample sample)
    {
        using var conn = new SqliteConnection(_connectionString);
        conn.Open();

        var cmd = conn.CreateCommand();
        cmd.CommandText = @"
            INSERT INTO machine_samples (
                timestamp, machine_id, machine_name, connected, error_message,
                mode, run_status, motion, program_number, main_program,
                spindle_speed, feed_rate, spindle_override, feedrate_override,
                emergency, alarm, alarm_message, axis_x, axis_y, axis_z,
                program_comment
            ) VALUES (
                @timestamp, @machine_id, @machine_name, @connected, @error_message,
                @mode, @run_status, @motion, @program_number, @main_program,
                @spindle_speed, @feed_rate, @spindle_override, @feedrate_override,
                @emergency, @alarm, @alarm_message, @axis_x, @axis_y, @axis_z,
                @program_comment
            )";

        cmd.Parameters.AddWithValue("@timestamp", sample.Timestamp.ToString("o"));
        cmd.Parameters.AddWithValue("@machine_id", sample.MachineId);
        cmd.Parameters.AddWithValue("@machine_name", sample.MachineName ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@connected", sample.Connected ? 1 : 0);
        cmd.Parameters.AddWithValue("@error_message", sample.ErrorMessage ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@mode", sample.Mode ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@run_status", sample.RunStatus ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@motion", sample.Motion ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@program_number", sample.ProgramNumber ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@main_program", sample.MainProgram ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@spindle_speed", sample.SpindleSpeed ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@feed_rate", sample.FeedRate ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@spindle_override", sample.SpindleOverride ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@feedrate_override", sample.FeedrateOverride ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@emergency", sample.Emergency ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@alarm", sample.Alarm ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@alarm_message", sample.AlarmMessage ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@axis_x", sample.AxisX ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@axis_y", sample.AxisY ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@axis_z", sample.AxisZ ?? (object)DBNull.Value);
        cmd.Parameters.AddWithValue("@program_comment", sample.ProgramComment ?? (object)DBNull.Value);

        cmd.ExecuteNonQuery();
    }

    public void Dispose()
    {
        _connection?.Dispose();
    }
}

public class MachineSample
{
    public DateTime Timestamp { get; set; }
    public string MachineId { get; set; } = "";
    public string? MachineName { get; set; }
    public bool Connected { get; set; }
    public string? ErrorMessage { get; set; }
    public string? Mode { get; set; }
    public string? RunStatus { get; set; }
    public string? Motion { get; set; }
    public int? ProgramNumber { get; set; }
    public int? MainProgram { get; set; }
    public int? SpindleSpeed { get; set; }
    public int? FeedRate { get; set; }
    public int? SpindleOverride { get; set; }
    public int? FeedrateOverride { get; set; }
    public int? Emergency { get; set; }
    public int? Alarm { get; set; }
    public string? AlarmMessage { get; set; }
    public int? AxisX { get; set; }
    public int? AxisY { get; set; }
    public int? AxisZ { get; set; }
    public string? ProgramComment { get; set; }
}
