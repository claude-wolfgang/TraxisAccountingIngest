using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using System.Text.Json;

namespace FocasMonitor;

public class MonitoringService : BackgroundService
{
    private readonly ILogger<MonitoringService> _logger;
    private readonly Config _config;
    private readonly Database _db;

    // Track previous alarm state per machine to detect new alarms
    private readonly Dictionary<string, int> _lastAlarmState = new();

    // Track previous WCO values per machine to detect changes
    private readonly Dictionary<string, Dictionary<int, int[]>> _lastWcoValues = new();

    // Slow poll counter — some data doesn't need every 60s
    private int _pollCount = 0;

    // Diagnostic counters — log raw bytes for first N polls per machine per function
    private readonly Dictionary<string, int> _diagCounters = new();

    // Key parameters to snapshot (number → description)
    private static readonly Dictionary<short, string> ParametersToCapture = new()
    {
        { 6800, "Tool life management enable/config" },
        { 6801, "Tool life type (0=count, 1=time)" },
        { 6813, "Max tool groups (0i-MF)" },
        { 1020, "Axis name assignment" },
        { 1022, "Axis type (linear/rotary)" },
        { 1401, "Feed clamp / override config" },
        { 1422, "Max cutting feedrate" },
        { 3111, "Display options" },
    };

    public MonitoringService(ILogger<MonitoringService> logger)
    {
        _logger = logger;
        _config = LoadConfig();
        _db = new Database(_config.DatabasePath);
    }

    private static Config LoadConfig()
    {
        var configPath = Path.Combine(AppContext.BaseDirectory, "machines.json");
        if (!File.Exists(configPath))
            throw new FileNotFoundException($"Configuration file not found: {configPath}");
        var json = File.ReadAllText(configPath);
        var options = new JsonSerializerOptions { PropertyNameCaseInsensitive = true };
        return JsonSerializer.Deserialize<Config>(json, options) ?? throw new Exception("Failed to parse config");
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        _logger.LogInformation("FOCAS Monitoring Service started (extended)");
        _logger.LogInformation("Database: {Path}", _config.DatabasePath);
        _logger.LogInformation("Poll interval: {Interval}s", _config.PollIntervalSeconds);
        _logger.LogInformation("Machines enabled: {Count}", _config.Machines.Count(m => m.Enabled));

        // Initialize WCO tracking from DB
        foreach (var machine in _config.Machines.Where(m => m.Enabled))
            _lastWcoValues[machine.Id] = _db.GetLastWcoValues(machine.Id);

        while (!stoppingToken.IsCancellationRequested)
        {
            var pollStart = DateTime.Now;
            _pollCount++;

            foreach (var machine in _config.Machines.Where(m => m.Enabled && !string.IsNullOrEmpty(m.Ip)))
            {
                try
                {
                    PollMachine(machine);
                }
                catch (Exception ex)
                {
                    _logger.LogError(ex, "Unhandled error polling {Id}", machine.Id);
                    _db.InsertSample(new MachineSample
                    {
                        Timestamp = DateTime.Now,
                        MachineId = machine.Id,
                        MachineName = machine.Name,
                        Connected = false,
                        ErrorMessage = ex.Message
                    });
                }
            }

            var elapsed = DateTime.Now - pollStart;
            _logger.LogInformation("Poll #{Count} complete in {Ms}ms", _pollCount, (int)elapsed.TotalMilliseconds);

            var delay = TimeSpan.FromSeconds(_config.PollIntervalSeconds) - elapsed;
            if (delay > TimeSpan.Zero)
                await Task.Delay(delay, stoppingToken);
        }
    }

