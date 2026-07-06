@echo off
REM check.bat — 실행 전 환경 점검 (python/ffmpeg/GPU/모델 상태)
setlocal
chcp 65001 >nul
set PYTHONUTF8=1
python "%~dp0engine\doctor.py"
