@echo off
title Tokeneado el pana
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo No se encontro Python. Instalalo desde https://www.python.org/downloads/
    echo y marca la casilla "Add python.exe to PATH" al instalar.
    pause
    exit /b
)

python -c "import keyboard, PIL" >nul 2>nul
if errorlevel 1 (
    echo Instalando lo necesario por unica vez...
    python -m pip install keyboard pillow
)

start "" pythonw contador_cofres.py
exit /b
