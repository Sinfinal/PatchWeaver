@echo off
setlocal
set SCRIPT_DIR=%~dp0
python "%SCRIPT_DIR%upload_to_validation.py" %*
endlocal
