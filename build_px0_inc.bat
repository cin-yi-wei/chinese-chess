@echo off
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
set PATH=C:\Users\conra\project\chinese-chess\alphazero\.venv\Scripts;%PATH%
cd /d C:\Users\conra\project\chinese-chess\px0
ninja -C builddir
