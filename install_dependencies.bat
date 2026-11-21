@echo off
setlocal EnableDelayedExpansion

title Install Dependencies for Offline OMR Evaluation System

echo ===============================================================================
echo            OFFLINE OMR EVALUATION SYSTEM - DEPENDENCY INSTALLER
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
    echo [ERROR] Python was not found on this machine!
    echo.
    echo Please install Python 3.10, 3.11, 3.12, or 3.13 from:
    echo   https://www.python.org/downloads/
    echo IMPORTANT: Make sure to check the box "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

echo Using Python: "%PYTHON_EXE%"
"%PYTHON_EXE%" --version
echo.

echo Upgrading pip...
"%PYTHON_EXE%" -m pip install --upgrade pip

echo.
echo Installing required packages from requirements.txt...
"%PYTHON_EXE%" -m pip install -r "%~dp0requirements.txt"

if errorlevel 1 (
    echo.
    echo [ERROR] Package installation failed.
    echo Please check your internet connection or Python permissions.
    echo.
    pause
    exit /b 1
)

echo.
echo ===============================================================================
echo [SUCCESS] All dependencies have been installed successfully!
echo You can now run:
echo   - extract_identities.bat (to process OMR sheets in batch)
echo   - run_app.bat            (to open the graphical desktop application)
echo   - run_tests.bat          (to verify everything with automated tests)
echo ===============================================================================
echo.
pause

