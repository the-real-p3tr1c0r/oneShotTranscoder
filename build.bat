@echo off
REM Build script for Windows
REM This script runs the Python build script to create a standalone executable

python build.py
if %ERRORLEVEL% NEQ 0 (
    echo Build failed!
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo Build completed successfully!
echo Executable location: dist\transcode.exe
pause


