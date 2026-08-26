@echo off
cd /d "%~dp0"
".venv312\Scripts\python.exe" main.py
if errorlevel 1 (
    echo.
    echo O app fechou com erro. Veja a mensagem acima.
    pause
)
