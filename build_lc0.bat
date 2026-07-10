@echo off
REM ---- Rebuild px0 python binding (.pyd) + lc0.exe (for leela2onnx) with known-good blas config ----
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
set PATH=C:\Users\conra\project\chinese-chess\alphazero\.venv\Scripts;%PATH%
cd /d C:\Users\conra\project\chinese-chess\px0
rmdir /s /q builddir 2>nul
meson setup builddir --native-file venv313.ini ^
  -Dbuildtype=release -Db_vscrt=md -Ddefault_library=static ^
  -Dpython_bindings=true -Dlc0=true ^
  -Dblas=true ^
  -Dcudnn=false -Dplain_cuda=false -Dcutlass=false ^
  -Dopencl=false -Ddx=false -Dtensorflow=false ^
  -Donednn=false -Donnx=false -Dsycl=off -Dmetal=disabled ^
  -Daccelerate=false -Dopenblas=false -Dmkl=false -Ddnnl=false ^
  -Dgtest=false -Dembed=false
if errorlevel 1 exit /b 1
ninja -C builddir lc0.exe backends.cp313-win_amd64.pyd
