# FOCAS Test Prerequisites Check
# Run this first to verify your PC is ready

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "FOCAS Test - Prerequisites Check" -ForegroundColor Cyan  
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# Check .NET SDK
Write-Host "[1] Checking .NET SDK..." -ForegroundColor Yellow
try {
    $dotnetVersion = dotnet --version 2>$null
    if ($dotnetVersion) {
        Write-Host "    OK - .NET SDK $dotnetVersion installed" -ForegroundColor Green
        
        # Check architecture
        $dotnetInfo = dotnet --info 2>$null
        if ($dotnetInfo -match "x86") {
            Write-Host "    OK - x86 (32-bit) version detected" -ForegroundColor Green
        } elseif ($dotnetInfo -match "x64") {
            Write-Host "    WARNING - x64 version detected" -ForegroundColor Yellow
            Write-Host "    The FOCAS DLLs are 32-bit. You may need x86 .NET SDK" -ForegroundColor Yellow
            Write-Host "    Download from: https://dotnet.microsoft.com/download/dotnet/6.0" -ForegroundColor Yellow
        }
    }
} catch {
    Write-Host "    MISSING - .NET SDK not found" -ForegroundColor Red
    Write-Host "    Download x86 version from: https://dotnet.microsoft.com/download/dotnet/6.0" -ForegroundColor Red
}

# Check DLL files
Write-Host ""
Write-Host "[2] Checking FOCAS DLLs..." -ForegroundColor Yellow
$requiredDlls = @("Fwlib32.dll", "fwlibe1.dll", "fwlib30i.dll", "Fwlib160.dll")
$missingDlls = @()

foreach ($dll in $requiredDlls) {
    if (Test-Path $dll) {
        $size = (Get-Item $dll).Length / 1KB
        Write-Host "    OK - $dll ({0:N0} KB)" -f $size -ForegroundColor Green
    } else {
        Write-Host "    MISSING - $dll" -ForegroundColor Red
        $missingDlls += $dll
    }
}

if ($missingDlls.Count -gt 0) {
    Write-Host ""
    Write-Host "    Missing DLLs! Make sure all DLLs are in this folder." -ForegroundColor Red
}

# Network test
Write-Host ""
Write-Host "[3] Network Connectivity Test..." -ForegroundColor Yellow
$testIp = Read-Host "    Enter machine IP to test (or press Enter to skip)"

if ($testIp) {
    Write-Host "    Testing ping to $testIp..." -ForegroundColor Gray
    $ping = Test-Connection -ComputerName $testIp -Count 2 -Quiet
    if ($ping) {
        Write-Host "    OK - Ping successful" -ForegroundColor Green
        
        Write-Host "    Testing FOCAS port 8193..." -ForegroundColor Gray
        $portTest = Test-NetConnection -ComputerName $testIp -Port 8193 -WarningAction SilentlyContinue
        if ($portTest.TcpTestSucceeded) {
            Write-Host "    OK - Port 8193 is open" -ForegroundColor Green
        } else {
            Write-Host "    FAILED - Port 8193 not responding" -ForegroundColor Red
            Write-Host "    Check FOCAS is enabled on CNC (TCP PORT = 8193)" -ForegroundColor Yellow
        }
    } else {
        Write-Host "    FAILED - Cannot ping $testIp" -ForegroundColor Red
        Write-Host "    Check: Network cable, IP address, machine power" -ForegroundColor Yellow
    }
}

# Summary
Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "Summary" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan

if ($dotnetVersion -and $missingDlls.Count -eq 0) {
    Write-Host "Ready to run test! Use:" -ForegroundColor Green
    Write-Host "  dotnet run 192.168.x.x" -ForegroundColor White
    Write-Host "  (replace with your machine IP)" -ForegroundColor Gray
} else {
    Write-Host "Fix the issues above before running the test." -ForegroundColor Yellow
}

Write-Host ""
Read-Host "Press Enter to exit"
