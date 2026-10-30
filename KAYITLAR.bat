@echo off
cd /d "%~dp0"
if exist logs\calisma.log (notepad logs\calisma.log) else (echo Henuz kayit yok. & pause)