    private void PollMachine(MachineConfig machine)
    {
        var sample = new MachineSample
        {
            Timestamp = DateTime.Now,
            MachineId = machine.Id,
            MachineName = machine.Name
        };

        ushort handle = 0;
        try
        {
            // Connect
            short ret = Focas.cnc_allclibhndl3(machine.Ip, (ushort)machine.Port, 3, out handle);
            if (ret != 0)
            {
                sample.Connected = false;
                sample.ErrorMessage = $"Connection failed (error {ret})";
                _db.InsertSample(sample);
                return;
            }
            sample.Connected = true;

            // ----------------------------------------------------------------
            // SYSTEM INFO
            // ----------------------------------------------------------------
            try
            {
                if (Focas.cnc_sysinfo(handle, out var sysinfo) == 0)
                {
                    sample.CncType  = sysinfo.cnc_type?.Trim();
                    sample.MtType   = sysinfo.mt_type?.Trim();
                    sample.Series   = sysinfo.series?.Trim();
                    sample.SwVersion= sysinfo.version?.Trim();
                    sample.MaxAxes  = sysinfo.max_axis;
                }
            }
            catch (Exception) { }

            try
            {
                var cncid = new uint[4];
                if (Focas.cnc_rdcncid(handle, cncid) == 0)
                    sample.CncId = string.Join("-", cncid.Select(x => x.ToString("X8")));
            }
            catch (Exception) { }

            // ----------------------------------------------------------------
            // STATUS
            // ----------------------------------------------------------------
            try
            {
                if (Focas.cnc_statinfo(handle, out var status) == 0)
                {
                    sample.Mode       = Focas.GetModeString(status.aut);
                    sample.RunStatus  = Focas.GetRunStatusString(status.run);
                    sample.Motion     = Focas.GetMotionString(status.motion);
                    sample.EditStatus = status.edit;
                    sample.Emergency  = status.emergency;
                    sample.Alarm      = status.alarm;
                }
            }
            catch (Exception) { }

            try
            {
                if (Focas.cnc_statinfo2(handle, out var status2) == 0)
                    sample.Warning = status2.warning;
            }
            catch (Exception) { }

            // ----------------------------------------------------------------
            // PROGRAM
            // ----------------------------------------------------------------
            try
            {
                if (Focas.cnc_rdprgnum(handle, out var prgnum) == 0)
                {
                    sample.ProgramNumber = prgnum.data;
                    sample.MainProgram   = prgnum.mdata;
                }
            }
            catch (Exception) { }

            try
            {
                if (Focas.cnc_rdseqnum(handle, out var seqnum) == 0)
                    sample.SequenceNumber = seqnum.data;
            }
            catch (Exception) { }

            try
            {
                if (Focas.cnc_rdblkcount(handle, out int blkcount) == 0)
                    sample.BlockCount = blkcount;
            }
            catch (Exception) { }

            // ----------------------------------------------------------------
            // ACTIVE BLOCK — capture tag parsing
            // ----------------------------------------------------------------
            try
            {
                var blockContent = Focas.ReadActiveBlockComment(handle);
                if (blockContent != null)
                {
                    sample.ActiveBlockContent = blockContent;
                    var tags = Focas.ParseCaptureTags(blockContent);
                    if (tags != null)
                    {
                        tags.TryGetValue("SESSION",  out var sessionId);
                        tags.TryGetValue("OP_ID",    out var opId);
                        tags.TryGetValue("TOOL_ID",  out var toolId);
                        sample.CaptureSessionId = sessionId;
                        sample.CaptureOpId      = opId;
                        sample.CaptureToolId    = toolId;
                    }
                }
            }
            catch (Exception) { }

            // ----------------------------------------------------------------
            // SPEEDS AND OVERRIDES
            // ----------------------------------------------------------------
            try
            {
                if (Focas.cnc_rdspeed(handle, -1, out var speed) == 0)
                {
                    sample.SpindleSpeed = speed.acts.data;
                    sample.FeedRate     = speed.actf.data;
                }
            }
            catch (Exception) { }

            try
            {
                var diagKey = machine.Id + "_spl";
                bool shouldDiag = _diagCounters.GetValueOrDefault(diagKey, 0) < 3;

                // Try cnc_rdspmeter first (type=0 = load, returns LOADELM per spindle)
                short spCount = 4;
                var spBuf = new byte[128];
                short spmRet = Focas.cnc_rdspmeter_raw(handle, 0, ref spCount, spBuf);

                if (shouldDiag)
                {
                    var hex = BitConverter.ToString(spBuf, 0, 48);
                    File.AppendAllText(@"C:\FASData\diag_spindle.log",
                        $"[{DateTime.Now:HH:mm:ss}] {machine.Id} rdspmeter: ret={spmRet} count={spCount} raw=[{hex}]{Environment.NewLine}");
                }

                if (spmRet == 0 && spCount > 0)
                {
                    // LOADELM: int data(4) + short dec(2) + short unit(2) + byte name(1) + 3 reserve
                    int rawLoad = BitConverter.ToInt32(spBuf, 0);
                    short dec = BitConverter.ToInt16(spBuf, 4);
                    if (dec > 0)
                        sample.SpindleLoad = (int)Math.Round(rawLoad / Math.Pow(10, dec));
                    else
                        sample.SpindleLoad = rawLoad;
                }
                else
                {
                    // Fallback: try cnc_rdspload
                    var splBuf = new byte[64];
                    short splRet = Focas.cnc_rdspload_raw(handle, 0, splBuf);

                    if (shouldDiag)
                    {
                        var hex2 = BitConverter.ToString(splBuf, 0, 24);
                        File.AppendAllText(@"C:\FASData\diag_spindle.log",
                            $"[{DateTime.Now:HH:mm:ss}] {machine.Id} rdspload fallback: ret={splRet} raw=[{hex2}]{Environment.NewLine}");
                    }

                    if (splRet == 0)
                        sample.SpindleLoad = BitConverter.ToInt16(splBuf, 4);
                }

                if (shouldDiag)
                    _diagCounters[diagKey] = _diagCounters.GetValueOrDefault(diagKey, 0) + 1;
            }
            catch (Exception ex)
            {
                File.AppendAllText(@"C:\FASData\diag_spindle.log",
                    $"[{DateTime.Now:HH:mm:ss}] {machine.Id} EXCEPTION: {ex.Message}{Environment.NewLine}");
            }

            // ----------------------------------------------------------------
            // CURRENT TOOL — try cnc_rdtool first, fall back to macro #4120
            // (cnc_rdtool requires optional Tool Management software;
            //  macro #4120 is the modal T code, available on all Fanuc controls)
            // ----------------------------------------------------------------
            try
            {
                if (Focas.cnc_rdtool(handle, out var tool) == 0)
                    sample.ToolNumber = tool.tool_no;
            }
            catch (Exception) { }

            if (sample.ToolNumber == null && machine.ToolPmcAddr >= 0)
            {
                try
                {
                    // Read current tool from PMC D-table at configured address (16-bit word)
                    short addr = (short)machine.ToolPmcAddr;
                    var buf = new byte[8 + 2];
                    if (Focas.pmc_rdpmcrng(handle, 9, 0, addr, (short)(addr + 1), 8 + 2, buf) == 0)
                    {
                        int toolNum = BitConverter.ToInt16(buf, 8);
                        if (toolNum > 0)
                            sample.ToolNumber = toolNum;
                    }
                }
                catch (Exception) { }
            }

            // ----------------------------------------------------------------
            // AXIS POSITIONS (length = 4 + 4 * MAX_AXIS, MAX_AXIS=32)
            // ----------------------------------------------------------------
            const short posLen = 4 + 4 * 32; // 132

            try
            {
                if (Focas.cnc_absolute2(handle, -1, posLen, out var absPos) == 0
                    && absPos.data != null)
                {
                    if (absPos.data.Length > 0) sample.AxisX = absPos.data[0];
                    if (absPos.data.Length > 1) sample.AxisY = absPos.data[1];
                    if (absPos.data.Length > 2) sample.AxisZ = absPos.data[2];
                    if (absPos.data.Length > 3) sample.AxisA = absPos.data[3];
                    if (absPos.data.Length > 4) sample.AxisB = absPos.data[4];
                }
            }
            catch (Exception) { }

            // cnc_machine2 and cnc_distance2 return error 4/−7 on all machines — disabled
            // Machine coordinates and distance-to-go not available on these controllers

            // ----------------------------------------------------------------
            // SERVO LOADS — use raw buffer (struct marshaling didn't work)
            // Each LOADELM is 12 bytes: int data(4) + short dec(2) + short unit(2) + byte name(1) + 3 reserve
            // ----------------------------------------------------------------
            try
            {
                short axisCount = 4;
                var svBuf = new byte[128];
                if (Focas.cnc_rdsvmeter_raw(handle, ref axisCount, svBuf) == 0 && axisCount > 0)
                {
                    for (int i = 0; i < axisCount && i < 4; i++)
                    {
                        int offset = i * 12;
                        int loadVal = BitConverter.ToInt32(svBuf, offset);
                        byte axisName = svBuf[offset + 8];

                        switch ((char)axisName)
                        {
                            case 'X': sample.ServoLoadX = loadVal; break;
                            case 'Y': sample.ServoLoadY = loadVal; break;
                            case 'Z': sample.ServoLoadZ = loadVal; break;
                            case 'A': sample.ServoLoadA = loadVal; break;
                            default:
                                if (i == 0 && sample.ServoLoadX == null) sample.ServoLoadX = loadVal;
                                else if (i == 1 && sample.ServoLoadY == null) sample.ServoLoadY = loadVal;
                                else if (i == 2 && sample.ServoLoadZ == null) sample.ServoLoadZ = loadVal;
                                break;
                        }
                    }
                }
            }
            catch (Exception) { }

            // ----------------------------------------------------------------
            // ALARMS
            // ----------------------------------------------------------------
            try
            {
                if (Focas.cnc_alarm(handle, out var alm) == 0)
                {
                    sample.Alarm = alm.data;

                    if (alm.data != 0)
                    {
                        short almCount = 10;
                        var almMsgs = new Focas.ODBALMMSG[10];
                        if (Focas.cnc_rdalmmsg(handle, -1, ref almCount, almMsgs) == 0 && almCount > 0)
                        {
                            sample.AlarmMessage = almMsgs[0].alm_msg?.Trim();

                            foreach (var msg in almMsgs.Take(almCount))
                            {
                                if (!_db.AlarmAlreadyRecorded(machine.Id, msg.alm_no,
                                        DateTime.Now.AddMinutes(-5)))
                                {
                                    _db.InsertAlarmHistory(new AlarmHistorySample
                                    {
                                        Timestamp        = sample.Timestamp,
                                        MachineId        = machine.Id,
                                        AlarmNumber      = msg.alm_no,
                                        AlarmType        = msg.type,
                                        AlarmAxis        = msg.axis,
                                        AlarmMessage     = msg.alm_msg?.Trim(),
                                        CaptureSessionId = sample.CaptureSessionId,
                                        CaptureOpId      = sample.CaptureOpId,
                                        ProgramNumber    = sample.ProgramNumber
                                    });
                                }
                            }
                        }
                    }
                }
            }
            catch (Exception) { }

            // ----------------------------------------------------------------
            // DIAGNOSIS COUNTERS + TOOL LIFE CONFIG
            // (cnc_diagnoss returns EW_FUNC on all machines — values will be null)
            // ----------------------------------------------------------------
            sample.DiagPowerOnMin = Focas.ReadDiagnosis(handle, 300);
            sample.DiagCuttingMin = Focas.ReadDiagnosis(handle, 301);
            sample.DiagCycleMin   = Focas.ReadDiagnosis(handle, 302);

            var p6800 = Focas.ReadParameter(handle, 6800);
            if (p6800.HasValue)
            {
                sample.ToolLifeEnabled = p6800.Value & 0x01;
                sample.ToolLifeType    = (p6800.Value & 0x02) != 0 ? "time" : "count";
            }

            // Write main sample
            _db.InsertSample(sample);

            // ----------------------------------------------------------------
            // POST-INSERT: Tool wear, tool life, WCO, parameters, programs
            // (each has own try-catch, uses functions confirmed in DLL)
            // ----------------------------------------------------------------
            if (sample.RunStatus == "STRT" || sample.RunStatus == "MSTR")
            {
                ReadToolWearRegisters(handle, machine.Id,
                    sample.CaptureSessionId, sample.CaptureOpId, sample.ToolNumber);
            }

            if (sample.ToolLifeEnabled == 1)
                ReadToolLifeData(handle, machine.Id, sample.ToolLifeType ?? "count");

            // WCO disabled — cnc_rdwkcofs not in this DLL
            // ReadWorkCoordinates(handle, machine.Id);

            if (_pollCount % 10 == 1)
            {
                ReadParameters(handle, machine.Id);
                ReadProgramDirectory(handle, machine.Id);
            }

            _logger.LogDebug("{Id}: {Status} | T{Tool} | S{RPM} | F{Feed} | X{X} | Load{Load}%",
                machine.Id, sample.RunStatus, sample.ToolNumber, sample.SpindleSpeed,
                sample.FeedRate, sample.AxisX, sample.SpindleLoad);

}
        finally
        {
            if (handle != 0)
                Focas.cnc_freelibhndl(handle);
        }
    }

