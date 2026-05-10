$ports = @(80, 502, 8234)
foreach ($port in $ports) {
    try {
        $tcp = New-Object System.Net.Sockets.TcpClient
        $tcp.Connect('10.1.1.180', $port)
        Write-Host "Port ${port}: OPEN" -ForegroundColor Green
        $tcp.Close()
    } catch {
        Write-Host "Port ${port}: CLOSED" -ForegroundColor Red
    }
}
