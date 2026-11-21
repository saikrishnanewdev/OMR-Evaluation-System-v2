@echo off
setlocal
title Test Evaluation - KNL SGT (83 Sheets)

echo ===============================================================================
echo               RUNNING 95%%+ ACCURACY TEST ON KNL SGT (83 SHEETS)
echo ===============================================================================
echo.

set "APP_DIR=%~dp0"
set "DATA_DIR=%APP_DIR%test_data\KNL_SGT"

if not exist "%DATA_DIR%" (
    if exist "C:\Projects\PC\Syam\New Data\KNL SGT" set "DATA_DIR=C:\Projects\PC\Syam\New Data\KNL SGT"
)

python "%APP_DIR%extract_identities_to_excel.py" "%DATA_DIR%"

echo.
echo ===============================================================================
echo [DONE] Excel report generated in:
echo   "%DATA_DIR%\OMR_Student_Identities.xlsx"
echo Processed crops for visual verification:
echo   "%DATA_DIR%\processed_crops\"
echo ===============================================================================
echo.
pause