    // ----------------------------------------------------------------
    // STRUCT DIAGNOSTICS — run once to discover actual DLL struct layouts
    // ----------------------------------------------------------------
    private void RunStructDiagnostics(ushort handle, string machineId)
    {
        _logger.LogInformation("=== STRUCT DIAGNOSTICS for {Id} ===", machineId);

        var tests = new (string name, Func<byte[], short> call, int bufSize)[]
        {
            ("cnc_statinfo (ODBST)",      buf => Focas.cnc_statinfo_raw(handle, buf), 64),
            ("cnc_statinfo2 (ODBST2)",    buf => Focas.cnc_statinfo2_raw(handle, buf), 64),
            ("cnc_rdprgnum (ODBPRO)",     buf => Focas.cnc_rdprgnum_raw(handle, buf), 64),
            ("cnc_rdseqnum (ODBSEQ)",     buf => Focas.cnc_rdseqnum_raw(handle, buf), 64),
            ("cnc_rdblkcount",            buf => Focas.cnc_rdblkcount_raw(handle, buf), 64),
            ("cnc_rdspeed (ODBSPEED)",    buf => Focas.cnc_rdspeed_raw(handle, -1, buf), 128),
            ("cnc_rdspload (ODBSPLOAD)",  buf => Focas.cnc_rdspload_raw(handle, 0, buf), 128),
            ("cnc_rdtool (ODBTOOL)",      buf => Focas.cnc_rdtool_raw(handle, buf), 64),
            ("cnc_absolute2 len=36",      buf => Focas.cnc_absolute2_raw(handle, -1, 36, buf), 128),
            ("cnc_absolute2 len=72",      buf => Focas.cnc_absolute2_raw(handle, -1, 72, buf), 128),
            ("cnc_machine2 len=36",       buf => Focas.cnc_machine2_raw(handle, -1, 36, buf), 128),
            ("cnc_distance2 len=36",      buf => Focas.cnc_distance2_raw(handle, -1, 36, buf), 128),
            ("cnc_alarm (ODBALM)",        buf => Focas.cnc_alarm_raw(handle, buf), 64),
        };

        foreach (var (name, call, bufSize) in tests)
        {
            try
            {
                var buf = new byte[bufSize];
                short ret = call(buf);

                // Find last non-zero byte to determine actual struct size
                int lastNonZero = 0;
                for (int i = buf.Length - 1; i >= 0; i--)
                {
                    if (buf[i] != 0) { lastNonZero = i + 1; break; }
                }

                var hex = BitConverter.ToString(buf, 0, Math.Min(lastNonZero + 4, bufSize));
                _logger.LogInformation("{Name}: ret={Ret} size~={Size} hex=[{Hex}]",
                    name, ret, lastNonZero, hex);
            }
            catch (EntryPointNotFoundException)
            {
                _logger.LogInformation("{Name}: NOT IN DLL", name);
            }
            catch (Exception ex)
            {
                _logger.LogInformation("{Name}: EXCEPTION {Ex}", name, ex.Message);
            }
        }

        // Servo meter — special because it takes ref param
        try
        {
            var buf = new byte[128];
            short num = 4;
            short ret = Focas.cnc_rdsvmeter_raw(handle, ref num, buf);
            int lastNonZero = 0;
            for (int i = buf.Length - 1; i >= 0; i--)
            {
                if (buf[i] != 0) { lastNonZero = i + 1; break; }
            }
            var hex = BitConverter.ToString(buf, 0, Math.Min(lastNonZero + 4, 128));
            _logger.LogInformation("cnc_rdsvmeter (n={Num}): ret={Ret} size~={Size} hex=[{Hex}]",
                num, ret, lastNonZero, hex);
        }
        catch (EntryPointNotFoundException) { _logger.LogInformation("cnc_rdsvmeter: NOT IN DLL"); }
        catch (Exception ex) { _logger.LogInformation("cnc_rdsvmeter: EXCEPTION {Ex}", ex.Message); }

        // Alarm messages
        try
        {
            var buf = new byte[512];
            short num = 1;
            short ret = Focas.cnc_rdalmmsg_raw(handle, -1, ref num, buf);
            int lastNonZero = 0;
            for (int i = buf.Length - 1; i >= 0; i--)
            {
                if (buf[i] != 0) { lastNonZero = i + 1; break; }
            }
            var hex = BitConverter.ToString(buf, 0, Math.Min(lastNonZero + 4, 512));
            _logger.LogInformation("cnc_rdalmmsg (n={Num}): ret={Ret} size~={Size} hex=[{Hex}]",
                num, ret, lastNonZero, hex);
        }
        catch (EntryPointNotFoundException) { _logger.LogInformation("cnc_rdalmmsg: NOT IN DLL"); }
        catch (Exception ex) { _logger.LogInformation("cnc_rdalmmsg: EXCEPTION {Ex}", ex.Message); }

        _logger.LogInformation("=== END DIAGNOSTICS ===");
    }

