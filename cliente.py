import sys
import os
import json
import subprocess
import tempfile
import shutil
import zipfile
import urllib.request
import random

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QSystemTrayIcon, QMenu, QAction,
    QMessageBox, QWidget, QLabel, QVBoxLayout, QHBoxLayout,
    QPushButton, QStackedWidget
)
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEnginePage, QWebEngineProfile
from PyQt5.QtCore import Qt, pyqtSignal, QObject, QTimer, QThread, QPoint, QPropertyAnimation, QEasingCurve, QUrl, QElapsedTimer
from PyQt5.QtGui import QIcon, QFont, QPixmap, QMouseEvent, QColor

# ============ CONFIG ============
RENDER_URL = "https://luminachat.duckdns.org"
CURRENT_VERSION = "1.1.0"
UPDATE_URL = RENDER_URL + "/api/version"
DOWNLOAD_URL = RENDER_URL + "/static/download/LuminaChat.zip"
APP_ID = "LuminaChat_v1"

# ============ FRASES ============
FRASES_NORMAL = [
    "A alpaca esta carregando. Ela nao sabe o que isso significa.",
    "Espera! A alpaca esta pensando...",
    "Quieto! Ela vai falar algo! Deixa pra la...",
    "A culpa e da gravidade.",
    "A alpaca esta contando estrelas...",
    "Conectando os pontos cosmicos...",
    "A alpaca esta ajustando o telescopio...",
]

FRASES_LENTO = [
    "Eu acho que a Alpaca bateu numa estrela.",
    "Erro 418: alpaca virou bule.",
    "Isso esta demorando tanto que Plutao foi promovido de novo.",
    "Mano... Cade a Alpaca?",
    "Estamos indo na velocidade da luz. Aparentemente ela nao e tao rapida assim.",
    "A alpaca parou para tomar um chimarrao no espaco.",
    "Acho que a Alpaca foi dar um passeio na Via Lactea.",
]

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

def resource_path(filename):
    if getattr(sys, "frozen", False):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, filename)

