# Full scan of 192.168.0.x subnet using ping
Write-Host "Scanning 192.168.0.1-254 ..." -ForegroundColor Cyan
foreach ($i in 1..254) {
    $ip = "192.168.0.$i"
    if ($ip -eq "192.168.0.100") { continue }  # skip our own alias
    $ping = ping -n 1 -w 300 $ip 2>&1
    if ($ping -match "Reply from") {
        Write-Host "FOUND: $ip" -ForegroundColor Green
    }
}
Write-Host ""
Write-Host "Also checking 192.168.1.x ..." -ForegroundColor Cyan
foreach ($i in 1..254) {
    $ip = "192.168.1.$i"
    $ping = ping -n 1 -w 300 $ip 2>&1
    if ($ping -match "Reply from") {
        Write-Host "FOUND: $ip" -ForegroundColor Green
    }
}
Write-Host "Scan complete."
