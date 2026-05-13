# composite_screenshots.ps1 — Combine 4 setup screenshots into a 2x2 grid
# Called from ProShopBridge.py via subprocess
# Args: -topPng <path> -frontPng <path> -rightPng <path> -isoPng <path> -outputPath <path>

param(
    [Parameter(Mandatory)][string]$topPng,
    [Parameter(Mandatory)][string]$frontPng,
    [Parameter(Mandatory)][string]$rightPng,
    [Parameter(Mandatory)][string]$isoPng,
    [Parameter(Mandatory)][string]$outputPath
)

Add-Type -AssemblyName System.Drawing

$imgTop = $null; $imgFront = $null; $imgRight = $null; $imgIso = $null
$canvas = $null; $g = $null

try {
    # Load source images
    $imgTop   = [System.Drawing.Image]::FromFile($topPng)
    $imgFront = [System.Drawing.Image]::FromFile($frontPng)
    $imgRight = [System.Drawing.Image]::FromFile($rightPng)
    $imgIso   = [System.Drawing.Image]::FromFile($isoPng)

    # Target canvas: 1280x720 (640x360 per quadrant) at JPEG q65.
    $maxCanvasW = 1280
    $maxCanvasH = 720
    $srcW = $imgTop.Width
    $srcH = $imgTop.Height
    $scale = [Math]::Min($maxCanvasW / ($srcW * 2), $maxCanvasH / ($srcH * 2))
    if ($scale -gt 1.0) { $scale = 1.0 }
    $qw = [int]($srcW * $scale)
    $qh = [int]($srcH * $scale)
    $canvas = New-Object System.Drawing.Bitmap(($qw * 2), ($qh * 2))
    $g = [System.Drawing.Graphics]::FromImage($canvas)
    $g.SmoothingMode = 'AntiAlias'
    $g.TextRenderingHint = 'AntiAlias'
    $g.InterpolationMode = 'HighQualityBicubic'
    $g.Clear([System.Drawing.Color]::White)

    # Draw images: TOP (top-left), FRONT (top-right), RIGHT (bot-left), ISO (bot-right)
    $g.DrawImage($imgTop,   0,   0, $qw, $qh)
    $g.DrawImage($imgFront, $qw, 0, $qw, $qh)
    $g.DrawImage($imgRight, 0,   $qh, $qw, $qh)
    $g.DrawImage($imgIso,   $qw, $qh, $qw, $qh)

    # Draw thin separator lines between quadrants
    $pen = New-Object System.Drawing.Pen([System.Drawing.Color]::FromArgb(180, 80, 80, 80), 2)
    $g.DrawLine($pen, $qw, 0, $qw, ($qh * 2))   # vertical center
    $g.DrawLine($pen, 0, $qh, ($qw * 2), $qh)    # horizontal center
    $pen.Dispose()

    # Add view labels
    $fontSize = if ($qw -lt 500) { 10 } else { 14 }
    $font = New-Object System.Drawing.Font('Segoe UI', $fontSize, [System.Drawing.FontStyle]::Bold)
    $textBrush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(240, 20, 20, 20))
    $bgBrush   = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(190, 255, 255, 255))

    $labels = @(
        @{ Text = 'TOP';   X = 0;   Y = 0   },
        @{ Text = 'FRONT'; X = $qw; Y = 0   },
        @{ Text = 'RIGHT'; X = 0;   Y = $qh },
        @{ Text = 'ISO';   X = $qw; Y = $qh }
    )

    foreach ($lbl in $labels) {
        $sz = $g.MeasureString($lbl.Text, $font)
        $pad = 6
        $rx = $lbl.X + 8
        $ry = $lbl.Y + 6
        $rect = New-Object System.Drawing.RectangleF($rx, $ry, ($sz.Width + $pad * 2), ($sz.Height + $pad))
        $g.FillRectangle($bgBrush, $rect)
        $g.DrawString($lbl.Text, $font, $textBrush, ($rx + $pad), ($ry + $pad / 2))
    }

    $font.Dispose(); $textBrush.Dispose(); $bgBrush.Dispose()

    # Save as JPEG with quality control
    $jpegCodec = [System.Drawing.Imaging.ImageCodecInfo]::GetImageEncoders() |
        Where-Object { $_.MimeType -eq 'image/jpeg' } | Select-Object -First 1
    $encParams = New-Object System.Drawing.Imaging.EncoderParameters(1)
    $encParams.Param[0] = New-Object System.Drawing.Imaging.EncoderParameter(
        [System.Drawing.Imaging.Encoder]::Quality, [long]65
    )
    $canvas.Save($outputPath, $jpegCodec, $encParams)

    Write-Output "OK"
}
catch {
    Write-Error "Composite failed: $_"
    exit 1
}
finally {
    if ($g)        { $g.Dispose() }
    if ($canvas)   { $canvas.Dispose() }
    if ($imgTop)   { $imgTop.Dispose() }
    if ($imgFront) { $imgFront.Dispose() }
    if ($imgRight) { $imgRight.Dispose() }
    if ($imgIso)   { $imgIso.Dispose() }
}
