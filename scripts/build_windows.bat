@echo off

rem Capture start time as ticks
for /f %%i in ('powershell -Command "(Get-Date).Ticks"') do set start_ticks=%%i

rem Check if OnTheSpot.exe is Running
SET "processName=OnTheSpot.exe"
tasklist /FI "IMAGENAME eq %processName%" | findstr /I "%processName%" >nul
if %errorlevel% equ 0 (
    echo %processName% is running. Close the program before building this script.
	pause
	exit /b
) else (
    echo %processName% is not running.
)

set FOLDER_NAME=%cd%
for %%F in ("%cd%") do set FOLDER_NAME=%%~nxF
if /i "%FOLDER_NAME%"=="scripts" (
    echo You are in the scripts folder. Changing to the parent directory...
    cd ..
)

echo ========= OnTheSpot Windows Build Script =========


echo =^> Cleaning up previous builds...
del /F /Q /A dist\OnTheSpot.exe


echo =^> Creating virtual environment...
python -m venv venvwin


echo =^> Activating virtual environment...
call venvwin\Scripts\activate.bat


echo =^> Installing dependencies via pip...
python -m pip install --upgrade pip wheel pyinstaller
pip install -r requirements.txt


echo =^> Downloading FFmpeg binary...
mkdir build
curl -L -o build\ffmpeg.zip https://github.com/GyanD/codexffmpeg/releases/download/8.1.1/ffmpeg-8.1.1-essentials_build.zip
powershell -Command "Expand-Archive -Path build\ffmpeg.zip -DestinationPath build\ffmpeg"


echo =^> Running PyInstaller to create .exe package...
pyinstaller --onefile --noconsole --noconfirm ^
    --hidden-import="zeroconf._utils.ipaddress" ^
    --hidden-import="zeroconf._handlers.answers" ^
    --add-data="src/onthespot/resources/translations/*.qm;onthespot/resources/translations" ^
    --add-data="src/onthespot/qt/qtui/*.ui;onthespot/qt/qtui" ^
    --add-data="src/onthespot/resources/icons/*.png;onthespot/resources/icons" ^
    --add-binary="build/ffmpeg/ffmpeg-8.1.1-essentials_build/bin/ffmpeg.exe;onthespot/bin/ffmpeg" ^
    --paths="src/onthespot" ^
    --name="OnTheSpot" ^
    --icon="src/onthespot/resources/icons/onthespot.png" ^
    src\portable.py

echo =^> Cleaning up temporary files...
del /F /Q *.spec
rmdir /s /q build __pycache__ ffbin_win venvwin

echo =^> Done! Executable available as 'dist/OnTheSpot.exe'

rem Calculate elapsed time
echo.
echo =^> Calculating compile time...
for /f %%i in ('powershell -Command "(Get-Date).Ticks"') do set end_ticks=%%i
powershell -Command "$span = New-Object TimeSpan(%end_ticks% - %start_ticks%); Write-Host ('Script compiled in: {0}h {1}m {2}s' -f [int]$span.Hours, [int]$span.Minutes, [int]$span.Seconds)"
echo.
pause