    // ----------------------------------------------------------------
    // TOOL WEAR REGISTERS
    // ----------------------------------------------------------------
    private void ReadToolWearRegisters(ushort handle, string machineId,
        string? sessionId, string? opId, int? currentTool)
    {
        try
        {
            if (Focas.cnc_rdtofsinfo(handle, out var info) != 0) return;

            short count = (short)Math.Min((int)info.use_no, 64);
            var tofs = new Focas.ODBTOFS[count];

            // type: 0=geometry+wear length, 1=geometry+wear diameter
            // Read all offsets — type -1 or iterate
            if (Focas.cnc_rdtofs(handle, 1, count, 0, tofs) == 0)
            {
                var ts = DateTime.Now;
                foreach (var tof in tofs.Take(count))
                {
                    _db.InsertToolWearSample(new ToolWearSample
                    {
                        Timestamp        = ts,
                        MachineId        = machineId,
                        CaptureSessionId = sessionId,
                        CaptureOpId      = opId,
                        ToolNumber       = currentTool,
                        OffsetNumber     = tof.number,
                        LengthWear       = tof.data?.Length > 0 ? tof.data[0] : null,
                        DiameterWear     = tof.data?.Length > 1 ? tof.data[1] : null,
                        LengthGeometry   = tof.data?.Length > 2 ? tof.data[2] : null,
                        DiameterGeometry = tof.data?.Length > 3 ? tof.data[3] : null,
                    });
                }
            }
        }
        catch (Exception ex)
        {
            _logger.LogDebug("Tool wear read failed for {Id}: {Ex}", machineId, ex.Message);
        }
    }

