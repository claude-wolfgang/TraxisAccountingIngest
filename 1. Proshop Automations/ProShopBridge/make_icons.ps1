Add-Type -AssemblyName System.Drawing

function Make-Icon {
    param([int]$sz, [string]$outPath)
    $bmp = New-Object System.Drawing.Bitmap($sz, $sz)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.SmoothingMode = 'AntiAlias'
    $g.TextRenderingHint = 'AntiAlias'
    $g.Clear([System.Drawing.Color]::FromArgb(255, 12, 25, 56))
    $fontSize = [math]::Floor($sz * 0.38)
    $font = New-Object System.Drawing.Font('Segoe UI', $fontSize, [System.Drawing.FontStyle]::Bold)
    $brush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(255, 255, 102, 0))
    $sf = New-Object System.Drawing.StringFormat
    $sf.Alignment = 'Center'
    $sf.LineAlignment = 'Center'
    $rect = New-Object System.Drawing.RectangleF(0, 0, $sz, $sz)
    $g.DrawString('PS', $font, $brush, $rect, $sf)
    $lineH = [math]::Max(1, [math]::Floor($sz * 0.06))
    $g.FillRectangle($brush, 0, ($sz - $lineH), $sz, $lineH)
    $g.Dispose()
    $bmp.Save($outPath, [System.Drawing.Imaging.ImageFormat]::Png)
    $bmp.Dispose()
    Write-Output "Created $outPath"
}

$base = 'D:\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\1. Proshop Automations\ProShopBridge\resources'
Make-Icon -sz 16 -outPath "$base\16x16.png"
Make-Icon -sz 32 -outPath "$base\32x32.png"
Make-Icon -sz 64 -outPath "$base\64x64.png"
