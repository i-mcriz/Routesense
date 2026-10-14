param(
    [string]$Url = "http://localhost:5000",
    [string]$HealthUrl = "http://localhost:5000/api/health",
    [int]$TimeoutSeconds = 120
)

$sw = [System.Diagnostics.Stopwatch]::StartNew()
$opened = $false

while ($sw.Elapsed.TotalSeconds -lt $TimeoutSeconds) {
    try {
        $res = Invoke-WebRequest -Uri $HealthUrl -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
        if ($res.StatusCode -eq 200) {
            Start-Process $Url
            $opened = $true
            break
        }
    } catch {
        # Server still initializing
    }
    Start-Sleep -Milliseconds 1200
}

if (-not $opened) {
    # If healthcheck timed out, still attempt to open URL as fallback
    Start-Process $Url
}