    // ----------------------------------------------------------------
    // TOOL LIFE DATA
    // ----------------------------------------------------------------
    private void ReadToolLifeData(ushort handle, string machineId, string lifeType)
    {
        try
        {
            if (Focas.cnc_rdtlinfo(handle, out var tlinfo) != 0) return;

            var ts = DateTime.Now;
            for (short grp = 1; grp <= tlinfo.use_grp; grp++)
            {
                if (Focas.cnc_rdtlife(handle, grp, out var tlife) != 0) continue;

                double remainingPct = tlife.life > 0
                    ? Math.Round(100.0 * (tlife.life - tlife.count) / tlife.life, 1)
                    : 0;

                // Read individual tools in group
                for (short t = 0; t < tlinfo.max_tool; t++)
                {
                    if (Focas.cnc_rdtlifd(handle, grp, t, out var tlifd) != 0) continue;
                    if (tlifd.tool_no == 0) continue; // empty slot

                    _db.InsertToolLifeSample(new ToolLifeSample
                    {
                        Timestamp        = ts,
                        MachineId        = machineId,
                        GroupNumber      = grp,
                        ToolNumber       = tlifd.tool_no,
                        HOffset          = tlifd.h_code,
                        DOffset          = tlifd.d_code,
                        LifeLimit        = tlife.life,
                        LifeUsed         = tlife.count,
                        LifeRemainingPct = remainingPct,
                        LifeType         = lifeType,
                        Status           = tlifd.status switch
                        {
                            0 => "available",
                            1 => "used",
                            2 => "expired",
                            _ => $"unknown({tlifd.status})"
                        }
                    });
                }
            }
        }
        catch (Exception ex)
        {
            _logger.LogDebug("Tool life read failed for {Id}: {Ex}", machineId, ex.Message);
        }
    }

