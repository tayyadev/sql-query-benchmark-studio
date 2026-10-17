@echo off
setlocal
cd /d "%~dp0"
echo KTNS SQL Benchmark Studio - local community edition
echo Open http://127.0.0.1:8765 in your browser after the server starts.
where py >nul 2>nul
if %ERRORLEVEL%==0 (
    py -3 -m sqlbench serve
) else (
    python -m sqlbench serve
)
if ERRORLEVEL 1 (
    echo Python 3.11 or later is required. Press any key to close.
    pause >nul
)
