# 中國象棋 AlphaZero 桌面版（三平台）

Windows / macOS / Linux 桌面應用。**複用**網頁版的引擎（`alphazero/`）與前端（`frontend/dist`）：
啟動時在本機跑對弈服務（`alphazero/serve_ws.py`），用 pywebview 開視窗顯示現有棋盤 UI。
有 NVIDIA GPU 的機器，torch 會自動用 GPU 推論，每步 <1 秒（不像那台 VM 只有 CPU）。

> 為何用「webview 殼 + 複用網頁」而非重寫原生 UI：省事、桌面/網頁同一套、之後只維護一份。
> 若要純原生棋盤（PySide6 畫）也可換，但工比較大。

## 開發執行（各平台自機，需 Python）
```
# 1) 前端先有 dist（在 repo 根）
cd frontend && npm install && npm run build && cd ..
# 2) 權重放 alphazero/checkpoints/latest.pt
# 3) 桌面版依賴（torch 有 GPU 裝 CUDA 版）
cd desktop && pip install -r requirements.txt
python app.py
```

## 打包成單一執行檔（PyInstaller，各平台各打一份）
在該平台上執行：
```
cd desktop
pyinstaller --noconfirm --windowed --name XiangqiAZ \
  --add-data "../frontend/dist:frontend/dist" \
  --add-data "../alphazero/checkpoints/latest.pt:checkpoints" \
  app.py
```
（Windows 的 --add-data 分隔符是 `;` 不是 `:`。打包後 app.py 需把 CHESS_STATIC / CHESS_WEIGHTS
指到 bundle 內的相對路徑——見 app.py 的環境變數，打包版再微調。）

## 硬體
- 有 NVIDIA GPU：CHESS_SIMS 可開 400~800+，每步 <1~2 秒、棋力好。
- 純 CPU：把 CHESS_SIMS 調小（如 96），每步約 10 秒。

## 狀態
- [x] 桌面殼 `app.py`（起 serve_ws + pywebview 視窗）+ requirements + 本說明
- [ ] 在真機（有顯示/ GPU）實跑驗證、微調視窗與打包（這步要在你的桌面環境做；開發機是無顯示的 VM）
- [ ] PyInstaller 三平台打包產物

備註：此 repo 的開發機是無顯示的 VM，GUI 沒法在這裡實跑；程式碼寫好給你在桌面環境跑/打包。
