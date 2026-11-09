#Requires -RunAsAdministrator
# Reset the Microsoft RFCOMM device used by the Pudding SPP link.

$devices = @(Get-PnpDevice -ErrorAction SilentlyContinue | Where-Object { $_.InstanceId -match 'MS_RFCOMM' })
if (-not $devices) {
    Write-Host "No RFCOMM device found."
    exit 0
}
if ($devices.Count -gt 1) {
    Write-Host "Found $($devices.Count) RFCOMM devices; using the first one."
}
$target = $devices[0]
Write-Host "Target: $($target.Status) - $($target.FriendlyName) [$($target.InstanceId)]"

Write-Host "Disabling..."
try {
    Disable-PnpDevice -InstanceId $target.InstanceId -Confirm:$false -ErrorAction Stop
} catch {
    Write-Host "Disable failed: $($_.Exception.Message)"
    exit 1
}

Start-Sleep -Seconds 2

Write-Host "Enabling..."
try {
    Enable-PnpDevice -InstanceId $target.InstanceId -Confirm:$false -ErrorAction Stop
} catch {
    Write-Host "Enable failed: $($_.Exception.Message)"
    exit 1
}

Start-Sleep -Seconds 3
$after = @(Get-PnpDevice -ErrorAction SilentlyContinue | Where-Object { $_.InstanceId -match 'MS_RFCOMM' })
if ($after) {
    Write-Host "Result: $($after[0].Status)"
} else {
    Write-Host "Result: device not found after reset."
}
