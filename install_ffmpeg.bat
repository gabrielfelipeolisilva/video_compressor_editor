@echo off
chcp 65001 >nul
title Instalar FFmpeg
cd /d "%~dp0"

:menu
cls
echo ============================================================
echo    Instalação do FFmpeg - Video Compressor
echo ============================================================
echo.
echo    [1] Instalar automaticamente via Winget (recomendado)
echo    [2] Instalação manual (abre o site de download)
echo    [0] Sair
echo.
set "OPT="
set /p "OPT=Escolha uma opção: "
if "%OPT%"=="1" goto :winget
if "%OPT%"=="2" goto :manual
if "%OPT%"=="0" exit /b 0
goto :menu

:winget
echo.
where winget >nul 2>&1
if errorlevel 1 (
    echo [ERRO] Winget não está disponível neste Windows. Use a opção [2].
    echo.
    pause
    goto :menu
)
echo Instalando FFmpeg (Gyan.FFmpeg) via Winget...
winget install -e --id Gyan.FFmpeg --accept-source-agreements --accept-package-agreements
if errorlevel 1 (
    echo.
    echo [AVISO] A instalação pode ter falhado. Tente a opção [2].
) else (
    echo.
    echo [OK] FFmpeg instalado! Feche e abra o Video Compressor novamente.
    echo      Se ainda não for encontrado, reinicie o computador.
)
echo.
pause
exit /b 0

:manual
echo.
echo Abrindo https://www.gyan.dev/ffmpeg/builds/ ...
start "" "https://www.gyan.dev/ffmpeg/builds/"
echo.
echo Passo a passo:
echo   1. Na seção "release builds", baixe "ffmpeg-release-essentials.zip".
echo   2. Extraia o conteúdo para C:\ffmpeg\
echo      (deve existir o arquivo C:\ffmpeg\bin\ffmpeg.exe)
echo   3. Adicione C:\ffmpeg\bin ao PATH:
echo      Iniciar ^> "Editar as variáveis de ambiente do sistema" ^>
echo      Variáveis de Ambiente ^> Path ^> Editar ^> Novo ^> C:\ffmpeg\bin ^> OK
echo   4. Feche e abra o Video Compressor novamente.
echo.
echo Dica: o app também encontra o FFmpeg em C:\ffmpeg\bin mesmo sem PATH,
echo ou numa pasta "ffmpeg\bin" ao lado do video_compressor.py.
echo.
pause
exit /b 0
