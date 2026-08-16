import sys
import os
import json
import tempfile
import shutil
import zipfile
import urllib.request
import webview
import threading
import time

# ============ CONFIG ============
RENDER_URL = "https://luminachat.duckdns.org"
CURRENT_VERSION = "1.2.0"
UPDATE_URL = RENDER_URL + "/api/version"
DOWNLOAD_URL = RENDER_URL + "/static/download/LuminaChat.zip"

# ============ SINGLE INSTANCE ============
import ctypes
from ctypes import wintypes

def is_already_running():
    mutex_name = "Global\\LuminaChat_Mutex_v1"
    kernel32 = ctypes.windll.kernel32
    mutex = kernel32.CreateMutexW(None, False, mutex_name)
    last_error = kernel32.GetLastError()
    if last_error == 183:
        return True
    return False

def focus_existing_window():
    try:
        hwnd = ctypes.windll.user32.FindWindowW(None, "Lumina Chat")
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            ctypes.windll.user32.SetForegroundWindow(hwnd)
            return True
    except Exception:
        pass
    return False

# ============ UPDATER ============
def check_update():
    try:
        req = urllib.request.Request(UPDATE_URL, headers={"User-Agent": "LuminaChat-Updater/1.2"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        remote = data.get("version", "0.0.0")
        url = data.get("download_url", DOWNLOAD_URL)
        notes = data.get("release_notes", "")
        if _version_greater(remote, CURRENT_VERSION):
            return {"has_update": True, "version": remote, "url": url, "notes": notes}
    except Exception as e:
        print("[Updater] Erro:", e)
    return {"has_update": False}

def _version_greater(v1, v2):
    try:
        return [int(x) for x in v1.split(".")] > [int(x) for x in v2.split(".")]
    except:
        return False

# ============ API (Bridge Python <-> JS) ============
class LuminaAPI:
    def __init__(self, window):
        self.window = window
        self._badge = 0
        self._hidden = False
    
    def showNotification(self, title, body, color="#a78bfa"):
        try:
            from win10toast import ToastNotifier
            toaster = ToastNotifier()
            toaster.show_toast(title, body, duration=4, threaded=True)
        except ImportError:
            pass
        self.flashWindow()
    
    def setBadge(self, count):
        self._badge = count
        if self.window:
            if count > 0:
                self.window.set_title(f"Lumina Chat ({count})")
            else:
                self.window.set_title("Lumina Chat")
    
    def flashWindow(self):
        try:
            hwnd = self.window.native_handle if self.window else None
            if hwnd:
                ctypes.windll.user32.FlashWindow(ctypes.c_void_p(hwnd), True)
        except Exception:
            pass
    
    def getPlatform(self):
        return "windows"
    
    def getVersion(self):
        return CURRENT_VERSION
    
    def hideToTray(self):
        if self.window:
            self._hidden = True
            self.window.hide()
    
    def showFromTray(self):
        if self.window:
            self._hidden = False
            self.window.show()
            self.window.restore()
    
    def quitApp(self):
        if self.window:
            self.window.destroy()
        os._exit(0)

# ============ LOADING HTML ============
LOADING_HTML = """<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { background: #050310; color: #a5b4fc; font-family: 'Segoe UI', sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; overflow: hidden; }
.card { text-align: center; animation: fadeIn 0.5s ease; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }
.alpaca { width: 140px; height: 140px; margin-bottom: 24px; animation: float 4s ease-in-out infinite; }
@keyframes float { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-12px); } }
.title { font-size: 28px; font-weight: 700; background: linear-gradient(135deg, #ec4899, #8b5cf6, #06b6d4); -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin-bottom: 8px; }
.status { font-size: 14px; color: #6366f1; margin-bottom: 16px; }
.phrase { font-size: 13px; color: #a5b4fc; font-style: italic; min-height: 20px; transition: opacity 0.3s; }
.dots { display: flex; gap: 6px; justify-content: center; margin-top: 20px; }
.dot { width: 8px; height: 8px; border-radius: 50%; background: #8b5cf6; animation: dotPulse 1.4s ease-in-out infinite; }
.dot:nth-child(2) { animation-delay: 0.2s; }
.dot:nth-child(3) { animation-delay: 0.4s; }
@keyframes dotPulse { 0%, 60%, 100% { transform: scale(1); opacity: 0.4; } 30% { transform: scale(1.3); opacity: 1; } }
</style></head><body>
<div class="card">
<img src="https://luminachat.duckdns.org/static/cosmic_aero/alpaca_avatar.png" class="alpaca" alt="Lumina">
<div class="title">Lumina</div>
<div class="status" id="status">Verificando atualizacoes...</div>
<div class="phrase" id="phrase"></div>
<div class="dots"><div class="dot"></div><div class="dot"></div><div class="dot"></div></div>
</div>
<script>
const FRASES_NORMAL = ["A alpaca esta carregando. Ela nao sabe o que isso significa.","Espera! A alpaca esta pensando...","Quieto! Ela vai falar algo! Deixa pra la...","A culpa e da gravidade.","A alpaca esta contando estrelas...","Conectando os pontos cosmicos...","A alpaca esta ajustando o telescopio..."];
const FRASES_LENTO = ["Eu acho que a Alpaca bateu numa estrela.","Erro 418: alpaca virou bule.","Isso esta demorando tanto que Plutao foi promovido de novo.","Mano... Cade a Alpaca?","Estamos indo na velocidade da luz. Aparentemente ela nao e tao rapida assim.","A alpaca parou para tomar um chimarrao no espaco.","Acho que a Alpaca foi dar um passeio na Via Lactea."];
let startTime = Date.now();
function rotatePhrase() {
    const elapsed = Date.now() - startTime;
    const list = elapsed > 60000 ? FRASES_LENTO : FRASES_NORMAL;
    const phrase = list[Math.floor(Math.random() * list.length)];
    const el = document.getElementById('phrase');
    el.style.opacity = '0';
    setTimeout(() => { el.textContent = phrase; el.style.opacity = '1'; }, 300);
}
rotatePhrase();
setInterval(rotatePhrase, 6000);
</script></body></html>"""

# ============ MAIN ============
def main():
    if is_already_running():
        if focus_existing_window():
            print("[Lumina] Janela ja existe. Focando...")
        sys.exit(0)
    
    api = LuminaAPI(None)
    
    # Janela principal COM title bar do Windows (frameless=False)
    main_window = webview.create_window(
        title="Lumina Chat",
        html=LOADING_HTML,
        width=1280,
        height=800,
        min_size=(900, 600),
        resizable=True,
        frameless=False,
        easy_drag=False,
        on_top=False,
        js_api=api,
    )
    api.window = main_window
    
    def on_loaded():
        update_info = check_update()
        if update_info.get("has_update"):
            print(f"[Updater] Nova versao disponivel: {update_info['version']}")
        
        # Navegar para o app real apos 2s
        time.sleep(2)
        main_window.load_url(RENDER_URL)
    
    def on_shown():
        main_window.evaluate_js("""
            (function(){
                if(window.quizcordNative) return;
                window.quizcordNative = {
                    showNotification: function(t,b,c){ if(window.pywebview && window.pywebview.api) window.pywebview.api.showNotification(t,b,c||"#a78bfa"); },
                    setBadge: function(n){ if(window.pywebview && window.pywebview.api) window.pywebview.api.setBadge(n); },
                    flashWindow: function(){ if(window.pywebview && window.pywebview.api) window.pywebview.api.flashWindow(); },
                    getPlatform: function(){ return "windows"; },
                    getVersion: function(){ return "1.2.0"; },
                    hideToTray: function(){ if(window.pywebview && window.pywebview.api) window.pywebview.api.hideToTray(); },
                    showFromTray: function(){ if(window.pywebview && window.pywebview.api) window.pywebview.api.showFromTray(); }
                };
                window.dispatchEvent(new CustomEvent("quizcord-native-ready", {detail:{platform:"windows", version:"1.2.0"}}));
                console.log("[Native] Bridge pywebview injetado!");
            })();
        """)
    
    main_window.events.loaded += on_loaded
    main_window.events.shown += on_shown
    
    webview.start(
        debug=False,
        gui="edgechromium",
        http_server=False,
    )

if __name__ == "__main__":
    main()
