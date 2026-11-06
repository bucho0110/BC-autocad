@echo off
rem Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
chcp 65001 >nul
rem BC AutoCAD MCP 설치 — 더블클릭으로 실행. Python은 배포하지 않으므로 먼저 직접 설치한다.
where python >nul 2>nul
if errorlevel 1 goto nopython
rem 버전 미달만 2로 끝낸다. 그 밖의 0 아닌 값(9009 등)은 스토어 별칭처럼 Python이 실제로 없는 경우다.
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 2)" >nul 2>nul
set "BC_PY=%errorlevel%"
if "%BC_PY%"=="2" (
  echo.
  echo [오류] 설치된 Python 버전이 3.10 미만입니다. 3.10 이상 버전을 설치한 후 다시 실행하십시오.
  echo.
  pause
  exit /b 1
)
if not "%BC_PY%"=="0" goto nopython
echo AutoCAD를 실행하고 도면을 하나 열어 둔 상태에서 설치를 진행하십시오.
python "%~dp0install\install.py" --all
rem AI 에이전트 등 키 입력을 할 수 없는 곳에서 실행할 때: install.cmd /nopause
if /i "%~1"=="/nopause" exit /b
echo.
pause
exit /b

:nopython
echo.
echo [오류] Python이 설치되어 있지 않습니다. 본 도구는 Python을 배포하지 않습니다.
echo   1. 공식 웹사이트^(https://www.python.org/downloads/^)에서 Python 3.10 이상 버전을 내려받아 설치하십시오.
echo   2. 설치 첫 화면 하단의 "Add python.exe to PATH" 옵션을 반드시 선택하십시오.
echo   3. 설치를 마친 후 install.cmd를 다시 실행하십시오.
echo.
pause
exit /b 1
