@echo off
REM batch.bat — 윈도우용. 폴더 안 모든 영상(mp4/mov/m4v/mkv)을 한 번에 컷편집
REM 사용법:  batch.bat "영상폴더" [보수^|표준^|공격]
setlocal enabledelayedexpansion
set "SRC=%~1"
set "PRESET=%~2"
if "%PRESET%"=="" set "PRESET=표준"
if "%SRC%"=="" (
  echo 사용법: batch.bat "영상폴더" [보수^|표준^|공격]
  exit /b 1
)
if not exist "%SRC%\" (
  echo 폴더를 찾을 수 없음: %SRC%
  exit /b 1
)
echo 프리셋 %PRESET% · 폴더 %SRC%
for %%E in (mp4 mov m4v mkv) do (
  for %%F in ("%SRC%\*.%%E") do (
    echo.
    echo ---------- %%~nxF ----------
    python "%~dp0engine\auto_cut.py" "%%~fF" --preset "%PRESET%" || echo [주의] 실패: %%~nxF (건너뜀^)
  )
)
echo.
echo 배치 완료. 결과는 output\ 폴더.
