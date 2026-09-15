@echo off
chcp 65001 >nul
REM 切換到專案根目錄（scripts 資料夾的上一層）
cd /d "%~dp0.."

REM以背景模式啟動主監控程式（不開啟命令視窗）
start /b "" ".venv\Scripts\pythonw.exe" src\main.py
exit
