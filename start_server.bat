@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Sunshine Kindergarten - Book Corner
echo.
echo   ============================================
echo    Sunshine Kindergarten Smart Book Corner
echo    Starting server on http://127.0.0.1:8501
echo    Close this window to stop the server.
echo   ============================================
echo.
".venv\Scripts\python.exe" -m streamlit run app.py --server.port 8501 --server.headless false --server.address 0.0.0.0 --browser.gatherUsageStats false
echo.
echo   Server stopped.
pause
