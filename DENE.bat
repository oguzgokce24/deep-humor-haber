@echo off
cd /d "%~dp0"
echo Facebook'a paylasmadan deneme yapiliyor; gorseller "out" klasorune kaydedilecek...
py -3 main.py --dry-run
echo.
pause
