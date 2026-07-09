"""中國象棋 AlphaZero 桌面版（三平台 Windows/macOS/Linux）。

作法：在本機起 aiohttp 對弈服務（複用 alphazero/serve_ws，torch 自動用本機 GPU），
用 pywebview 開一個桌面視窗載入現有 Phaser 前端。這樣桌面版與網頁版共用同一套
引擎與 UI；有 NVIDIA GPU 的機器推論會很快（每步 <1 秒）。

執行（在有 Python 的機器）：
    pip install -r requirements.txt
    python app.py            # 用 alphazero/checkpoints/latest.pt

打包成單一執行檔見 README（PyInstaller，各平台各打一份）。
"""

from __future__ import annotations

import os
import sys
import threading

# 路徑：開發時用 repo 相對路徑；PyInstaller 凍結後用解壓目錄 sys._MEIPASS。
# 權重不打包進執行檔——首次啟動從 GitHub Release 下載到使用者可寫目錄。
if getattr(sys, "frozen", False):
    _BASE = sys._MEIPASS  # type: ignore[attr-defined]
    _AZ = os.path.join(_BASE, "alphazero")
    _STATIC = os.path.join(_BASE, "frontend", "dist")
    _WEIGHTS = os.path.join(os.path.expanduser("~"), ".xiangqi-az", "latest.pt")
else:
    _HERE = os.path.dirname(os.path.abspath(__file__))
    _AZ = os.path.join(os.path.dirname(_HERE), "alphazero")
    _STATIC = os.path.join(os.path.dirname(_HERE), "frontend", "dist")
    _WEIGHTS = os.path.join(_AZ, "checkpoints", "latest.pt")

sys.path.insert(0, _AZ)
os.environ.setdefault("CHESS_WEIGHTS", _WEIGHTS)
os.environ.setdefault("CHESS_STATIC", _STATIC)
# 權重下載來源（GitHub Release 的 latest.pt 附件；換強腦只要重傳附件）
os.environ.setdefault(
    "CHESS_WEIGHTS_URL",
    "https://github.com/cin-yi-wei/chinese-chess/releases/download/weights/latest.pt",
)


def ensure_weight() -> None:
    """權重不存在就從 Release 下載。"""
    import urllib.request

    path = os.environ["CHESS_WEIGHTS"]
    if os.path.exists(path):
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    url = os.environ["CHESS_WEIGHTS_URL"]
    print(f"下載權重 {url} -> {path}")
    urllib.request.urlretrieve(url, path)
os.environ.setdefault("CHESS_SIMS", "400")   # 有 GPU 可開大；純 CPU 建議調小
os.environ.setdefault("CHESS_BATCH", "32")

PORT = int(os.environ.get("CHESS_PORT", "8611"))

from aiohttp import web  # noqa: E402


def _run_server() -> None:
    import asyncio
    import serve_ws  # 匯入時載入網路權重（吃 CHESS_WEIGHTS）

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    runner = web.AppRunner(serve_ws.make_app())
    loop.run_until_complete(runner.setup())
    site = web.TCPSite(runner, "127.0.0.1", PORT)
    loop.run_until_complete(site.start())
    loop.run_forever()


def main() -> None:
    ensure_weight()  # 權重先就位（serve_ws 匯入時會載入）
    t = threading.Thread(target=_run_server, daemon=True)
    t.start()
    # 等服務起來（載入 torch+權重需幾秒）
    import time
    import urllib.request

    for _ in range(60):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=1)
            break
        except Exception:
            time.sleep(1)

    url = f"http://127.0.0.1:{PORT}/"
    # 優先開原生視窗（pywebview）；失敗（如 Windows 的 pythonnet/clr 打包問題）就退回系統瀏覽器。
    try:
        import webview
        webview.create_window("中國象棋 AlphaZero", url, width=680, height=800)
        webview.start()
    except Exception as e:
        print(f"pywebview 開視窗失敗（{e}），改用系統瀏覽器開啟：{url}")
        import webbrowser
        import time
        webbrowser.open(url)
        # 保持行程存活（伺服器在背景執行緒），否則視窗/瀏覽器一開程式就結束
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
