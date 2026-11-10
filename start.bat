@echo off
setlocal
cd /d "%~dp0"

rem First run: create .env from the example and ask for the password.
if not exist ".env" (
    copy ".env.example" ".env" >nul
    echo Created .env. Open it in Notepad, set MARIADB_PASSWORD to your
    echo MariaDB root password, save it, then run start.bat again.
    start "" notepad ".env"
    pause
    exit /b 0
)

rem Create the virtual environment once, then install requirements.
if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv
    if errorlevel 1 goto failed
)

".venv\Scripts\python.exe" -m pip install --quiet -r requirements.txt
if errorlevel 1 goto failed

rem Creates the database, migrates, loads demo data and starts the server.
".venv\Scripts\python.exe" run.py
if errorlevel 1 goto failed
exit /b 0

:failed
echo.
echo Startup failed. Read the error above and the steps in README.md.
pause
exit /b 1
