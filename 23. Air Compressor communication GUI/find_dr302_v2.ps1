# Scan 10.1.1.x for any new device with port 502 or port 80 open
# Also try common DR302 defaults on other subnets

Write-Host "=== Checking common DR302 default IPs ===" -ForegroundColor Cyan
$defaults = @('192.168.0.7','192.168.1.7','192.168.0.1','192.168.1.1','192.168.0.10','192.168.1.10','192.168.0.100','192.168.1.100','192.168.0.200','192.168.1.200')
foreach ($ip in $defaults) {
    $ping = ping -n 1 -w 500 $ip 2>&1
    if ($ping -match "Reply from") {
        Write-Host "FOUND: $ip responds to ping!" -ForegroundColor Green
    }
}

Write-Host ""
Write-Host "=== Scanning 10.1.1.x for port 502 (Modbus) and port 80 (Web) ===" -ForegroundColor Cyan
foreach ($i in 1..254) {
    $ip = "10.1.1.$i"
    foreach ($port in @(502, 80)) {
        try {
            $tcp = New-Object System.Net.Sockets.TcpClient
            $result = $tcp.BeginConnect($ip, $port, $null, $null)
            $wait = $result.AsyncWaitHandle.WaitOne(200, $false)
            if ($wait -and $tcp.Connected) {
                Write-Host "OPEN: ${ip}:${port}" -ForegroundColor Green
            }
            $tcp.Close()
        } catch {}
    }
}
Write-Host "Scan complete."
