@echo off
chcp 65001 >nul
title Video Compressor - Treinamentos
cd /d "%~dp0"

set "VENV_PY=%~dp0.venv\Scripts\python.exe"

if not exist "%VENV_PY%" (
    echo ============================================================
    echo    [ERRO] O ambiente do aplicativo ainda não foi instalado.
    echo ============================================================
    echo.
    echo    Rode primeiro o setup.bat ^(duplo clique^). Ele instala o Python,
    echo    as bibliotecas ^(na pasta .venv^) e o FFmpeg.
    echo.
    pause
    exit /b 1
)

echo Iniciando o Video Compressor...
"%VENV_PY%" "%~dp0video_compressor.py"
if errorlevel 1 (
    echo.
    echo ============================================================
    echo    [ERRO] O aplicativo foi encerrado com erro.
    echo ============================================================
    echo    Se a mensagem acima falar em "No module named", rode setup.bat
    echo    de novo para reinstalar as bibliotecas.
    echo.
    pause
    exit /b 1
)
exit /b 0
