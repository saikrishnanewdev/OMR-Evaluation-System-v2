@echo off
setlocal
title OMR Evaluation & Identity System - Client Edition

set "APP_DIR=%~dp0"
cd /d "%APP_DIR%"

if exist "%APP_DIR%dist\OMREvaluationSystem\OMREvaluationSystem.exe" (
    start "" "%APP_DIR%dist\OMREvaluationSystem\OMREvaluationSystem.exe"
) else (
    python app\main.py
)
exit

