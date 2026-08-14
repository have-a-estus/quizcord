@echo off
chcp 65001 >nul
echo ==========================================
echo   LUMINA CHAT - Build System v1.1.0
echo ==========================================
echo.

set "APP_NAME=LuminaChat"
set "VERSION=1.1.0"
set "ICON=Icon.ico"
set "ICON_DIZZY=Icon_dizzy.ico"
set "MAIN=cliente.py"
set "ISS=lumina_setup.iss"

cd /d "%~dp0"

echo [1/6] Limpando builds anteriores...
if exist "dist" rmdir /s /q "dist"
if exist "build" rmdir /s /q "build"
if exist "*.spec" del /f /q "*.spec"
if exist "update_*.zip" del /f /q "update_*.zip"
if exist "LuminaChat_Update.zip" del /f /q "LuminaChat_Update.zip"
echo OK
echo.

echo [2/6] Compilando executavel com PyInstaller...
pyinstaller --noconfirm --onefile --windowed ^
  --name "%APP_NAME%" ^
  --icon="%ICON%" ^
  --add-data "%ICON%;." ^
  --add-data "%ICON_DIZZY%;." ^
  --hidden-import PyQt5.QtWebEngineWidgets ^
  --hidden-import PyQt5.QtWebEngineCore ^
  --hidden-import PyQt5.QtNetwork ^
  "%MAIN%"

if errorlevel 1 (
  echo ERRO na compilacao!
  pause
  exit /b 1
)
echo OK
echo.

echo [3/6] Criando ZIP de atualizacao (update)...
if not exist "dist\download" mkdir "dist\download"

:: Os icones estao na pasta raiz, o .exe esta em dist\
:: Usamos caminhos relativos corretos
powershell -Command "Compress-Archive -Path 'dist\%APP_NAME%.exe','%ICON%','%ICON_DIZZY%' -Force -DestinationPath 'dist\download\LuminaChat.zip'"
if errorlevel 1 (
  echo ERRO ao criar ZIP de update!
  pause
  exit /b 1
)
echo OK - ZIP de update: dist\download\LuminaChat.zip
echo.

echo [4/6] Criando ZIP full (para distribuicao manual)...
powershell -Command "Compress-Archive -Path 'dist\%APP_NAME%.exe','%ICON%','%ICON_DIZZY%' -Force -DestinationPath 'dist\LuminaChat_v%VERSION%_Windows.zip'"
echo OK - ZIP full: dist\LuminaChat_v%VERSION%_Windows.zip
echo.

echo [5/6] Compilando instalador com Inno Setup...
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" (
  "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" /Q "%ISS%"
  echo OK - Instalador gerado
) else (
  echo AVISO: Inno Setup nao encontrado. Pulando criacao do instalador.
)
echo.

echo [6/6] Resumo do build:
echo ------------------------------------------
dir /b "dist\%APP_NAME%.exe"
dir /b "dist\download\LuminaChat.zip"
dir /b "dist\LuminaChat_v%VERSION%_Windows.zip" 2>nul
dir /b "Output\*.exe" 2>nul
echo ------------------------------------------
echo.
echo ==========================================
echo  BUILD CONCLUIDO!
echo ==========================================
echo.
echo Proximos passos:
echo  1. Teste: execute dist\%APP_NAME%.exe
echo  2. Envie o ZIP de update para o servidor:
echo     scp -i "Brabocord.pem" "dist\download\LuminaChat.zip" ubuntu@15.229.83.216:~/quizcord/static/download/
echo  3. Envie o instalador para os amigos
echo.
pause