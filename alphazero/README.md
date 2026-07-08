# AlphaZero 中國象棋（Python）

用 AlphaZero 式自我對弈訓練一個「真的強」的象棋 AI，取代主線那套弱 MCTS。
之後可用交大吳毅成團隊論文（`../reference/papers/`）的 strength index z 系統，把訓練好的強引擎往下調成 1~100 難度。

## 為何是 Python
ML 生態在 Python（PyTorch）。規則層從主線 Rust 引擎移植過來（已用「開局合法著法=44」驗證正確）。

## 分工 / 硬體
- **訓練在使用者的 Windows 機（RTX 4070 Ti Super）**——自我對弈 + 訓練吃 GPU，這台 Linux（CPU 弱、核顯）不訓練。
- 這台只用來開發 + CPU 小規模 smoke 驗證邏輯。
- 訓練產出的權重之後匯出，供對弈推論（web 端走 Python 推論 sidecar，或匯 ONNX）。

## 架構（AlphaZero）
1. 神經網路：policy + value 雙頭殘差 CNN，輸入=盤面多通道張量
2. PUCT MCTS：用 NN 的 value 取代隨機 rollout、prior 引導選點
3. 自我對弈訓練迴圈：自對弈產棋譜 → 訓練網路 → 更強網路再自對弈…反覆

## 進度（分階段）
- [x] Phase 1：象棋規則 `xiangqi/board.py`（合法著法、make/undo、將軍/將死、FEN）— CPU 驗證 44 著法
- [x] Phase 2：盤面編碼 `xiangqi/encode.py`（15×10×9 平面 + policy 索引 8100）+ 網路 `net.py`
- [x] Phase 3：PUCT MCTS `mcts.py`（NN 引導、評估器可插拔）
- [x] Phase 4：自我對弈 `selfplay.py` + 訓練迴圈 `train.py` + `config.py` + NN 評估器 `nn_eval.py`（在 4070TiS 上 `python train.py`）
- [ ] Phase 5：權重匯出 + 對弈推論整合到 web（chess-test 或新網址）

程式碼皆 py_compile 通過；純 Python 部分（規則/編碼/PUCT）在無 GPU 機實測過。
含 torch 的（net/nn_eval/train）待在 4070TiS 首次執行驗證。

## Windows GPU 訓練設定（Phase 4 用，先記著）
```
# 裝 CUDA 版 PyTorch（依 CUDA 版本挑指令，見 pytorch.org）
pip install -r requirements.txt
python -m alphazero.train   # 自我對弈+訓練（Phase 4 完成後）
```

## 本機（CPU）驗證
```
cd alphazero && python -m pytest tests/ -q
```
