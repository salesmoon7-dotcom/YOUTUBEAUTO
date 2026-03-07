@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
pushd "%SCRIPT_DIR%"

if "%~1"=="" (
    python -m runtime_v2.cli --selftest
) else (
    python -m runtime_v2.cli %*
)

set "EXIT_CODE=%ERRORLEVEL%"
popd

exit /b %EXIT_CODE%
