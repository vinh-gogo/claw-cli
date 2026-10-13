@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
"%SCRIPT_DIR%.venv\Scripts\claw.exe" %*
