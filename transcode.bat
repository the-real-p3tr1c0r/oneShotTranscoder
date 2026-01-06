@echo off
REM Batch wrapper for Transcoder executable
REM This script allows calling transcode from anywhere when added to PATH

REM Get the directory where this batch file is located
set "SCRIPT_DIR=%~dp0"

REM Change to the script directory
cd /d "%SCRIPT_DIR%"

REM Check for executable in onedir structure (lightweight build)
if exist "transcode\transcode.exe" (
    REM Run from onedir build
    "transcode\transcode.exe" %*
    exit /b %ERRORLEVEL%
) else if exist "transcode.exe" (
    REM Run the executable directly (if in root)
    "transcode.exe" %*
    exit /b %ERRORLEVEL%
) else (
    echo Error: transcode.exe not found in %SCRIPT_DIR%
    echo Please reinstall Transcoder.
    exit /b 1
)

