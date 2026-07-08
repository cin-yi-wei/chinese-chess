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

# 讓 desktop/ 能匯入 alphazero/ 的引擎
_HERE = os.path.dirname(os.path.abspath(__file__))
_AZ = os.path.join(os.path.dirname(_HERE), "alphazero")
sys.path.insert(0, _AZ)

# 權重與靜態前端路徑（可用環境變數覆寫；打包時改指到 bundle 內）
os.environ.setdefault("CHESS_WEIGHTS", os.path.join(_AZ, "checkpoints", "latest.pt"))
os.environ.setdefault("CHESS_STATIC", os.path.join(os.path.dirname(_HERE), "frontend", "dist"))
os.environ.setdefault("CHESS_SIMS", "400")   # 有 GPU 可開大；純 CPU 建議調小
os.environ.setdefault("CHESS_BATCH", "32")

PORT = int(os.environ.get("CHESS_PORT", "8611"))

import webview  # noqa: E402
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

    webview.create_window("中國象棋 AlphaZero", f"http://127.0.0.1:{PORT}/", width=680, height=800)
    webview.start()


if __name__ == "__main__":
    main()
