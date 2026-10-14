param(
    [string]$TargetRelative = "run.bat",
    [string]$ShortcutName = "RouteSense AI.lnk"
)

try {
    $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
    $projectRoot = (Resolve-Path (Join-Path $scriptDir "..")).Path
    $targetPath = Join-Path $projectRoot $TargetRelative

    $desktops = @(
        [System.Environment]::GetFolderPath([System.Environment+SpecialFolder]::Desktop),
        (Join-Path $env:USERPROFILE "OneDrive\Desktop"),
        (Join-Path $env:USERPROFILE "Desktop")
    ) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -Unique

    $wsh = New-Object -ComObject WScript.Shell

    foreach ($dp in $desktops) {
        $shortcutPath = Join-Path $dp $ShortcutName
        $shortcut = $wsh.CreateShortcut($shortcutPath)
        $shortcut.TargetPath = $targetPath
        $shortcut.WorkingDirectory = $projectRoot
        $shortcut.Description = "RouteSense AI - Disaster Evacuation Intelligence"
        $shortcut.IconLocation = "shell32.dll,135"
        $shortcut.Save()
        Write-Host "[Shortcut] Desktop shortcut ready: $shortcutPath"
    }
} catch {
    Write-Warning "[Shortcut] Could not create desktop shortcut: $_"
}