    // ----------------------------------------------------------------
    // WORK COORDINATE OFFSETS
    // ----------------------------------------------------------------
    private void ReadWorkCoordinates(ushort handle, string machineId)
    {
        try
        {
            var ts = DateTime.Now;
            var wcoData = new Focas.ODBWKOFS[6];

            if (Focas.cnc_rdwkcofs(handle, 0, 1, 6, wcoData) != 0) return;

            if (!_lastWcoValues.ContainsKey(machineId))
                _lastWcoValues[machineId] = new Dictionary<int, int[]>();

            var wcsNames = new[] { "", "G54", "G55", "G56", "G57", "G58", "G59" };

            for (int i = 0; i < 6; i++)
            {
                var wco = wcoData[i];
                int wcsNum = i + 1;
                var current = new[] {
                    wco.data?.Length > 0 ? wco.data[0] : 0,
                    wco.data?.Length > 1 ? wco.data[1] : 0,
                    wco.data?.Length > 2 ? wco.data[2] : 0,
                    wco.data?.Length > 3 ? wco.data[3] : 0,
                };

                bool changed = !_lastWcoValues[machineId].TryGetValue(wcsNum, out var prev)
                    || !current.SequenceEqual(prev);

                // Always write on change; write every 10 polls even if unchanged (heartbeat)
                if (changed || _pollCount % 10 == 1)
                {
                    _db.InsertWcoSample(new WcoSample
                    {
                        Timestamp = ts,
                        MachineId = machineId,
                        WcsNumber = wcsNum,
                        WcsName   = wcsNames[wcsNum],
                        OffsetX   = current[0],
                        OffsetY   = current[1],
                        OffsetZ   = current[2],
                        OffsetA   = current[3],
                        Changed   = changed
                    });

                    if (changed)
                    {
                        _logger.LogInformation("{Id}: WCO {WCS} changed", machineId, wcsNames[wcsNum]);
                        _lastWcoValues[machineId][wcsNum] = current;
                    }
                }
            }
        }
        catch (Exception ex)
        {
            _logger.LogDebug("WCO read failed for {Id}: {Ex}", machineId, ex.Message);
        }
    }

