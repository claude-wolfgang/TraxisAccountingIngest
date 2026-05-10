using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using FocasMonitor;

// Configure and run the service
var builder = Host.CreateApplicationBuilder(args);

// Configure logging
builder.Logging.ClearProviders();
builder.Logging.AddConsole();
builder.Logging.SetMinimumLevel(LogLevel.Information);

// Add file logging
var logPath = Path.Combine(
    Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData),
    "FASData", "logs");
Directory.CreateDirectory(logPath);

// Add the monitoring service
builder.Services.AddHostedService<MonitoringService>();

// Enable Windows Service support
builder.Services.AddWindowsService(options =>
{
    options.ServiceName = "FOCAS Machine Monitor";
});

var host = builder.Build();

Console.WriteLine("=====================================================");
Console.WriteLine("  FOCAS Machine Monitor - Traxis Manufacturing");
Console.WriteLine("=====================================================");
Console.WriteLine();
Console.WriteLine("Press Ctrl+C to stop");
Console.WriteLine();

await host.RunAsync();
