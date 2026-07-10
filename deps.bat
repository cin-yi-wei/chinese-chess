@echo off
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul
cd /d C:\Users\conra\project\chinese-chess\px0\builddir
dumpbin /dependents backends.cp314-win_amd64.pyd
