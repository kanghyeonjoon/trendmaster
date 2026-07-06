@echo off
REM edit.bat — 윈도우용. 영상 1개 → 무음/추임새 컷 + 음량정리 + 자막 한 번에
REM 사용법:  edit.bat "원본영상.mp4"  [--preset 보수^|표준^|공격] [--script "대본.txt"]
setlocal
chcp 65001 >nul
set PYTHONUTF8=1
if "%~1"=="" (
  echo 사용법: edit.bat "원본영상.mp4" [--preset 보수^|표준^|공격] [--script "대본.txt"]
  exit /b 1
)
if not exist "%~1" (
  echo 파일을 찾을 수 없음: %~1
  exit /b 1
)
python "%~dp0engine\auto_cut.py" %*