    // ----------------------------------------------------------------
    // PARAMETERS (slow poll)
    // ----------------------------------------------------------------
    private void ReadParameters(ushort handle, string machineId)
    {
        try
        {
            var ts = DateTime.Now;
            foreach (var (paramNum, description) in ParametersToCapture)
            {
                var value = Focas.ReadParameter(handle, paramNum);
                if (value.HasValue)
                {
                    _db.InsertParameterSnapshot(new ParameterSnapshot
                    {
                        Timestamp   = ts,
                        MachineId   = machineId,
                        ParamNumber = paramNum,
                        Axis        = 0,
                        Value       = value,
                        Description = description
                    });
                }
            }
        }
        catch (Exception ex)
        {
            _logger.LogDebug("Parameter read failed for {Id}: {Ex}", machineId, ex.Message);
        }
    }

    // ----------------------------------------------------------------
    // PROGRAM DIRECTORY (slow poll)
    // ----------------------------------------------------------------
    // Two-tier strategy: try cnc_rdprogdir3 type=0 (full enumeration) first;
    // on failure, fall back to cnc_rdprogdir3 type=1 for the currently-running
    // program. Either path captures the program comment, which downstream
    // consumers (P25 lathe_programs.json, audit cross-reference) need.
    //
    // Errors are logged at Warning level (not Debug) so silent-failure mode
    // can't recur — empty program_directory was undetectable for months.
    private void ReadProgramDirectory(ushort handle, string machineId)
    {
        if (TryEnumerateDirectory(handle, machineId))
            return;

        // Fallback: capture comment for the currently-running program only.
        TryReadRunningProgram(handle, machineId);
    }

