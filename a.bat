@echo off
python %~dp0\fetch01.py %~dp0
pause

echo %~d0
echo %~dp0
echo %~sdp0
echo %~f0
echo %cd%
pause