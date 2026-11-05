@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
title Video Compressor - Instalacao
cd /d "%~dp0"

echo ============================================================
echo    Video Compressor - Treinamentos  ^|  Instalação
echo ============================================================
echo.

REM ── 1. Python ───────────────────────────────────────────────
echo [1/3] Verificando Python...
call :find_python
if not defined PY (
    echo    Python não encontrado. Instalando Python 3.12 via Winget...
    where winget >nul 2>&1
    if errorlevel 1 (
        echo.
        echo    [ERRO] Winget não está disponível neste Windows.
        echo    Instale o Python manualmente em: https://www.python.org/downloads/
        echo    IMPORTANTE: marque a opção "Add python.exe to PATH" no instalador.
        echo    Depois rode este setup.bat novamente.
        goto :fail
    )
    winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
    call :find_python
)
if not defined PY (
    echo.
    echo    [ERRO] Não foi possível localizar o Python após a instalação.
    echo    Feche esta janela, abra de novo e rode setup.bat mais uma vez.
    echo    Ou instale manualmente: https://www.python.org/downloads/
    goto :fail
)
for /f "delims=" %%v in ('"!PY!" --version 2^>^&1') do echo    OK: %%v

REM ── 2. Ambiente virtual + bibliotecas ─────────────────────
echo.
echo [2/3] Criando o ambiente virtual (.venv) e instalando as bibliotecas...
set "VENV_PY=%~dp0.venv\Scripts\python.exe"
if not exist "!VENV_PY!" (
    "!PY!" -m venv "%~dp0.venv"
    if errorlevel 1 (
        echo.
        echo    [ERRO] Não foi possível criar o ambiente virtual na pasta .venv
        goto :fail
    )
)
"!VENV_PY!" -m pip install --upgrade pip >nul 2>&1
"!VENV_PY!" -m pip install -r "%~dp0requirements.txt"
if errorlevel 1 (
    echo.
    echo    [ERRO] Falha ao instalar as bibliotecas. Verifique sua internet e tente de novo.
    goto :fail
)
echo    OK: bibliotecas instaladas em .venv - o Python do sistema não foi alterado.

REM ── 3. FFmpeg ───────────────────────────────────────────────
echo.
echo [3/3] Verificando FFmpeg...
set "HAS_FFMPEG="
where ffmpeg >nul 2>&1 && set "HAS_FFMPEG=1"
if exist "C:\ffmpeg\bin\ffmpeg.exe" set "HAS_FFMPEG=1"
if exist "%~dp0ffmpeg\bin\ffmpeg.exe" set "HAS_FFMPEG=1"
if exist "%LOCALAPPDATA%\Microsoft\WinGet\Links\ffmpeg.exe" set "HAS_FFMPEG=1"

if defined HAS_FFMPEG (
    echo    OK: FFmpeg já está instalado.
) else (
    echo    FFmpeg não encontrado. Instalando via Winget ^(Gyan.FFmpeg^)...
    where winget >nul 2>&1
    if errorlevel 1 (
        echo    [AVISO] Winget indisponível. Instale manualmente:
        echo      1. Baixe "ffmpeg-release-essentials.zip" em https://www.gyan.dev/ffmpeg/builds/
        echo      2. Extraia para C:\ffmpeg\  ^(deve existir C:\ffmpeg\bin\ffmpeg.exe^)
        echo      3. Adicione C:\ffmpeg\bin ao PATH do Windows
    ) else (
        winget install -e --id Gyan.FFmpeg --accept-source-agreements --accept-package-agreements
        if errorlevel 1 (
            echo    [AVISO] A instalação do FFmpeg pode ter falhado. Use install_ffmpeg.bat.
        ) else (
            echo    OK: FFmpeg instalado. ^(Se o app não encontrá-lo, reinicie o computador.^)
        )
    )
)

echo.
echo ============================================================
echo    Instalação concluída! Agora dê duplo clique em start.bat
echo ============================================================
echo.
pause
exit /b 0

:fail
echo.
pause
exit /b 1

REM ── Localiza um Python funcional (ignora o atalho da Microsoft Store) ──
:find_python
set "PY="
where python >nul 2>&1 && python --version >nul 2>&1 && set "PY=python"
if not defined PY (
    where py >nul 2>&1 && py --version >nul 2>&1 && set "PY=py"
)
if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
exit /b 0
