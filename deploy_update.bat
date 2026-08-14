@echo off
echo ==========================================
echo   DEPLOY UPDATE - Lumina Chat
echo ==========================================
echo.

set "SERVER_IP=15.229.83.216"
set "PEM=Brabocord.pem"
set "ZIP=dist\download\LuminaChat.zip"

if not exist "%ZIP%" (
  echo ERRO: %ZIP% nao encontrado!
  echo Execute build.bat primeiro.
  pause
  exit /b 1
)

echo Enviando ZIP para o servidor...
echo Servidor: %SERVER_IP%
echo Arquivo: %ZIP%
echo.

scp -i "%PEM%" "%ZIP%" ubuntu@%SERVER_IP%:~/quizcord/static/download/

if errorlevel 1 (
  echo.
  echo ERRO no upload! Verifique:
  echo  - O arquivo %PEM% esta na pasta atual?
  echo  - O IP do servidor esta correto?
  echo  - Voce tem o OpenSSH/SCP instalado?
  echo.
  pause
  exit /b 1
)

echo.
echo ==========================================
echo  UPLOAD CONCLUIDO COM SUCESSO!
echo ==========================================
echo.
echo O arquivo foi enviado para:
echo   /home/ubuntu/quizcord/static/download/LuminaChat.zip
echo.
echo O auto-updater agora vai funcionar!
echo.
pause
