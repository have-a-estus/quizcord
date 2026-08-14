import sys
import os
import json
import time
import subprocess
import tempfile
import shutil
import zipfile
import urllib.request
from pathlib import Path

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QSystemTrayIcon, QMenu, QAction,
    QMessageBox, QWidget, QLabel, QVBoxLayout, QHBoxLayout,
    QPushButton, QGraphicsBlurEffect, QStackedWidget
)
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEnginePage, QWebEngineProfile
from PyQt5.QtCore import (
    QUrl, Qt, QSettings, pyqtSignal, QObject, QTimer, QThread,
    QPropertyAnimation, QEasingCurve, QPoint, pyqtProperty
)
from PyQt5.QtGui import QIcon, QFont, QPixmap, QMouseEvent, QTransform

# ============ CONFIG ============
RENDER_URL = "https://luminachat.duckdns.org"
CURRENT_VERSION = "1.1.0"
UPDATE_URL = RENDER_URL + "/api/version"
DOWNLOAD_URL = RENDER_URL + "/static/download/LuminaChat.zip"
APP_ID = "LuminaChat_v1"

# ============ SINGLE INSTANCE ============
from PyQt5.QtNetwork import QLocalSocket, QLocalServer

class SingleInstance:
    def __init__(self, app_id):
        self.app_id = app_id
        self.socket = QLocalSocket()
        self.socket.connectToServer(app_id)
        if self.socket.waitForConnected(500):
            self.is_running = True
            self.socket.disconnectFromServer()
        else:
            self.is_running = False
            self.server = QLocalServer()
            self.server.listen(app_id)

# ============ UTILS: RESOURCE PATH ============
def resource_path(filename):
    if getattr(sys, "frozen", False):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, filename)

