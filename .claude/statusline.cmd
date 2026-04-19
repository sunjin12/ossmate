@echo off
:: Ossmate status line (Windows cmd version)
::
:: settings.json should point to either statusline.sh OR this file depending
:: on the user's OS. This is a minimal fallback for systems without bash.
:: For full feature parity (open PR count, stale count), use statusline.sh.

setlocal EnableDelayedExpansion

:: Read all of stdin into a temp file so PowerShell can parse it as JSON.
set "TMPFILE=%TEMP%\ossmate_statusline_%RANDOM%.json"
more > "%TMPFILE%"

:: Delegate JSON parsing + git lookup to PowerShell — cmd's string handling
:: is too painful for nested JSON.
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$j = Get-Content -Raw '%TMPFILE%' | ConvertFrom-Json;" ^
    "$model = $j.model.display_name;" ^
    "$proj  = $j.workspace.project_dir;" ^
    "if (-not $proj) { $proj = $j.cwd }" ^
    "$branch = '';" ^
    "if (Test-Path (Join-Path $proj '.git')) {" ^
    "  Push-Location $proj;" ^
    "  $branch = (git symbolic-ref --short HEAD 2>$null);" ^
    "  $tag = (git describe --tags --abbrev=0 2>$null);" ^
    "  Pop-Location;" ^
    "}" ^
    "$line = \"[$model]\";" ^
    "if ($branch) { $line += \"  branch:$branch\" }" ^
    "if ($tag)    { $line += \"  tag:$tag\" }" ^
    "if ($j.context_window.used_percentage) { $line += \"  ctx:$($j.context_window.used_percentage)%%\" }" ^
    "Write-Output $line"

del "%TMPFILE%" 2>nul
endlocal
