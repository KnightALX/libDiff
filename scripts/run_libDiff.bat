@echo off
setlocal EnableExtensions
cd /d "%~dp0.."

set PYTHONUNBUFFERED=1
set "LIBDIFF_PYTHON="

if exist "%USERPROFILE%\anaconda3\python.exe" set "LIBDIFF_PYTHON=%USERPROFILE%\anaconda3\python.exe"
if not defined LIBDIFF_PYTHON if exist "%USERPROFILE%\miniconda3\python.exe" set "LIBDIFF_PYTHON=%USERPROFILE%\miniconda3\python.exe"
if not defined LIBDIFF_PYTHON if exist "C:\ProgramData\anaconda3\python.exe" set "LIBDIFF_PYTHON=C:\ProgramData\anaconda3\python.exe"

if not defined LIBDIFF_PYTHON (
  where py >nul 2>nul
  if not errorlevel 1 (
    py -3 -c "from PyQt5.QtWidgets import QApplication" >nul 2>nul
    if not errorlevel 1 set "LIBDIFF_PYTHON=PY_LAUNCHER"
  )
)

if not defined LIBDIFF_PYTHON (
  where python >nul 2>nul
  if not errorlevel 1 (
    python -c "from PyQt5.QtWidgets import QApplication" >nul 2>nul
    if not errorlevel 1 set "LIBDIFF_PYTHON=PYTHON_PATH"
  )
)

if not defined LIBDIFF_PYTHON (
  echo.
  echo [libDiff] ERROR: No Python with PyQt5 found.
  echo This project needs PyQt5 + matplotlib + numpy.
  echo Tried: %%USERPROFILE%%\anaconda3\python.exe, py -3, python
  echo.
  echo Fix example:
  echo   "%USERPROFILE%\anaconda3\python.exe" -m pip install -e ".[dev]"
  echo.
  pause
  exit /b 1
)

echo [libDiff] Starting GUI ...
if "%LIBDIFF_PYTHON%"=="PY_LAUNCHER" (
  py -3 -m libdiff gui %*
) else if "%LIBDIFF_PYTHON%"=="PYTHON_PATH" (
  python -m libdiff gui %*
) else (
  echo [libDiff] Python: %LIBDIFF_PYTHON%
  "%LIBDIFF_PYTHON%" -m libdiff gui %*
)

set "EC=%ERRORLEVEL%"
if not "%EC%"=="0" (
  echo.
  echo [libDiff] Exited with code %EC%
  pause
)
exit /b %EC%
