@echo off
setlocal enabledelayedexpansion
REM ---- px0 CUDA (plain_cuda, no cuDNN, no cutlass) build for xiangqi 9x10 ----
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
set PATH=C:\Users\conra\project\chinese-chess\alphazero\.venv\Scripts;%PATH%

REM auto-detect CUDA toolkit if env not set (installer sets it system-wide, may need new shell)
if "%CUDA_PATH%"=="" (
  for /d %%d in ("C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v*") do set CUDA_PATH=%%d
)
if "%CUDA_PATH%"=="" (
  echo ERROR: CUDA toolkit not found.
  exit /b 1
)
echo Using CUDA_PATH=%CUDA_PATH%
set PATH=%CUDA_PATH%\bin;%PATH%
REM convert backslashes to forward slashes for meson ini
set CP=%CUDA_PATH:\=/%

cd /d C:\Users\conra\project\chinese-chess\px0

REM ---- native file: force venv python 3.13 + point at CUDA libs/includes ----
(
echo [binaries]
echo python = 'C:\Users\conra\project\chinese-chess\alphazero\.venv\Scripts\python.exe'
echo.
echo [project options]
echo cudnn_libdirs = ['%CP%/lib/x64']
echo cudnn_include = ['%CP%/include']
) > venv313_cuda.ini
echo --- venv313_cuda.ini ---
type venv313_cuda.ini
echo ------------------------

rmdir /s /q builddir 2>nul
meson setup builddir --native-file venv313_cuda.ini ^
  -Dbuildtype=release -Db_vscrt=md -Ddefault_library=static ^
  -Dpython_bindings=true ^
  -Dblas=true ^
  -Dnvcc=true -Dplain_cuda=true -Dcudnn=false -Dcutlass=false -Dnative_cuda=true ^
  -Dopencl=false -Ddx=false -Dtensorflow=false ^
  -Donednn=false -Donnx=false -Dsycl=off -Dmetal=disabled ^
  -Daccelerate=false -Dopenblas=false -Dmkl=false -Ddnnl=false ^
  -Dgtest=false -Dembed=false
if errorlevel 1 exit /b 1
ninja -C builddir
