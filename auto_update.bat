@echo off
cd /d "%~dp0"

echo.
echo [1/2] Collecting recall data...
python recall.py --auto
if %errorlevel% neq 0 (
    echo FAILED: recall.py error
    pause
    exit /b 1
)

echo.
echo [2/2] Uploading to GitHub...
python upload.py
if %errorlevel% neq 0 (
    echo FAILED: upload.py error
    pause
    exit /b 1
)

echo.
echo Done! https://ajongchil-maker.github.io/recall
echo.
pause
