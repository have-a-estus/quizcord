import os
import sys
import json
import urllib.request
import urllib.error
import zipfile
import shutil
import subprocess
from pathlib import Path

UPDATE_URL = "https://luminachat.duckdns.org/api/version"
DOWNLOAD_URL = "https://luminachat.duckdns.org/static/download/LuminaChat.zip"

APP_DIR = Path(os.environ.get('LOCALAPPDATA', os.path.expanduser('~'))) / "LuminaChat"
VERSION_FILE = APP_DIR / "version.json"

class AutoUpdater:
    def __init__(self, current_version="1.0.0"):
        self.current_version = current_version
        self.latest_version = None
        self.download_url = None

    def check_update(self):
        """Verifica se ha atualizacao disponivel. Retorna (needs_update, version_info)"""
        try:
            req = urllib.request.Request(UPDATE_URL, headers={'User-Agent': 'LuminaChat/1.0'})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                self.latest_version = data.get('version', self.current_version)
                self.download_url = data.get('download_url', DOWNLOAD_URL)

                needs_update = self._compare_versions(self.current_version, self.latest_version) < 0
                return needs_update, data
        except Exception as e:
            print(f"[Updater] Erro ao verificar atualizacao: {e}")
            return False, None

    def _compare_versions(self, v1, v2):
        """Compara duas versoes. Retorna -1 se v1 < v2, 0 se igual, 1 se v1 > v2"""
        def normalize(v):
            return [int(x) for x in v.split('.')]
        return (normalize(v1) > normalize(v2)) - (normalize(v1) < normalize(v2))

    def download_and_install(self, parent_widget=None):
        """Baixa e instala a atualizacao"""
        import tempfile

        try:
            temp_dir = Path(tempfile.gettempdir()) / "LuminaChat_Update"
            temp_dir.mkdir(exist_ok=True)

            zip_path = temp_dir / "update.zip"

            print(f"[Updater] Baixando {self.download_url}...")
            req = urllib.request.Request(self.download_url, headers={'User-Agent': 'LuminaChat/1.0'})
            with urllib.request.urlopen(req, timeout=60) as resp:
                with open(zip_path, 'wb') as f:
                    f.write(resp.read())

            extract_dir = temp_dir / "extracted"
            if extract_dir.exists():
                shutil.rmtree(extract_dir)
            with zipfile.ZipFile(zip_path, 'r') as z:
                z.extractall(extract_dir)

            # Cria script de atualizacao
            updater_script = temp_dir / "do_update.bat"
            exe_path = Path(sys.executable)
            app_dir = exe_path.parent

            batch_content = (
                '@echo off\n'
                'timeout /t 2 /nobreak >nul\n'
                'echo Atualizando Lumina Chat...\n'
                f'xcopy /e /i /y "{extract_dir}\\*" "{app_dir}\\"\n'
                f'if exist "{app_dir}\\LuminaChat.exe" (\n'
                f'    start "" "{app_dir}\\LuminaChat.exe"\n'
                ')\n'
                f'del "{zip_path}"\n'
                f'rmdir /s /q "{extract_dir}"\n'
                'del "%~f0"\n'
            )

            with open(updater_script, 'w') as f:
                f.write(batch_content)

            subprocess.Popen([str(updater_script)], shell=True, 
                           creationflags=subprocess.CREATE_NEW_CONSOLE)

            return True

        except Exception as e:
            print(f"[Updater] Erro ao atualizar: {e}")
            return False

    def save_version(self):
        APP_DIR.mkdir(parents=True, exist_ok=True)
        with open(VERSION_FILE, 'w') as f:
            json.dump({'version': self.current_version}, f)

    def load_version(self):
        if VERSION_FILE.exists():
            try:
                with open(VERSION_FILE) as f:
                    data = json.load(f)
                    return data.get('version', '1.0.0')
            except:
                pass
        return '1.0.0'
