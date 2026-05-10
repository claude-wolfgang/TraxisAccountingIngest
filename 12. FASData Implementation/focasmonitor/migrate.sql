-- FocasMonitor migration: original → extended
-- Run once against existing monitoring.db before starting extended service
-- Safe to run multiple times (uses IF NOT EXISTS / IGNORE patterns)

PRAGMA journal_mode=WAL;

-- Add new columns to machine_samples
ALTER TABLE machine_samples ADD COLUMN cnc_type TEXT;
ALTER TABLE machine_samples ADD COLUMN mt_type TEXT;
ALTER TABLE machine_samples ADD COLUMN series TEXT;
ALTER TABLE machine_samples ADD COLUMN sw_version TEXT;
ALTER TABLE machine_samples ADD COLUMN max_axes INTEGER;
ALTER TABLE machine_samples ADD COLUMN cnc_id TEXT;
ALTER TABLE machine_samples ADD COLUMN sequence_number INTEGER;
ALTER TABLE machine_samples ADD COLUMN block_count INTEGER;
ALTER TABLE machine_samples ADD COLUMN active_block_content TEXT;
ALTER TABLE machine_samples ADD COLUMN capture_session_id TEXT;
ALTER TABLE machine_samples ADD COLUMN capture_op_id TEXT;
ALTER TABLE machine_samples ADD COLUMN capture_tool_id TEXT;
ALTER TABLE machine_samples ADD COLUMN spindle_load INTEGER;
ALTER TABLE machine_samples ADD COLUMN tool_number INTEGER;
ALTER TABLE machine_samples ADD COLUMN active_wcs INTEGER;
ALTER TABLE machine_samples ADD COLUMN edit_status INTEGER;
ALTER TABLE machine_samples ADD COLUMN warning INTEGER;
ALTER TABLE machine_samples ADD COLUMN axis_a INTEGER;
ALTER TABLE machine_samples ADD COLUMN axis_b INTEGER;
ALTER TABLE machine_samples ADD COLUMN mach_x INTEGER;
ALTER TABLE machine_samples ADD COLUMN mach_y INTEGER;
ALTER TABLE machine_samples ADD COLUMN mach_z INTEGER;
ALTER TABLE machine_samples ADD COLUMN dtg_x INTEGER;
ALTER TABLE machine_samples ADD COLUMN dtg_y INTEGER;
ALTER TABLE machine_samples ADD COLUMN dtg_z INTEGER;
ALTER TABLE machine_samples ADD COLUMN servo_load_x INTEGER;
ALTER TABLE machine_samples ADD COLUMN servo_load_y INTEGER;
ALTER TABLE machine_samples ADD COLUMN servo_load_z INTEGER;
ALTER TABLE machine_samples ADD COLUMN servo_load_a INTEGER;
ALTER TABLE machine_samples ADD COLUMN diag_power_on_min INTEGER;
ALTER TABLE machine_samples ADD COLUMN diag_cutting_min INTEGER;
ALTER TABLE machine_samples ADD COLUMN diag_cycle_min INTEGER;
ALTER TABLE machine_samples ADD COLUMN tool_life_enabled INTEGER;
ALTER TABLE machine_samples ADD COLUMN tool_life_type TEXT;

-- New indexes on machine_samples
CREATE INDEX IF NOT EXISTS idx_ms_session ON machine_samples(capture_session_id)
    WHERE capture_session_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_ms_program ON machine_samples(machine_id, program_number)
    WHERE program_number IS NOT NULL;

-- New tables (same as Database.cs Initialize())
CREATE TABLE IF NOT EXISTS tool_wear_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    machine_id TEXT NOT NULL,
    capture_session_id TEXT,
    capture_op_id TEXT,
    tool_number INTEGER,
    offset_number INTEGER,
    length_wear INTEGER,
    diameter_wear INTEGER,
    length_geometry INTEGER,
    diameter_geometry INTEGER
);
CREATE INDEX IF NOT EXISTS idx_tw_machine   ON tool_wear_samples(machine_id);
CREATE INDEX IF NOT EXISTS idx_tw_timestamp ON tool_wear_samples(timestamp);
CREATE INDEX IF NOT EXISTS idx_tw_session   ON tool_wear_samples(capture_session_id)
    WHERE capture_session_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_tw_tool      ON tool_wear_samples(machine_id, tool_number);

CREATE TABLE IF NOT EXISTS tool_life_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    machine_id TEXT NOT NULL,
    group_number INTEGER,
    tool_number INTEGER,
    h_offset INTEGER,
    d_offset INTEGER,
    life_limit INTEGER,
    life_used INTEGER,
    life_remaining_pct REAL,
    life_type TEXT,
    status TEXT
);
CREATE INDEX IF NOT EXISTS idx_tl_machine   ON tool_life_samples(machine_id);
CREATE INDEX IF NOT EXISTS idx_tl_timestamp ON tool_life_samples(timestamp);
CREATE INDEX IF NOT EXISTS idx_tl_tool      ON tool_life_samples(machine_id, tool_number);

CREATE TABLE IF NOT EXISTS wco_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    machine_id TEXT NOT NULL,
    wcs_number INTEGER,
    wcs_name TEXT,
    offset_x INTEGER,
    offset_y INTEGER,
    offset_z INTEGER,
    offset_a INTEGER,
    changed INTEGER
);
CREATE INDEX IF NOT EXISTS idx_wco_machine   ON wco_samples(machine_id);
CREATE INDEX IF NOT EXISTS idx_wco_timestamp ON wco_samples(timestamp);

CREATE TABLE IF NOT EXISTS parameter_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    machine_id TEXT NOT NULL,
    param_number INTEGER,
    axis INTEGER,
    value INTEGER,
    description TEXT
);
CREATE INDEX IF NOT EXISTS idx_ps_machine ON parameter_snapshots(machine_id);
CREATE INDEX IF NOT EXISTS idx_ps_param   ON parameter_snapshots(machine_id, param_number);

CREATE TABLE IF NOT EXISTS alarm_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    machine_id TEXT NOT NULL,
    alarm_number INTEGER,
    alarm_type INTEGER,
    alarm_axis INTEGER,
    alarm_message TEXT,
    capture_session_id TEXT,
    capture_op_id TEXT,
    program_number INTEGER
);
CREATE INDEX IF NOT EXISTS idx_ah_machine   ON alarm_history(machine_id);
CREATE INDEX IF NOT EXISTS idx_ah_timestamp ON alarm_history(timestamp);
CREATE INDEX IF NOT EXISTS idx_ah_session   ON alarm_history(capture_session_id)
    WHERE capture_session_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS program_directory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    machine_id TEXT NOT NULL,
    program_number INTEGER,
    program_size_bytes INTEGER,
    program_comment TEXT
);
CREATE INDEX IF NOT EXISTS idx_pd_machine  ON program_directory(machine_id);
CREATE INDEX IF NOT EXISTS idx_pd_program  ON program_directory(machine_id, program_number);
