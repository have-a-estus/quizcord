import sys
from PyQt5.QtWidgets import QApplication, QMainWindow
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtCore import QUrl

# ------------------------------------------------
# CONFIGURAÇÃO: coloque a URL do seu servidor Render
# ------------------------------------------------
RENDER_URL = "https://quizcord.onrender.com"  # altere para a URL real do seu deploy

# ------------------------------------------------
# JANELA PRINCIPAL PYQT
# ------------------------------------------------
class MainWindow(QMainWindow):
    """Janela principal que hospeda o QWebEngineView."""
    def __init__(self, url):
        super().__init__()
        self.setWindowTitle("Quizcord - Cliente Global")
        self.setGeometry(100, 100, 1024, 768)

        self.browser = QWebEngineView()
        self.browser.setUrl(QUrl(url))
        self.setCentralWidget(self.browser)

# ------------------------------------------------
# FUNÇÃO PARA INICIAR O APP
# ------------------------------------------------
def start_app(url):
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    window = MainWindow(url)
    window.show()
    sys.exit(app.exec_())

# ------------------------------------------------
# BLOCO PRINCIPAL
# ------------------------------------------------
if __name__ == "__main__":
    start_app(RENDER_URL)

