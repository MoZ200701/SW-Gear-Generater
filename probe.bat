@echo off
REM Probe the SolidWorks API on the running session and write the results into
REM probe\results. SolidWorks must already be open; nothing is launched.
REM
REM pushd maps the \\wsl.localhost path of a WSL checkout to a drive letter, so
REM this works whether the repo sits on C: or inside WSL.
pushd "%~dp0"
python "%~dp0probe.py" --out "%~dp0probe\results" %*
set CODE=%ERRORLEVEL%
popd
exit /b %CODE%