    /// <summary>Try full enumeration via cnc_rdprogdir3 type=0. Returns true on success.</summary>
    private bool TryEnumerateDirectory(ushort handle, string machineId)
    {
        try
        {
            int topProg = 1;          // start from first program
            short numProg = 100;      // buffer size in / count out
            var buf = new Focas.PRGDIR3[100];
            short ret = Focas.cnc_rdprogdir3(handle, 0, ref topProg, ref numProg, buf);
            if (ret != 0)
            {
                _logger.LogWarning(
                    "{Id}: cnc_rdprogdir3 type=0 returned {Ret} (will fall back to per-running-program)",
                    machineId, ret);
                return false;
            }
            if (numProg <= 0)
            {
                _logger.LogDebug("{Id}: cnc_rdprogdir3 reported 0 programs in memory", machineId);
                return true;  // No data is not a failure.
            }
            _db.InsertProgramDirectory(machineId, buf, numProg);
            _logger.LogInformation("{Id}: captured {Count} programs from directory enumeration",
                machineId, numProg);
            return true;
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex,
                "{Id}: cnc_rdprogdir3 enumeration threw — falling back",
                machineId);
            return false;
        }
    }

    /// <summary>Fallback: look up just the currently-running program by number.</summary>
    private void TryReadRunningProgram(ushort handle, string machineId)
    {
        try
        {
            if (Focas.cnc_rdprgnum(handle, out var prgnum) != 0)
                return;
            int progNo = prgnum.data;
            if (progNo <= 0)
                return;

            int topProg = progNo;
            short numProg = 1;
            var buf = new Focas.PRGDIR3[1];
            short ret = Focas.cnc_rdprogdir3(handle, 1, ref topProg, ref numProg, buf);
            if (ret != 0 || numProg <= 0)
            {
                _logger.LogWarning(
                    "{Id}: cnc_rdprogdir3 type=1 (per-program) returned {Ret} for O{Prog:D4}",
                    machineId, ret, progNo);
                return;
            }

            _db.InsertProgramDirectoryEntry(
                machineId,
                buf[0].number,
                buf[0].length,
                buf[0].comment);
            _logger.LogInformation("{Id}: captured comment for running program O{Prog:D4}",
                machineId, progNo);
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex,
                "{Id}: per-running-program lookup failed",
                machineId);
        }
    }
}

// Configuration classes (unchanged from original)
public class Config
{
    public int PollIntervalSeconds { get; set; } = 60;
    public string DatabasePath { get; set; } = @"C:\FASData\monitoring.db";
    public string LogPath { get; set; } = @"C:\FASData\logs";
    public List<MachineConfig> Machines { get; set; } = new();
}

public class MachineConfig
{
    public string Id { get; set; } = "";
    public string Name { get; set; } = "";
    public string Type { get; set; } = "";
    public string Ip { get; set; } = "";
    public int Port { get; set; } = 8193;
    public bool Enabled { get; set; } = true;
    public string? Notes { get; set; }

    /// <summary>
    /// PMC D-table address (byte offset) where current tool number is stored.
    /// Read as 16-bit little-endian word. Set to -1 to disable PMC tool read.
    /// </summary>
    public int ToolPmcAddr { get; set; } = -1;
}
