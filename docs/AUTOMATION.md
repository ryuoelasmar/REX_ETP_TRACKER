# Pipeline Automation (Windows Task Scheduler)

Fully automated pipeline execution using Windows Task Scheduler with wake timers. $0/mo.

## How It Works

Two scheduled tasks run `scripts/run_all_pipelines.py` on weekdays:

| Task | Time | Purpose |
|------|------|---------|
| `REX_Morning_Pipeline` | 8:00 AM | Catch overnight SEC filings |
| `REX_Evening_Pipeline` | 5:30 PM | Process Bloomberg data finalized by 5 PM |

Each run executes:
1. **SEC pipeline** -- fetch filings, extract funds, sync to DB, rescore screener
2. **Market pipeline** -- process bbg_data.xlsx (skips automatically if file unchanged)
3. **Upload DB** -- push SQLite to Render
4. **Email digest** -- send daily brief to subscribers

The PC wakes from sleep, runs everything, then goes back to sleep.

## Daily Workflow

```
  YOU (manual)                    AUTOMATED
  ============                    =========

  [morning]
       |                    8:00 AM -- PC wakes from sleep
       |                         |
       |                    run_all_pipelines.py
       |                      -> SEC pipeline (overnight filings)
       |                      -> Market pipeline (skips if no new data)
       |                      -> Upload DB to Render
       |                      -> Email digest
       |                         |
       |                    PC goes back to sleep
       |
  Update Bloomberg data
  in OneDrive / data/
       |
  By 5:00 PM -- data finalized
       |
       |                    5:30 PM -- PC wakes from sleep
       |                         |
       |                    run_all_pipelines.py
       |                      -> SEC pipeline (afternoon filings)
       |                      -> Market pipeline (processes new bbg_data)
       |                      -> Upload DB to Render
       |                      -> Email digest
       |                         |
       |                    PC goes back to sleep
       |
  [evening]                 Website on Render has fresh data
```

## Setup (One-Time)

### 1. Create Scheduled Tasks

Run PowerShell **as Administrator**:

```powershell
powershell -ExecutionPolicy Bypass -File C:\Projects\rexfinhub\scripts\setup_scheduler.ps1
```

This creates both `REX_Morning_Pipeline` and `REX_Evening_Pipeline` tasks.

### 2. Verify Wake Timers Are Enabled

Windows must allow wake timers for the PC to wake from sleep:

1. Open **Power Options** (Win+R, `powercfg.cpl`)
2. Click **Change plan settings** > **Change advanced power settings**
3. Expand **Sleep** > **Allow wake timers**
4. Set to **Enable** (both on battery and plugged in)

### 3. Verify Tasks Were Created

```powershell
Get-ScheduledTask -TaskName "REX_*" | Format-Table TaskName, State
```

## Running Manually

```bash
# Full run (all pipelines)
python scripts/run_all_pipelines.py

# Skip specific steps
python scripts/run_all_pipelines.py --skip-sec
python scripts/run_all_pipelines.py --skip-market
python scripts/run_all_pipelines.py --skip-email

# Force market pipeline even if bbg_data unchanged
python scripts/run_all_pipelines.py --force-market

# Or trigger via Task Scheduler
Start-ScheduledTask -TaskName "REX_Morning_Pipeline"
```

## Log Files

All runs log to `logs/pipeline_YYYYMMDD_HHMM.log` (tee to both console and file).

```bash
# View most recent log
ls -t logs/pipeline_*.log | head -1 | xargs cat

# Tail a running log
tail -f logs/pipeline_$(date +%Y%m%d)_*.log
```

## Task Scheduler Settings

Both tasks use these settings:

| Setting | Value | Why |
|---------|-------|-----|
| WakeToRun | Yes | Wakes PC from sleep at scheduled time |
| AllowStartIfOnBatteries | Yes | Runs on laptop too |
| DontStopIfGoingOnBatteries | Yes | Won't kill mid-run if unplugged |
| StartWhenAvailable | Yes | If PC was off, runs when it wakes |
| ExecutionTimeLimit | 1 hour | Safety kill switch |
| MultipleInstances | IgnoreNew | Won't double-run |

## Troubleshooting

### PC doesn't wake from sleep

1. Check wake timers are enabled (see Setup step 2)
2. Some machines disable wake timers in BIOS -- check BIOS settings
3. Hibernate (S4) does NOT support wake timers, only Sleep (S3) does
4. Verify: `powercfg /waketimers` shows the scheduled tasks

### Pipeline runs but market data is stale

The market pipeline skips if `bbg_data.xlsx` hasn't changed since the last run:
```
  Data unchanged since last run (2026-02-25T17:00:00)
  Use --force to re-process. Exiting.
```

This is expected. To force a re-run: `python scripts/run_all_pipelines.py --force-market`

### Task Scheduler shows "Last Run Result: 0x1"

Check the log file for errors. Common causes:
- Python not on PATH (Task Scheduler uses system PATH, not user PATH)
- Missing dependencies (`pip install -r requirements.txt`)
- Network issues (SEC or Render unreachable)

Fix PATH issue by using full Python path in setup_scheduler.ps1:
```powershell
$PythonExe = "C:\Python313\python.exe"  # or wherever your Python is
```

### Removing the scheduled tasks

```powershell
Unregister-ScheduledTask -TaskName "REX_Morning_Pipeline" -Confirm:$false
Unregister-ScheduledTask -TaskName "REX_Evening_Pipeline" -Confirm:$false
```

## Why Not VPS?

| Option | Cost | Pros | Cons |
|--------|------|------|------|
| **Windows Task Scheduler** | **$0/mo** | **Free, has HTTP cache (13GB), has OneDrive** | **Requires PC to sleep (not off)** |
| VPS (Hetzner/DO) | $4-6/mo | Always on | No OneDrive, must sync cache, monthly cost |
| GitHub Actions | Free | No server | No persistent HTTP cache, limited minutes |

The HTTP cache alone (~13GB) makes local execution preferable. The SEC pipeline reads from cached responses, so incremental runs complete in seconds.
