@echo off
cd /d "%~dp0"

where pythonw.exe >nul 2>&1
if %errorlevel%==0 (
    start "" /b pythonw.exe "%~dp0main.py"
    exit /b 0
)

if exist "%LocalAppData%\Programs\Python\Python313\pythonw.exe" (
    start "" /b "%LocalAppData%\Programs\Python\Python313\pythonw.exe" "%~dp0main.py"
    exit /b 0
)

echo Python 3.13 pythonw.exe was not found.
pause