# ============ UPDATER ============
class UpdateChecker(QThread):
    update_available = pyqtSignal(str, str, str)
    no_update = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, current_version, update_url):
        super().__init__()
        self.current_version = current_version
        self.update_url = update_url

    def run(self):
        try:
            req = urllib.request.Request(self.update_url, headers={"User-Agent": "LuminaChat-Updater/1.1"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status != 200:
                    self.error.emit(f"Servidor retornou status {resp.status}")
                    return
                data = json.loads(resp.read().decode("utf-8"))
            remote = data.get("version", "0.0.0")
            url = data.get("download_url", DOWNLOAD_URL)
            notes = data.get("release_notes", "")
            if self._version_greater(remote, self.current_version):
                self.update_available.emit(remote, url, notes)
            else:
                self.no_update.emit()
        except Exception as e:
            self.error.emit(str(e))

    def _version_greater(self, v1, v2):
        try:
            return [int(x) for x in v1.split(".")] > [int(x) for x in v2.split(".")]
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
                    self.error.emit(f"Servidor retornou {resp.status}")
                    return
                with open(self.dest, 'wb') as f:
                    f.write(resp.read())
            if not zipfile.is_zipfile(self.dest):
                self.error.emit("Arquivo baixado nao e um ZIP valido.")
                os.remove(self.dest)
                return
            self.finished_download.emit(self.dest)
        except Exception as e:
            self.error.emit(str(e))

class AutoUpdater(QObject):
    check_done = pyqtSignal(bool, str, str, str)

    def __init__(self, parent, current_version, update_url):
        super().__init__(parent)
        self.current_version = current_version
        self.update_url = update_url

    def check(self):
        self.checker = UpdateChecker(self.current_version, self.update_url)
        self.checker.update_available.connect(lambda v,u,n: self.check_done.emit(True, v, u, n))
        self.checker.no_update.connect(lambda: self.check_done.emit(False, "", "", ""))
        self.checker.error.connect(lambda e: self.check_done.emit(False, "", "", e))
        self.checker.start()

    def download_and_install(self, url):
        zip_path = os.path.join(tempfile.gettempdir(), "LuminaChat_update.zip")
        self.downloader = UpdateDownloader(url, zip_path)
        self.downloader.finished_download.connect(self._install)
        self.downloader.error.connect(lambda e: QMessageBox.critical(None, "Erro", e))
        self.downloader.start()

    def _install(self, zip_path):
        try:
            app_dir = os.path.dirname(sys.executable)
            if getattr(sys, "frozen", False):
                extract_dir = os.path.join(tempfile.gettempdir(), "LuminaChat_update")
                if os.path.exists(extract_dir):
                    shutil.rmtree(extract_dir)
                with zipfile.ZipFile(zip_path, "r") as z:
                    z.extractall(extract_dir)
                bat = os.path.join(tempfile.gettempdir(), "update_lumina.bat")
                exe = os.path.join(app_dir, "LuminaChat.exe")
                with open(bat, "w", encoding='utf-8') as f:
                    f.write(f'@echo off\ntimeout /t 4 /nobreak >nul\n')
                    f.write(f'xcopy /s /y /i "{extract_dir}\\*" "{app_dir}"\n')
                    f.write(f'start "" "{exe}"\n')
                    f.write(f'rmdir /s /q "{extract_dir}"\n')
                    f.write(f'del /f /q "{zip_path}"\n')
                    f.write(f'del /f /q "%~f0"\n')
                subprocess.Popen(["cmd", "/c", bat], shell=True, creationflags=subprocess.CREATE_NEW_CONSOLE)
                QApplication.instance().quit()
            else:
                QMessageBox.information(None, "Update", "Nova versao baixada. Reinicie o app.")
        except Exception as e:
            QMessageBox.critical(None, "Erro", "Falha ao instalar: " + str(e))

# ============ BRIDGE ============
class Bridge(QObject):
    notify = pyqtSignal(str, str, str)
    badge = pyqtSignal(int)
    flash = pyqtSignal()

# ============ TITLE BAR (100% OPACA) ============
class TitleBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.drag_pos = None
        self.setFixedHeight(32)
        self.setStyleSheet("""
            TitleBar {
                background-color: #0a081e;
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
                border-bottom: 1px solid rgba(139, 92, 246, 0.15);
            }
            QLabel {
                color: #c4b5fd;
                font-family: 'Segoe UI', sans-serif;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton {
                background: transparent;
                color: #a5b4fc;
                border: none;
                font-size: 14px;
                font-weight: bold;
                width: 38px;
                height: 32px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: rgba(139, 92, 246, 0.25);
                color: #e0e7ff;
            }
            QPushButton#closeBtn:hover {
                background-color: #ef4444;
                color: white;
            }
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 6, 0)
        layout.setSpacing(2)

        icon_path = resource_path("Icon.ico")
        if os.path.exists(icon_path):
            ico = QLabel()
            ico.setPixmap(QPixmap(icon_path).scaled(22, 22, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            layout.addWidget(ico)
        layout.addSpacing(10)

        layout.addWidget(QLabel("Lumina Chat"))
        layout.addStretch()

        self.btn_min = QPushButton("\u2014")
        self.btn_min.setToolTip("Minimizar")
        self.btn_min.clicked.connect(parent.showMinimized)
        layout.addWidget(self.btn_min)

        self.btn_max = QPushButton("\u25a1")
        self.btn_max.setToolTip("Maximizar")
        self.btn_max.clicked.connect(self._toggle_max)
        layout.addWidget(self.btn_max)

        self.btn_close = QPushButton("\u2715")
        self.btn_close.setObjectName("closeBtn")
        self.btn_close.setToolTip("Fechar")
        self.btn_close.clicked.connect(parent._force_quit)
        layout.addWidget(self.btn_close)

    def _toggle_max(self):
        if self.parent.isMaximized():
            self.parent.showNormal()
            self.btn_max.setText("\u25a1")
        else:
            self.parent.showMaximized()
            self.btn_max.setText("\u2750")

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self.drag_pos = event.globalPos() - self.parent.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        if event.buttons() == Qt.LeftButton and self.drag_pos is not None:
            if self.parent.isMaximized():
                self.parent.showNormal()
            self.parent.move(event.globalPos() - self.drag_pos)
            event.accept()

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        self._toggle_max()

# ============ LOADING SCREEN ============
class LoadingScreen(QWidget):
    finished = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            LoadingScreen {
                background-color: #110f36;
            }
        """)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        self.card = QWidget()
        self.card.setFixedSize(640, 720)
        self.card.setStyleSheet("""
            QWidget {
                background-color: #110f36;
                border-radius: 24px;
                border: none;
            }
        """)
        card_layout = QVBoxLayout(self.card)
        card_layout.setAlignment(Qt.AlignCenter)
        card_layout.setSpacing(20)
        card_layout.setContentsMargins(40, 50, 40, 50)

        # Icone
        self.icon_label = QLabel()
        self.icon_label.setAlignment(Qt.AlignCenter)
        self.icon_label.setFixedSize(180, 180)

        self.img_normal = self._load_img("Icon.png")
        self.img_dizzy = self._load_img("Icon_dizzy.png")
        if self.img_dizzy is None:
            self.img_dizzy = self.img_normal

        if self.img_normal:
            self.icon_label.setPixmap(self.img_normal)
        card_layout.addWidget(self.icon_label, alignment=Qt.AlignCenter)

        # === LABEL 1: Titulo principal ===
        self.text_label = QLabel("Verificando atualizacoes...")
        self.text_label.setAlignment(Qt.AlignCenter)
        self.text_label.setWordWrap(True)
        self.text_label.setMinimumWidth(500)
        self.text_label.setStyleSheet("""
            font-size: 20px;
            color: #a5b4fc;
            letter-spacing: 0.5px;
            font-weight: 600;
            font-family: 'Segoe UI', sans-serif;
        """)
        card_layout.addWidget(self.text_label, alignment=Qt.AlignCenter)

        # === LABEL 2: Status fixo (offline/erro) ===
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setWordWrap(True)
        self.status_label.setMinimumWidth(500)
        self.status_label.setStyleSheet("""
            font-size: 14px;
            color: #818cf8;
            font-family: 'Segoe UI', sans-serif;
        """)
        card_layout.addWidget(self.status_label, alignment=Qt.AlignCenter)

        # === LABEL 3: Frases engracadas ===
        self.phrase_label = QLabel("")
        self.phrase_label.setAlignment(Qt.AlignCenter)
        self.phrase_label.setWordWrap(True)
        self.phrase_label.setMinimumWidth(500)
        self.phrase_label.setStyleSheet("""
            font-size: 13px;
            color: #a5b4fc;
            font-family: 'Segoe UI', sans-serif;
            font-style: italic;
            padding-top: 8px;
            line-height: 1.5;
        """)
        card_layout.addWidget(self.phrase_label, alignment=Qt.AlignCenter)

        layout.addWidget(self.card, alignment=Qt.AlignCenter)

        self._phrase_timer = QTimer(self)
        self._phrase_timer.timeout.connect(self._rotate_phrase)
        self._elapsed = None

    def _load_img(self, name):
        png_path = resource_path(name)
        if os.path.exists(png_path):
            pm = QPixmap(png_path)
            if not pm.isNull():
                if pm.width() > 180 or pm.height() > 180:
                    pm = pm.scaled(180, 180, Qt.KeepAspectRatio, Qt.FastTransformation)
                return pm
        ico_name = name.replace('.png', '.ico')
        ico_path = resource_path(ico_name)
        if os.path.exists(ico_path):
            icon = QIcon(ico_path)
            pm = icon.pixmap(180, 180)
            if not pm.isNull():
                return pm
        return None

    def start_animation(self):
        self.text_label.setText("Verificando atualizacoes...")
        self.status_label.setText("")
        self.phrase_label.setText("")
        self._elapsed = QElapsedTimer()
        self._elapsed.start()
        if self._phrase_timer.isActive():
            self._phrase_timer.stop()
        self._rotate_phrase()
        self._phrase_timer.start(6000)
        QTimer.singleShot(3000, self._bounce_dizzy)

    def _rotate_phrase(self):
        if self._elapsed and self._elapsed.elapsed() > 60000:
            phrase = random.choice(FRASES_LENTO)
        else:
            phrase = random.choice(FRASES_NORMAL)
        self.phrase_label.setText(phrase)

    def show_offline(self):
        self.text_label.setText("Tentando Novamente...")
        self.status_label.setText("O servidor esta offline")
        if self.img_dizzy:
            self.icon_label.setPixmap(self.img_dizzy)
        if not self._phrase_timer.isActive():
            self._phrase_timer.start(6000)

    def _bounce_dizzy(self):
        if self.img_dizzy:
            self.icon_label.setPixmap(self.img_dizzy)
        self.text_label.setText("Quase la...")
        self.status_label.setText("")
        self._phrase_timer.stop()

        self._anim = QPropertyAnimation(self.card, b"pos")
        start = self.card.pos()
        self._anim.setDuration(700)
        self._anim.setEasingCurve(QEasingCurve.OutBounce)
        self._anim.setStartValue(start)
        self._anim.setKeyValueAt(0.4, QPoint(start.x(), start.y() - 60))
        self._anim.setEndValue(start)
        self._anim.start()

        QTimer.singleShot(1200, self.finished.emit)

    def show_error(self, msg):
        self.status_label.setText(msg)
        self.status_label.setStyleSheet("""
            font-size: 14px;
            color: #f87171;
            font-family: 'Segoe UI', sans-serif;
        """)

    def stop_phrases(self):
        self._phrase_timer.stop()

# ============ MAIN WINDOW ============
class LuminaClient(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Lumina Chat")
        self.setWindowFlags(Qt.FramelessWindowHint)
        # REMOVIDO: WA_TranslucentBackground
        self.setStyleSheet("background-color: #0a081e;")
        self.resize(1280, 800)

        self.central = QWidget()
        self.central.setStyleSheet("background-color: #0a081e;")
        self.setCentralWidget(self.central)
        self.layout = QVBoxLayout(self.central)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        self.title_bar = TitleBar(self)
        self.layout.addWidget(self.title_bar)

        self.stack = QStackedWidget()
        self.stack.setStyleSheet("background-color: #0a081e;")
        self.layout.addWidget(self.stack)

        self.loading = LoadingScreen()
        self.stack.addWidget(self.loading)

        self.web_container = QWidget()
        self.web_container.setStyleSheet("background-color: #0f0f12;")
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
        if getattr(self, '_page_ok', False):
            self.loading.stop_phrases()
            self.updater.check()

    def _on_load_finished(self, ok):
        if ok:
            check_js = """
            (function(){
                var hasApp = document.getElementById('app') !== null;
                var hasAuth = document.querySelector('.auth-screen') !== null;
                var title = document.title || '';
                var body = document.body ? document.body.innerText : '';
                var isError = title.toLowerCase().indexOf('error') !== -1 
                    || body.indexOf('502') !== -1 
                    || body.indexOf('ERR_') !== -1
                    || body.indexOf('nao consegue atender') !== -1
                    || document.querySelector('.error-code') !== null;
                return {hasApp: hasApp, hasAuth: hasAuth, isError: isError, title: title};
            })()
            """
            self.browser.page().runJavaScript(check_js, self._on_page_check)
        else:
            self._handle_offline()

    def _on_page_check(self, result):
        if result and result.get('isError'):
            self._handle_offline()
        elif result and (result.get('hasApp') or result.get('hasAuth')):
            self._page_ok = True
            self._inject_bridge()
            QTimer.singleShot(400, lambda: self.stack.setCurrentWidget(self.web_container))
        else:
            self._handle_offline()

    def _handle_offline(self):
        self._page_ok = False
        self.loading.show_offline()
        QTimer.singleShot(5000, lambda: self.browser.reload())

    def _inject_bridge(self):
        js = """
        (function(){
            if(window.quizcordNative)return;
            window.quizcordNative={
                showNotification:function(t,b,c){if(window.pybridge&&window.pybridge.notify)window.pybridge.notify(t,b,c||"#a78bfa");},
                setBadge:function(n){if(window.pybridge&&window.pybridge.setBadge)window.pybridge.setBadge(n);},
                flashWindow:function(){if(window.pybridge&&window.pybridge.flash)window.pybridge.flash();},
                getPlatform:function(){return"windows";},
                getVersion:function(){return"1.1.0";}
            };
            window.dispatchEvent(new CustomEvent("quizcord-native-ready",{detail:{platform:"windows",version:"1.1.0"}}));
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
        self.tray.setToolTip("Lumina Chat (" + str(count) + " nao lidas)" if count > 0 else "Lumina Chat")

    def _flash_window(self):
        if self.isMinimized() or not self.isActiveWindow():
            self.setWindowState(self.windowState() & ~Qt.WindowMinimized | Qt.WindowActive)
            self.raise_()
            self.activateWindow()

    def _on_update_check(self, has_update, version, url, notes_or_error):
        if has_update:
            notes = notes_or_error or "Novas melhorias disponiveis!"
            reply = QMessageBox.question(self, "Atualizacao Disponivel",
                "Nova versao <b>" + version + "</b> disponivel!\n\n" + notes + "\n\nDeseja atualizar agora?",
                QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.updater.download_and_install(url)
        else:
            if notes_or_error:
                print("[Updater] Erro:", notes_or_error)

    def closeEvent(self, event):
        event.ignore()
        self.hide()
        if self.tray:
            self.tray.showMessage("Lumina Chat", "O app continua rodando na bandeja.", QSystemTrayIcon.Information, 2000)

    def _force_quit(self):
        self.tray.hide()
        QApplication.instance().quit()

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Lumina Chat")
    app.setApplicationDisplayName("Lumina Chat")
    app.setFont(QFont("Segoe UI", 10))

    single = SingleInstance(APP_ID)
    if single.is_running:
        QMessageBox.information(None, "Lumina Chat", "Lumina Chat ja esta aberto!")
        sys.exit(0)

    window = LuminaClient()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
