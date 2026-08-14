@echo off
chcp 65001 >nul
echo ==========================================
echo  Lumina Chat - Build System v1.1
echo ==========================================
echo.

REM Verifica PyInstaller
pyinstaller --version >nul 2>&1
if errorlevel 1 (
    echo [ERRO] PyInstaller nao encontrado. Instalando...
    pip install pyinstaller
)

REM Verifica Inno Setup
if not exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" (
    if not exist "C:\Program Files\Inno Setup 6\ISCC.exe" (
        echo [ERRO] Inno Setup 6 nao encontrado!
        echo Baixe em: https://jrsoftware.org/isdl.php
        pause
        exit /b 1
    )
)

echo [1/4] Limpando builds antigos...
if exist dist rmdir /s /q dist
if exist build rmdir /s /q build
if exist LuminaChat.spec del /f /q LuminaChat.spec

echo [2/4] Compilando executavel com PyInstaller...
pyinstaller --noconfirm --onefile --windowed --name "LuminaChat" --icon=Icon.ico --add-data "Icon.ico;." --add-data "Icon_dizzy.ico;." cliente.py

echo [3/4] Preparando arquivos para o instalador...
mkdir dist\installer
move /y dist\LuminaChat.exe dist\installer\
if exist Icon.ico copy /y Icon.ico dist\installer\ >nul
if exist icon.ico copy /y icon.ico dist\installer\ >nul 2>nul

echo [4/4] Gerando instalador Inno Setup...
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" (
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" lumina_setup.iss
) else (
    "C:\Program Files\Inno Setup 6\ISCC.exe" lumina_setup.iss
)

echo.
echo ==========================================
echo  BUILD CONCLUIDO!
echo ==========================================
if exist "dist\installer\LuminaChatSetup.exe" (
    echo Instalador: dist\installer\LuminaChatSetup.exe
    echo.
    echo Pronto para distribuir!
) else (
    echo [AVISO] Instalador nao encontrado. Verifique erros acima.
)
echo.
pause