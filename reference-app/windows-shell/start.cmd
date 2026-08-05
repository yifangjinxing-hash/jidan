@echo off
setlocal
cd /d "%~dp0"
if not exist "JidanOS.exe" call build.cmd
if errorlevel 1 pause & exit /b 1
start "" "JidanOS.exe"
