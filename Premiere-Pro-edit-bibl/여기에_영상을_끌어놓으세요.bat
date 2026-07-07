@echo off
REM 영상 파일을 이 아이콘 위에 끌어다 놓으면 편집이 시작됩니다. (여러 개 가능)
REM 명령어를 칠 필요가 없어요 — 끝나면 output 폴더가 자동으로 열립니다.
setlocal
chcp 65001 >nul
set PYTHONUTF8=1
if "%~1"=="" (
  echo 사용법: 영상 파일을 이 파일 아이콘 위에 끌어다 놓으세요.
  pause
  exit /b 1
)
set FAIL=0
:loop
if "%~1"=="" goto done
echo.
echo ================ %~nx1 ================
python "%~dp0engine\auto_cut.py" "%~f1" || set FAIL=1
shift
goto loop
:done
echo.
if "%FAIL%"=="1" (
  echo [주의] 일부 영상에서 문제가 있었습니다. 위 내용 또는 output\_last_error.log 를 확인하세요.
) else (
  echo 전부 완료! 결과 폴더를 엽니다.
  start "" "%~dp0output"
)
pause
