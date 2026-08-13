import sys
from PyQt5.QtWidgets import QApplication, QMainWindow
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEnginePage
from PyQt5.QtCore import QUrl

RENDER_URL = "https://quizcord.onrender.com"  # troque pelo seu

class MainWindow(QMainWindow):
    def __init__(self, url):
        super().__init__()
        self.setWindowTitle("Quizcord")
        self.setGeometry(100, 100, 1280, 800)

        self.browser = QWebEngineView()
        
        # Permite notificações desktop no WebEngine
        self.browser.page().featurePermissionRequested.connect(self.on_permission)
        
        self.browser.setUrl(QUrl(url))
        self.setCentralWidget(self.browser)

    def on_permission(self, url, feature):
        if feature == QWebEnginePage.Notifications:
            self.browser.page().setFeaturePermission(
                url, feature, QWebEnginePage.PermissionGrantedByUser
            )

def start_app(url):
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    window = MainWindow(url)
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    start_app(RENDER_URL)