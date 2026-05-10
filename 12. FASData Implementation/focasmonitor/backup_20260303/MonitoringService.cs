using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using System.Text.Json;

namespace FocasMonitor;

public class MonitoringService : BackgroundService
{
    private readonly ILogger<MonitoringService> _logger;
    private readonly Config _config;
    private readonly Database _db;

    public MonitoringService(ILogger<MonitoringService> logger)
    {
        _logger = logger;
        _config = LoadConfig();
        _db = new Database(_config.DatabasePath);
    }

    private static Config LoadConfig()
    {
        var configPath = Path.Combine(AppContext.BaseDirectory, "machines.json");
        Console.WriteLine($"Looking for config at: {configPath}");
        
        if (!File.Exists(configPath))
        {
            throw new FileNotFoundException($"Configuration file not found: {configPath}");
        }
        
        var json = File.ReadAllText(configPath);
        var options = new JsonSerializerOptions
        {
            PropertyNameCaseInsensitive = true
        };
        
        var config = JsonSerializer.Deserialize<Config>(json, options) ?? throw new Exception("Failed to parse config");
        
        Console.WriteLine($"Loaded {config.Machines.Count} machines from config");
        foreach (var m in config.Machines)
        {
            Console.WriteLine($"  - {m.Id}: {m.Name} ({m.Ip}) Enabled={m.Enabled}");
        }
        
        return config;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        _logger.LogInformation("FOCAS Monitoring Service started");
        _logger.LogInformation("Database: {Path}", _config.DatabasePath);
        _logger.LogInformation("Poll interval: {Interval} seconds", _config.PollIntervalSeconds);
        _logger.LogInformation("Machines configured: {Count}", _config.Machines.Count(m => m.Enabled));

        while (!stoppingToken.IsCancellationRequested)
        {
            var pollStart = DateTime.Now;
            
            foreach (var machine in _config.Machines.Where(m => m.Enabled && !string.IsNullOrEmpty(m.Ip)))
            {
                try
                {
                    var sample = PollMachine(machine);
                    _db.InsertSample(sample);
                    
                    if (sample.Connected)
                    {
                        _logger.LogDebug("{Id}: {Status} | Spindle: {RPM} RPM | Program: O{Prog}",
                            machine.Id, sample.RunStatus, sample.SpindleSpeed, sample.ProgramNumber);
                    }
                    else
                    {
                        _logger.LogWarning("{Id}: Connection failed - {Error}", machine.Id, sample.ErrorMessage);
                    }
                }
                catch (Exception ex)
                {
                    _logger.LogError(ex, "Error polling {Id}", machine.Id);
                    
                    // Still record the failed attempt
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
            _logger.LogInformation("Poll cycle complete in {Ms}ms", elapsed.TotalMilliseconds);

            // Wait for next poll interval
            var delay = TimeSpan.FromSeconds(_config.PollIntervalSeconds) - elapsed;
            if (delay > TimeSpan.Zero)
            {
                await Task.Delay(delay, stoppingToken);
            }
        }
    }

    private MachineSample PollMachine(MachineConfig machine)
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
                return sample;
            }

            sample.Connected = true;

            // Read status
            if (Focas.cnc_statinfo(handle, out var status) == 0)
            {
                sample.Mode = Focas.GetModeString(status.aut);
                sample.RunStatus = Focas.GetRunStatusString(status.run);
                sample.Motion = Focas.GetMotionString(status.motion);
                sample.Emergency = status.emergency;
                sample.Alarm = status.alarm;
            }

            // Read program number
            if (Focas.cnc_rdprgnum(handle, out var prgnum) == 0)
            {
                sample.ProgramNumber = prgnum.data;
                sample.MainProgram = prgnum.mdata;
            }

            // Read program comment for the running program
            if (sample.ProgramNumber.HasValue && sample.ProgramNumber.Value > 0)
            {
                try
                {
                    var buf = new Focas.PRGDIR3[1];
                    int topProg = sample.ProgramNumber.Value;
                    short numProg = 1;
                    short ret2 = Focas.cnc_rdprogdir3(handle, 1, ref topProg, ref numProg, buf);
                    if (ret2 == 0 && numProg > 0)
                    {
                        string raw = buf[0].comment?.Trim() ?? "";
                        if (raw.StartsWith("(") && raw.EndsWith(")"))
                            raw = raw[1..^1].Trim();
                        if (!string.IsNullOrEmpty(raw))
                            sample.ProgramComment = raw;
                    }
                }
                catch (Exception ex)
                {
                    _logger.LogDebug("Failed to read program comment for {Id}: {Error}",
                        machine.Id, ex.Message);
                }
            }

            // Read spindle speed
            if (Focas.cnc_rdspeed(handle, -1, out var speed) == 0)
            {
                sample.SpindleSpeed = speed.acts.data;
                sample.FeedRate = speed.actf.data;
            }

            // Read positions (axis 1, 2, 3 = X, Y, Z typically)
            if (Focas.cnc_absolute2(handle, -1, 4 + 8 * 3, out var pos) == 0)
            {
                if (pos.data != null && pos.data.Length >= 3)
                {
                    sample.AxisX = pos.data[0];
                    sample.AxisY = pos.data[1];
                    sample.AxisZ = pos.data[2];
                }
            }

            return sample;
        }
        finally
        {
            if (handle != 0)
            {
                Focas.cnc_freelibhndl(handle);
            }
        }
    }
}

// Configuration classes
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
}
