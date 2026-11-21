@echo off
title OMR Automated Test Suite
echo Running complete verification test suite...
python -m pytest -v -s tests\
if errorlevel 1 (
    echo.
    echo Tests failed.
    pause
    exit /b 1
)
echo.
echo All tests passed successfully!
pause

