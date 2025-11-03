@echo off
setlocal

REM --- Script de Compilacao do Quizcord ---

REM Define o diretorio do projeto
set PROJECT_DIR=%~dp0

REM 1. Tenta encontrar e ativar o ambiente virtual (venv)
if exist "%PROJECT_DIR%venv\Scripts\activate.bat" (
call "%PROJECT_DIR%venv\Scripts\activate.bat"
echo Ambiente virtual venv ativado.

REM 2. Define o caminho do PyInstaller dentro do VENV
set PYINSTALLER_CMD="%PROJECT_DIR%venv\Scripts\pyinstaller.exe"


) else (
echo AVISO: Ambiente virtual VENV nao encontrado. Assumindo que o PyInstaller esta no PATH do sistema.
set PYINSTALLER_CMD=pyinstaller
)

REM Define o nome do arquivo principal
set SCRIPT_NAME=disgarai.py

REM Define o nome do executavel de saida
set EXE_NAME=Quizcord.exe

echo Iniciando a compilacao com PyInstaller...
echo.

REM Comando de compilacao com o hook essencial para o PyQtWebEngine
%PYINSTALLER_CMD% %SCRIPT_NAME% ^
--onefile ^
--windowed ^
--name %EXE_NAME% ^
--hidden-import PyQt5.QtWebEngineCore ^
--hidden-import uvicorn.workers

if ERRORLEVEL 1 (
echo.
echo ERRO: A compilacao falhou! Verifique as mensagens acima.
pause
) else (
echo.
echo SUCESSO! O arquivo executavel foi criado em: dist%EXE_NAME%
echo.
pause
)
endlocal