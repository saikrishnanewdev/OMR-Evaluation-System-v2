@echo off
title Offline OMR Evaluation System
echo Starting Offline OMR Evaluation System...
python app\main.py
if errorlevel 1 (
    echo.
    echo Application exited with an error.
    pause
)

