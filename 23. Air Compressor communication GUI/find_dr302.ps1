$ips = @(
    '10.1.1.13','10.1.1.35','10.1.1.44','10.1.1.67','10.1.1.70',
    '10.1.1.72','10.1.1.76','10.1.1.82','10.1.1.100','10.1.1.108',
    '10.1.1.112','10.1.1.127','10.1.1.134','10.1.1.139','10.1.1.156',
    '10.1.1.176','10.1.1.186','10.1.1.188','10.1.1.190','10.1.1.191',
    '10.1.1.197','10.1.1.199','10.1.1.200','10.1.1.201','10.1.1.202',
    '10.1.1.220','10.1.1.228','10.1.1.242','10.1.1.243','10.1.1.253'
)

foreach ($ip in $ips) {
    try {
        $tcp = New-Object System.Net.Sockets.TcpClient
        $result = $tcp.BeginConnect($ip, 502, $null, $null)
        $wait = $result.AsyncWaitHandle.WaitOne(300, $false)
        if ($wait -and $tcp.Connected) {
            Write-Host "FOUND PORT 502 OPEN: $ip"
        }
        $tcp.Close()
    } catch {}
}
Write-Host "Scan complete."
