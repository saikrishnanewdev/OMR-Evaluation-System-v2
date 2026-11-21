@echo off
setlocal EnableDelayedExpansion

title Offline OMR Student Identity Extractor

echo ===============================================================================
echo            OFFLINE OMR BATCH IDENTITY EXTRACTOR TO EXCEL
echo ===============================================================================
echo.

:: 1. Detect Python executable
set "PYTHON_EXE="
where python >nul 2>&1 && set "PYTHON_EXE=python"

if "%PYTHON_EXE%"=="" if exist "C:\Program Files\Python313\python.exe" set "PYTHON_EXE=C:\Program Files\Python313\python.exe"
if "%PYTHON_EXE%"=="" if exist "C:\Program Files\Python312\python.exe" set "PYTHON_EXE=C:\Program Files\Python312\python.exe"
if "%PYTHON_EXE%"=="" if exist "C:\Program Files\Python311\python.exe" set "PYTHON_EXE=C:\Program Files\Python311\python.exe"
if "%PYTHON_EXE%"=="" if exist "%LocalAppData%\Programs\Python\Python313\python.exe" set "PYTHON_EXE=%LocalAppData%\Programs\Python\Python313\python.exe"
if "%PYTHON_EXE%"=="" if exist "%LocalAppData%\Programs\Python\Python312\python.exe" set "PYTHON_EXE=%LocalAppData%\Programs\Python\Python312\python.exe"

if "%PYTHON_EXE%"=="" (
    echo [ERROR] Python was not found on your system!
    echo Please install Python 3.10+ or ensure python is added to your PATH.
    echo.
    pause
    exit /b 1
)

:: 2. Locate Application Directory containing extract_identities_to_excel.py
set "APP_DIR="
if exist "%~dp0extract_identities_to_excel.py" set "APP_DIR=%~dp0"
if "%APP_DIR%"=="" if exist "C:\Projects\PC\Syam\Application\extract_identities_to_excel.py" set "APP_DIR=C:\Projects\PC\Syam\Application"

if "%APP_DIR%"=="" (
    echo [ERROR] Could not locate 'extract_identities_to_excel.py'!
    echo Expected in C:\Projects\PC\Syam\Application or alongside this .bat file.
    echo.
    pause
    exit /b 1
)

:: Canonicalize APP_DIR path
for %%I in ("%APP_DIR%") do set "APP_DIR=%%~fI"

:: 3. Determine Target Folder with Scanned OMR Sheets
set "TARGET_DIR="

:: Case A: Argument passed (command-line argument or Drag-and-Drop)
if not "%~1"=="" set "TARGET_DIR=%~1"
if not "%TARGET_DIR%"=="" goto check_target

:: Case B: The directory where this .bat file lives (if placed directly in scans folder)
set "BAT_DIR=%~dp0"
for %%I in ("%BAT_DIR%") do set "BAT_DIR=%%~fI"

if /I "%BAT_DIR%"=="%APP_DIR%" goto check_current_dir
if exist "%BAT_DIR%\*.jpg" set "TARGET_DIR=%BAT_DIR%"
if exist "%BAT_DIR%\*.jpeg" set "TARGET_DIR=%BAT_DIR%"
if exist "%BAT_DIR%\*.png" set "TARGET_DIR=%BAT_DIR%"
if exist "%BAT_DIR%\*.tif" set "TARGET_DIR=%BAT_DIR%"
if exist "%BAT_DIR%\*.tiff" set "TARGET_DIR=%BAT_DIR%"
if not "%TARGET_DIR%"=="" goto check_target

:check_current_dir
:: Case C: Current working directory
set "CURRENT_DIR=%CD%"
for %%I in ("%CURRENT_DIR%") do set "CURRENT_DIR=%%~fI"

if /I "%CURRENT_DIR%"=="%APP_DIR%" goto prompt_user
if exist "%CURRENT_DIR%\*.jpg" set "TARGET_DIR=%CURRENT_DIR%"
if exist "%CURRENT_DIR%\*.jpeg" set "TARGET_DIR=%CURRENT_DIR%"
if exist "%CURRENT_DIR%\*.png" set "TARGET_DIR=%CURRENT_DIR%"
if exist "%CURRENT_DIR%\*.tif" set "TARGET_DIR=%CURRENT_DIR%"
if exist "%CURRENT_DIR%\*.tiff" set "TARGET_DIR=%CURRENT_DIR%"
if not "%TARGET_DIR%"=="" goto check_target

:prompt_user
:: Case D: Prompt user if running directly inside application folder without argument
set "DEFAULT_DIR=C:\Projects\PC\Syam\New Data\KNL SA"
echo Scanned OMR folder not specified.
echo.
set /p "USER_INPUT=Enter folder path [Press ENTER for default: %DEFAULT_DIR%]: "
if "%USER_INPUT%"=="" (
    set "TARGET_DIR=%DEFAULT_DIR%"
) else (
    set "TARGET_DIR=%USER_INPUT%"
)

:check_target
:: Clean quotes & canonicalize
set "TARGET_DIR=%TARGET_DIR:"=%"
for %%I in ("%TARGET_DIR%") do set "TARGET_DIR=%%~fI"

if not exist "%TARGET_DIR%" (
    echo.
    echo [ERROR] Specified folder does not exist: "%TARGET_DIR%"
    echo.
    pause
    exit /b 1
)

:: 4. Execute Identity Extraction
echo -------------------------------------------------------------------------------
echo Application  : "%APP_DIR%"
echo Target Folder: "%TARGET_DIR%"
echo -------------------------------------------------------------------------------
echo.

set "PYTHONPATH=%APP_DIR%"
"%PYTHON_EXE%" "%APP_DIR%\extract_identities_to_excel.py" "%TARGET_DIR%"

if errorlevel 1 (
    echo.
    echo [ERROR] Processing completed with errors.
) else (
    echo.
    echo [SUCCESS] Batch evaluation and extraction finished successfully!
    echo Output Excel: 'OMR_Student_Identities.xlsx' (OMR Marks, Ranks and Identities)
)

echo.
pause
