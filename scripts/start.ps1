$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if (!(Test-Path '.env')) { throw 'Run python scripts/setup.py first and add OPENROUTER_API_KEY to .env.' }
Start-Process -FilePath "$PWD/.venv/Scripts/python.exe" -ArgumentList '-m uvicorn app.b:app --host 127.0.0.1 --port 8001' -WorkingDirectory $PWD -WindowStyle Hidden -RedirectStandardOutput "$PWD/runtime/b-stdout.log" -RedirectStandardError "$PWD/runtime/b-stderr.log" -PassThru | Select-Object Id
Start-Process -FilePath "$PWD/.venv/Scripts/python.exe" -ArgumentList '-m uvicorn app.a:app --host 127.0.0.1 --port 8000' -WorkingDirectory $PWD -WindowStyle Hidden -RedirectStandardOutput "$PWD/runtime/a-stdout.log" -RedirectStandardError "$PWD/runtime/a-stderr.log" -PassThru | Select-Object Id
Write-Output 'Open http://localhost:8000. Stop these process IDs when finished.'

Start-Process -FilePath "$PWD/.venv/Scripts/python.exe" -ArgumentList '-m uvicorn app.logs:app --host 127.0.0.1 --port 8002' -WorkingDirectory $PWD -WindowStyle Hidden -RedirectStandardOutput "$PWD/runtime/logs-stdout.log" -RedirectStandardError "$PWD/runtime/logs-stderr.log" -PassThru | Select-Object Id
Start-Process -FilePath "$PWD/.venv/Scripts/python.exe" -ArgumentList '-m uvicorn app.bookings:app --host 127.0.0.1 --port 8003' -WorkingDirectory $PWD -WindowStyle Hidden -RedirectStandardOutput "$PWD/runtime/bookings-stdout.log" -RedirectStandardError "$PWD/runtime/bookings-stderr.log" -PassThru | Select-Object Id
