# setup_scheduler.ps1 - Create Windows Task Scheduler entries for REX pipelines
#
# Run this script ONCE as Administrator:
#   powershell -ExecutionPolicy Bypass -File C:\Projects\rexfinhub\scripts\setup_scheduler.ps1
#
# Creates two scheduled tasks:
#   REX_Morning_Pipeline  - 8:00 AM weekdays (catches overnight SEC filings)
#   REX_Evening_Pipeline  - 5:30 PM weekdays (processes Bloomberg data finalized by 5 PM)
#
# Both tasks:
#   - Wake the PC from sleep (WakeToRun)
#   - Run even on battery power
#   - Run if the PC was off at trigger time (StartWhenAvailable)
#   - Auto-kill after 1 hour (safety timeout)

$ErrorActionPreference = "Stop"

$PythonExe = "python"
$Script = "C:\Projects\rexfinhub\scripts\run_all_pipelines.py"
$WorkingDir = "C:\Projects\rexfinhub"

# Verify the script exists
if (-not (Test-Path $Script)) {
    Write-Error "Script not found: $Script"
    exit 1
}

# --- Helper function ---
function New-PipelineTask {
    param(
        [string]$TaskName,
        [string]$TriggerTime,
        [string]$Description
    )

    Write-Host "`nCreating task: $TaskName ($TriggerTime weekdays)" -ForegroundColor Cyan

    # Remove existing task if present
    $existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($existing) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "  Removed existing task."
    }

    # Action: run python with the script
    $action = New-ScheduledTaskAction `
        -Execute $PythonExe `
        -Argument $Script `
        -WorkingDirectory $WorkingDir

    # Trigger: weekdays at specified time
    $trigger = New-ScheduledTaskTrigger `
        -Weekly `
        -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday `
        -At $TriggerTime

    # Settings
    $settings = New-ScheduledTaskSettingsSet `
        -WakeToRun `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
        -MultipleInstances IgnoreNew

    # Register the task (runs as current user, no password needed for non-elevated)
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Description $Description

    Write-Host "  Created: $TaskName" -ForegroundColor Green
}

# --- Create both tasks ---

New-PipelineTask `
    -TaskName "REX_Morning_Pipeline" `
    -TriggerTime "8:00AM" `
    -Description "REX ETP Tracker - Morning run. SEC pipeline + market pipeline + upload to Render + email digest."

New-PipelineTask `
    -TaskName "REX_Evening_Pipeline" `
    -TriggerTime "5:30PM" `
    -Description "REX ETP Tracker - Evening run. SEC pipeline + market pipeline + upload to Render + email digest."

# --- Verify ---
Write-Host "`n--- Verification ---" -ForegroundColor Yellow
Get-ScheduledTask -TaskName "REX_*" | Format-Table TaskName, State, @{
    Label = "NextRunTime"
    Expression = { (Get-ScheduledTaskInfo -TaskName $_.TaskName).NextRunTime }
}

Write-Host "Done. Both tasks will wake the PC from sleep to run." -ForegroundColor Green
Write-Host ""
Write-Host "To check status later:"
Write-Host "  Get-ScheduledTask -TaskName 'REX_*' | Format-List"
Write-Host ""
Write-Host "To run manually:"
Write-Host "  Start-ScheduledTask -TaskName 'REX_Morning_Pipeline'"
Write-Host ""
Write-Host "To remove:"
Write-Host "  Unregister-ScheduledTask -TaskName 'REX_Morning_Pipeline' -Confirm:`$false"
Write-Host "  Unregister-ScheduledTask -TaskName 'REX_Evening_Pipeline' -Confirm:`$false"
