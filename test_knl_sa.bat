@echo off
setlocal
title Test Evaluation - KNL SA (15 Sheets)

echo ===============================================================================
echo               RUNNING 100%% ACCURACY TEST ON KNL SA (15 SHEETS)
echo ===============================================================================
echo.

set "APP_DIR=%~dp0"
set "DATA_DIR=%APP_DIR%test_data\KNL_SA"

if not exist "%DATA_DIR%" (
    if exist "C:\Projects\PC\Syam\New Data\KNL SA" set "DATA_DIR=C:\Projects\PC\Syam\New Data\KNL SA"
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
