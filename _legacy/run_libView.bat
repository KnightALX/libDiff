@echo off
setlocal
cd /d "%~dp0"
set PYTHONUNBUFFERED=1
"C:\Users\USER\anaconda3\python.exe" "%~dp0libView.py" %*