# ============ AUTO UPDATER (ROBUSTO) ============
class UpdateChecker(QThread):
    update_available = pyqtSignal(str, str, str)  # version, url, release_notes
    no_update = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, current_version, update_url):
        super().__init__()
        self.current_version = current_version
        self.update_url = update_url

    def run(self):
        try:
            req = urllib.request.Request(
                self.update_url,
                headers={"User-Agent": "LuminaChat-Updater/1.1"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status != 200:
                    self.error.emit(f"Servidor retornou status {resp.status}")
                    return
                data = json.loads(resp.read().decode("utf-8"))
            remote_version = data.get("version", "0.0.0")
            download_url = data.get("download_url", DOWNLOAD_URL)
            release_notes = data.get("release_notes", "")
            if self._version_greater(remote_version, self.current_version):
                self.update_available.emit(remote_version, download_url, release_notes)
            else:
                self.no_update.emit()
        except Exception as e:
            self.error.emit(str(e))

    def _version_greater(self, v1, v2):
        def parse(v):
            return [int(x) for x in v.split(".")]
        try:
            return parse(v1) > parse(v2)
        except:
            return False


class UpdateDownloader(QThread):
    finished_download = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, url, dest):
        super().__init__()
        self.url = url
        self.dest = dest

    def run(self):
        try:
            req = urllib.request.Request(self.url, headers={"User-Agent": "LuminaChat-Updater/1.1"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                if resp.status != 200:
                    self.error.emit(f"Servidor retornou {resp.status}. O arquivo de atualizacao pode nao estar disponivel.")
                    return
                total = int(resp.headers.get('Content-Length', 0))
                if total > 0 and total < 1000:
                    self.error.emit("Arquivo de atualizacao muito pequeno. Verifique se o ZIP foi enviado ao servidor.")
                    return
                with open(self.dest, 'wb') as f:
                    f.write(resp.read())
            # Verifica se eh um ZIP valido
            if not zipfile.is_zipfile(self.dest):
                self.error.emit("O arquivo baixado nao e um ZIP valido. Verifique o servidor.")
                os.remove(self.dest)
                return
            self.finished_download.emit(self.dest)
        except Exception as e:
            self.error.emit(str(e))


class AutoUpdater(QObject):
    check_done = pyqtSignal(bool, str, str, str)  # has_update, version, url, notes

    def __init__(self, parent, current_version, update_url):
        super().__init__(parent)
        self.current_version = current_version
        self.update_url = update_url
        self.checker = None
        self.downloader = None

    def check(self):
        self.checker = UpdateChecker(self.current_version, self.update_url)
        self.checker.update_available.connect(self._on_update_available)
        self.checker.no_update.connect(lambda: self.check_done.emit(False, "", "", ""))
        self.checker.error.connect(lambda e: self.check_done.emit(False, "", "", e))
        self.checker.start()

    def _on_update_available(self, version, url, notes):
        self.check_done.emit(True, version, url, notes)

    def download_and_install(self, url):
        temp_dir = tempfile.gettempdir()
        zip_path = os.path.join(temp_dir, "LuminaChat_update.zip")
        self.downloader = UpdateDownloader(url, zip_path)
        self.downloader.finished_download.connect(self._install_update)
        self.downloader.error.connect(lambda e: QMessageBox.critical(None, "Erro de Atualizacao", e))
        self.downloader.start()

    def _install_update(self, zip_path):
        try:
            app_dir = os.path.dirname(sys.executable)
            if getattr(sys, "frozen", False):
                extract_dir = os.path.join(tempfile.gettempdir(), "LuminaChat_update")
                if os.path.exists(extract_dir):
                    shutil.rmtree(extract_dir)
                with zipfile.ZipFile(zip_path, "r") as z:
                    z.extractall(extract_dir)

                bat_path = os.path.join(tempfile.gettempdir(), "update_lumina.bat")
                exe_path = os.path.join(app_dir, "LuminaChat.exe")

                with open(bat_path, "w", encoding='utf-8') as f:
                    f.write("@echo off\n")
                    f.write("echo [Updater] Aguardando LuminaChat fechar...\n")
                    f.write("timeout /t 5 /nobreak >nul\n")
                    f.write('echo [Updater] Copiando arquivos...\n')
                    f.write('xcopy /s /y /i "' + extract_dir + '\\*" "' + app_dir + '"\n')
                    f.write("if errorlevel 1 (\n")
                    f.write('  echo [Updater] ERRO ao copiar arquivos!\n')
                    f.write('  pause\n')
                    f.write('  exit /b 1\n')
                    f.write(")\n")
                    f.write('echo [Updater] Reiniciando LuminaChat...\n')
                    f.write('start "" "' + exe_path + '"\n')
                    f.write("echo [Updater] Limpeza...\n")
                    f.write("rmdir /s /q \"" + extract_dir + "\"\n")
                    f.write("del /f /q \"" + zip_path + "\"\n")
                    f.write("del /f /q \"%~f0\"\n")

                subprocess.Popen(["cmd", "/c", bat_path], shell=True,
                                 creationflags=subprocess.CREATE_NEW_CONSOLE)
                QApplication.instance().quit()
            else:
                QMessageBox.information(None, "Update", "Nova versao baixada com sucesso. Reinicie o app para aplicar.")
        except Exception as e:
            QMessageBox.critical(None, "Erro", "Falha ao instalar atualizacao: " + str(e))


# ============ BRIDGE JS <-> PYTHON ============
class Bridge(QObject):
    notify = pyqtSignal(str, str, str)
    badge = pyqtSignal(int)
    flash = pyqtSignal()


# ============ TITLE BAR (Frameless) ============
class TitleBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.drag_pos = None
        self.setFixedHeight(36)
        self.setStyleSheet("""
            TitleBar {
                background-color: rgba(10, 8, 30, 0.95);
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
            }
            QLabel {
                color: #c4b5fd;
                font-family: 'Segoe UI', sans-serif;
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton {
                background: transparent;
                color: #a5b4fc;
                border: none;
                font-size: 14px;
                font-weight: bold;
                width: 40px;
                height: 36px;
            }
            QPushButton:hover {
                background-color: rgba(139, 92, 246, 0.2);
                color: #e0e7ff;
            }
            QPushButton#closeBtn:hover {
                background-color: #ef4444;
                color: white;
            }
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 0, 0)
        layout.setSpacing(0)

        icon_path = resource_path("Icon.ico")
        if os.path.exists(icon_path):
            icon_label = QLabel()
            icon_label.setPixmap(QPixmap(icon_path).scaled(20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            layout.addWidget(icon_label)
        layout.addSpacing(8)

        title = QLabel("Lumina Chat")
        layout.addWidget(title)
        layout.addStretch()

        self.btn_min = QPushButton("\u2014")
        self.btn_min.setObjectName("minBtn")
        self.btn_min.clicked.connect(self.parent.showMinimized)
        layout.addWidget(self.btn_min)

        self.btn_max = QPushButton("\u25a1")
        self.btn_max.setObjectName("maxBtn")
        self.btn_max.clicked.connect(self._toggle_max)
        layout.addWidget(self.btn_max)

        self.btn_close = QPushButton("\u2715")
        self.btn_close.setObjectName("closeBtn")
        self.btn_close.clicked.connect(self.parent._force_quit)
        layout.addWidget(self.btn_close)

    def _toggle_max(self):
        if self.parent.isMaximized():
            self.parent.showNormal()
        else:
            self.parent.showMaximized()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self.drag_pos = event.globalPos() - self.parent.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        if event.buttons() == Qt.LeftButton and self.drag_pos is not None:
            self.parent.move(event.globalPos() - self.drag_pos)
            event.accept()

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        self._toggle_max()


# ============ LOADING SCREEN (Alpaca Animation) ============
class LoadingScreen(QWidget):
    finished = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._angle = 0
        self._cycle = 0
        self._max_cycles = 2
        self._is_dizzy = False
        self._spinning = False

        self.setStyleSheet("""
            LoadingScreen {
                background: qradialgradient(cx:0.5, cy:0.5, radius:0.8,
                    stop:0 #1a103c, stop:0.5 #0f0a1e, stop:1 #050310);
            }
            QLabel {
                color: #c4b5fd;
                font-family: 'Segoe UI', sans-serif;
            }
        """)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(20)

        self.alpaca_label = QLabel()
        self.alpaca_label.setAlignment(Qt.AlignCenter)
        self.alpaca_label.setFixedSize(128, 128)

        self.img_normal = self._load_img("Icon.ico")
        self.img_dizzy = self._load_img("Icon_dizzy.ico")
        if self.img_dizzy is None:
            self.img_dizzy = self.img_normal

        self.alpaca_label.setPixmap(self.img_normal)
        layout.addWidget(self.alpaca_label, alignment=Qt.AlignCenter)

        self.blur = QGraphicsBlurEffect()
        self.blur.setBlurRadius(0)
        self.alpaca_label.setGraphicsEffect(self.blur)

        self.text_label = QLabel("Verificando Atualizacoes...")
        self.text_label.setAlignment(Qt.AlignCenter)
        self.text_label.setStyleSheet("font-size: 14px; color: #a5b4fc; letter-spacing: 1px;")
        layout.addWidget(self.text_label)

        self.sub_label = QLabel("")
        self.sub_label.setAlignment(Qt.AlignCenter)
        self.sub_label.setStyleSheet("font-size: 11px; color: #6366f1;")
        layout.addWidget(self.sub_label)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_frame)

    def _load_img(self, name):
        path = resource_path(name)
        if os.path.exists(path):
            return QPixmap(path).scaled(128, 128, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        path = resource_path(name.lower())
        if os.path.exists(path):
            return QPixmap(path).scaled(128, 128, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        return None

    def _on_frame(self):
        if not self._spinning:
            return
        self._angle += 12
        if self._angle >= 360:
            self._angle = 0
            self._spinning = False
            self._timer.stop()
            self.blur.setBlurRadius(0)
            self._on_spin_done()
            return

        if 90 <= self._angle <= 270:
            self.blur.setBlurRadius(8 + abs(180 - self._angle) / 22)
        else:
            self.blur.setBlurRadius(0)

        orig = self.img_dizzy if self._is_dizzy else self.img_normal
        if orig:
            t = QTransform().rotate(self._angle)
            rotated = orig.transformed(t, Qt.SmoothTransformation)
            self.alpaca_label.setPixmap(rotated)

    def start_animation(self):
        self._cycle = 0
        self._is_dizzy = False
        if self.img_normal:
            self.alpaca_label.setPixmap(self.img_normal)
        self.text_label.setText("Verificando Atualizacoes...")
        self.sub_label.setText("")
        self._start_spin_cycle()

    def _start_spin_cycle(self):
        if self._cycle >= self._max_cycles:
            self.finished.emit()
            return
        self._cycle += 1
        self._angle = 0
        self._spinning = True
        self._timer.start(25)

    def _on_spin_done(self):
        self._is_dizzy = not self._is_dizzy
        if self._is_dizzy:
            if self.img_dizzy:
                self.alpaca_label.setPixmap(self.img_dizzy)
            self.text_label.setText("Carregando o universo...")
        else:
            if self.img_normal:
                self.alpaca_label.setPixmap(self.img_normal)
            self.text_label.setText("Verificando Atualizacoes...")
        QTimer.singleShot(400, self._start_spin_cycle)

    def show_error(self, msg):
        self.sub_label.setText(msg)
        self.sub_label.setStyleSheet("font-size: 11px; color: #f87171;")

    def show_reconnecting(self):
        self.text_label.setText("Conectando ao servidor...")
        self.sub_label.setText("O servidor esta offline. Tentando reconectar...")


# ============ MAIN WINDOW ============
class LuminaClient(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Lumina Chat")
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.resize(1280, 800)

        self.central = QWidget()
        self.setCentralWidget(self.central)
        self.layout = QVBoxLayout(self.central)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        self.title_bar = TitleBar(self)
        self.layout.addWidget(self.title_bar)

        self.stack = QStackedWidget()
        self.layout.addWidget(self.stack)

        self.loading = LoadingScreen()
        self.stack.addWidget(self.loading)

        self.web_container = QWidget()
        web_layout = QVBoxLayout(self.web_container)
        web_layout.setContentsMargins(0, 0, 0, 0)

        self.profile = QWebEngineProfile("LuminaChat", self)
        self.profile.setPersistentCookiesPolicy(QWebEngineProfile.ForcePersistentCookies)
        cache_path = os.path.join(os.path.expanduser("~"), ".lumina", "cache")
        os.makedirs(cache_path, exist_ok=True)
        self.profile.setCachePath(cache_path)
        self.profile.setPersistentStoragePath(os.path.join(os.path.expanduser("~"), ".lumina", "storage"))

        self.browser = QWebEngineView()
        self.page = QWebEnginePage(self.profile, self.browser)
        self.browser.setPage(self.page)
        web_layout.addWidget(self.browser)
        self.stack.addWidget(self.web_container)

        self.bridge = Bridge()
        self.bridge.notify.connect(self._show_notification)
        self.bridge.badge.connect(self._set_badge)
        self.bridge.flash.connect(self._flash_window)

        self.browser.loadFinished.connect(self._on_load_finished)
        self.browser.load(QUrl(RENDER_URL))

        self._setup_tray()

        self.updater = AutoUpdater(self, CURRENT_VERSION, UPDATE_URL)
        self.updater.check_done.connect(self._on_update_check)

        self.loading.start_animation()
        self.loading.finished.connect(self._after_loading)

        self._center_window()

    def _center_window(self):
        from PyQt5.QtWidgets import QDesktopWidget
        qr = self.frameGeometry()
        cp = QDesktopWidget().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

    def _after_loading(self):
        self.updater.check()

    def _on_load_finished(self, ok):
        if ok:
            self._inject_bridge()
            QTimer.singleShot(500, lambda: self.stack.setCurrentWidget(self.web_container))
        else:
            self.loading.show_reconnecting()
            QTimer.singleShot(5000, lambda: self.browser.reload())

    def _inject_bridge(self):
        js = """
        (function() {
            if (window.quizcordNative) return;
            window.quizcordNative = {
                showNotification: function(title, body, color) {
                    if (window.pybridge && window.pybridge.notify) {
                        window.pybridge.notify(title, body, color || "#a78bfa");
                    }
                },
                setBadge: function(count) {
                    if (window.pybridge && window.pybridge.setBadge) {
                        window.pybridge.setBadge(count);
                    }
                },
                flashWindow: function() {
                    if (window.pybridge && window.pybridge.flash) {
                        window.pybridge.flash();
                    }
                },
                getPlatform: function() { return "windows"; },
                getVersion: function() { return "1.1.0"; }
            };
            window.dispatchEvent(new CustomEvent("quizcord-native-ready", {
                detail: { platform: "windows", version: "1.1.0" }
            }));
        })();
        """
        self.browser.page().runJavaScript(js)

    def _setup_tray(self):
        self.tray = QSystemTrayIcon(self)
        icon_path = resource_path("Icon.ico")
        if os.path.exists(icon_path):
            self.tray.setIcon(QIcon(icon_path))
        self.tray.setToolTip("Lumina Chat")
        self.tray.activated.connect(self._tray_activated)

        menu = QMenu()
        open_action = QAction("Abrir Lumina Chat", self)
        open_action.triggered.connect(self.showNormal)
        menu.addAction(open_action)
        menu.addSeparator()
        exit_action = QAction("Sair", self)
        exit_action.triggered.connect(self._force_quit)
        menu.addAction(exit_action)

        self.tray.setContextMenu(menu)
        self.tray.show()

    def _tray_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.showNormal()
            self.raise_()
            self.activateWindow()

    def _show_notification(self, title, body, color):
        if self.tray and self.tray.supportsMessages():
            self.tray.showMessage(title, body, QSystemTrayIcon.Information, 3000)

    def _set_badge(self, count):
        if count > 0:
            self.tray.setToolTip("Lumina Chat (" + str(count) + " nao lidas)")
        else:
            self.tray.setToolTip("Lumina Chat")

    def _flash_window(self):
        if self.isMinimized() or not self.isActiveWindow():
            self.setWindowState(self.windowState() & ~Qt.WindowMinimized | Qt.WindowActive)
            self.raise_()
            self.activateWindow()

    def _on_update_check(self, has_update, version, url, notes_or_error):
        if has_update:
            notes = notes_or_error if notes_or_error else "Novas melhorias disponiveis!"
            reply = QMessageBox.question(
                self, "Atualizacao Disponivel",
                "Nova versao <b>" + version + "</b> disponivel!\n\n" + notes + "\n\nDeseja atualizar agora?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.updater.download_and_install(url)
        else:
            if notes_or_error:
                # Erro na verificacao (nao mostra popup, so loga)
                print("[Updater] Erro na verificacao:", notes_or_error)

    def closeEvent(self, event):
        event.ignore()
        self.hide()
        if self.tray:
            self.tray.showMessage(
                "Lumina Chat",
                "O app continua rodando na bandeja. Clique no icone para abrir.",
                QSystemTrayIcon.Information, 2000
            )

    def _force_quit(self):
        self.tray.hide()
        QApplication.instance().quit()


# ============ MAIN ============
def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Lumina Chat")
    app.setApplicationDisplayName("Lumina Chat")

    font = QFont("Segoe UI", 10)
    app.setFont(font)

    single = SingleInstance(APP_ID)
    if single.is_running:
        QMessageBox.information(None, "Lumina Chat", "Lumina Chat ja esta aberto!")
        sys.exit(0)

    window = LuminaClient()
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
