"""中國象棋 px0 桌面版（Windows / macOS / Linux）—— 包「網頁版」。

用 px0 強權重（經 ONNX）+ 自製 PUCT MCTS，跑線上同一套網頁對弈服務 serve_az.py
（aiohttp WebSocket + Phaser 前端 frontend/dist，4 難度 + 交大 z-index 1~100 拉霸），
pywebview 開視窗載入。零 torch、GPU 走 onnxruntime(-directml)。權重不打包，首次啟動下載。

執行（開發，需先 build 前端 → frontend/dist）：
    pip install pywebview aiohttp onnxruntime numpy
    (cd ../frontend && npm install && npm run build)
    PX0_ONNX=../px0/nets/net_33mb.onnx python app_px0.py
打包見 .github/workflows/build-desktop-px0.yml（CI：node build 前端 + PyInstaller 三平台）。
"""

from __future__ import annotations

import os
import sys
import threading
import time

if getattr(sys, "frozen", False):
    _BASE = sys._MEIPASS  # type: ignore[attr-defined]
    _AZ = os.path.join(_BASE, "alphazero")
    _STATIC = os.path.join(_BASE, "frontend", "dist")
    _ONNX = os.path.join(os.path.expanduser("~"), ".xiangqi-px0", "net.onnx")
else:
    _HERE = os.path.dirname(os.path.abspath(__file__))
    _AZ = os.path.join(os.path.dirname(_HERE), "alphazero")
    _STATIC = os.path.join(os.path.dirname(_HERE), "frontend", "dist")
    _ONNX = os.environ.get(
        "PX0_ONNX", os.path.join(os.path.dirname(_HERE), "px0", "nets", "net_33mb.onnx"))

sys.path.insert(0, _AZ)
# serve_az 在 import 時就建 Px0Evaluator + 讀這些 env，故先設好
os.environ["CHESS_ONNX"] = _ONNX
os.environ["CHESS_STATIC"] = _STATIC
os.environ.setdefault("CHESS_BATCH", "8")
os.environ.setdefault(
    "PX0_ONNX_URL",
    "https://github.com/cin-yi-wei/chinese-chess/releases/download/weights/net.onnx",
)
PORT = int(os.environ.setdefault("CHESS_PORT", "8611"))


def ensure_onnx() -> None:
    if os.path.exists(_ONNX):
        return
    import urllib.request
    os.makedirs(os.path.dirname(_ONNX), exist_ok=True)
    url = os.environ["PX0_ONNX_URL"]
    print(f"下載權重 {url} -> {_ONNX}")
    urllib.request.urlretrieve(url, _ONNX)


def _run_server() -> None:
    # aiohttp 的 run_app 需主執行緒；背景執行改用 AppRunner + 自建事件迴圈。
    import asyncio
    from aiohttp import web
    import serve_az   # import 時載入 onnx（吃 CHESS_ONNX）

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    runner = web.AppRunner(serve_az.make_app())
    loop.run_until_complete(runner.setup())
    site = web.TCPSite(runner, "127.0.0.1", PORT)
    loop.run_until_complete(site.start())
    loop.run_forever()


def main() -> None:
    ensure_onnx()
    threading.Thread(target=_run_server, daemon=True).start()

    import urllib.request
    for _ in range(120):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=1)
            break
        except Exception:
            time.sleep(1)

    url = f"http://127.0.0.1:{PORT}/"
    try:
        import webview
        webview.create_window("中國象棋 · px0", url, width=640, height=760)
        webview.start()
    except Exception as e:
        print(f"pywebview 開視窗失敗（{e}），改用系統瀏覽器：{url}")
        import webbrowser
        webbrowser.open(url)
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
