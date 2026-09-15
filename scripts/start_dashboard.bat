@echo off
REM強制將CMD編碼切換為UTF-8，解決中文亂碼問題
chcp 65001 >nul

REM切換到專案根目錄（scripts 資料夾的上一層）
cd /d "%~dp0.."

echo ===================================================
echo 正在啟用虛擬環境並啟動Streamlit網頁儀表板...
echo ===================================================

REM啟用虛擬環境
call .venv\Scripts\activate

REM 啟動 Streamlit 網頁
streamlit run src\dashboard.py

echo.
echo ===================================================
echo 系統通知：程式執行已中斷或結束。
echo ===================================================
pause
