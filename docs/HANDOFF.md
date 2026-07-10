# 象棋 AI 交接文件 — px0 強權重 + 自製 MCTS

> 給接手的 Ubuntu session：這份文件說明「這幾天在 Windows 上做了什麼、為什麼這樣決策、結果如何、以及你在 Ubuntu 上要怎麼接下去部署」。
> 讀完你就能在 Ubuntu 把這套跑起來，並繼續做交大 z-index 線性棋力系統。

---

## 0. 一句話總結

原本要從零訓練 AlphaZero 象棋網路（單張 4070 Ti Super），**嚴謹驗證後確認算力不足、練不出真棋力**。改採「**借 PikaXiangqiZero（px0，lc0 的象棋 fork）的強權重當評估器，跑在使用者自己的 PUCT MCTS 上**」。目前 Windows 上端到端打通、已驗證正確、對自家 Rust 引擎（alpha-beta + TT）**depth-2/4 100% 勝、depth-6 壓制中**。最終架構就是 **MCTS**（使用者硬需求，要接交大吳毅成 z-index 線性棋力系統）。

---

## 1. 使用者的目標與硬約束

- **最終架構必須是 MCTS**：使用者要用它做交大（NCTU 吳毅成）的 z-index 線性棋力調整系統（`best_move_mcts_strength`，用 sims/溫度/visit 當棋力旋鈕）。NNUE（Pikafish 那種 value-only alpha-beta）不行。
- 只動 `alphazero/`（Python）。Rust（engine/server/frontend）、C++（cpp-port）是別條線，除了幫 engine 加對手守護程序外沒動核心。
- 產出要能交給 prod/部署（就是你，Ubuntu session）。

---

## 2. 發展歷程與關鍵決策（怎麼走到這裡）

### 階段 A：從零訓練 AlphaZero（失敗，但已嚴謹證實）
- 環境：`alphazero/.venv`（Python 3.13 + torch cu124），4070 Ti Super。
- 做了：斷點續訓、多 worker 平行自對弈、批次葉評估 MCTS（`visit_distribution_batched`）、材料裁決給 value 訊號。
- **純 self-play** 練到 iter ~50 毫無棋力（全和 → value 頭空轉）。
- 改 **課程學習**（AZ vs Rust alpha-beta 老師）→ 冷啟動解除但仍卡。
- 改 **監督式模仿 / DAgger / 混合對手 DAgger**（`imitate.py`）→ match% 衝到 99%，但**是過擬合**：held-out match 才 16%，隨機開局實測 vs depth-2 才 10%。
- **關鍵教訓**：評測一定要**隨機開局**，否則確定性引擎 + 近確定網路會重複同一盤，勝率數字全是騙人的（我們一度被假數字誤導）。
- **決策（使用者拍板）**：從零訓練這條在此算力下不到位（AlphaZero 是數百萬局的尺度，我們是數千局）。轉向「借現成強權重」。

### 階段 B：找強權重 → 決定用 px0
- 使用者要的是「**能跑在我這套 MCTS 的權重**」，並提出關鍵洞見：「**用它的權重，把輸入改成跟它一樣**」。
- 選定 `official-pikafish/px0`（lc0 對象棋的 fork）+ 其權重庫 `official-pikafish/pxzero-networks`（294 顆雜湊命名網路，21MB~503MB）。

### 階段 C：編 px0 綁定（Windows 一堆坑，已全解）
見第 5 節「踩過的坑」。結論：**成功編出 Python 綁定 + lc0.exe**。

### 階段 D：發現 C++ 神經後端不能用 → 改走 ONNX（正解）
- **px0 這個 fork 的 C++ 神經後端（blas / cuda / cudnn）全是「沒 port 的西洋棋 8×8=64 碼」**：`network_blas.cc`/`network_cuda.cc` 到處寫死 `kSquares=64`、winograd 8×8 tile、attention `64×64`、expandPlanes `index>>6 / &0x3F / n*8*8`。象棋是 9×10=90 → 緩衝越界 segfault / 算錯。
- 只有 **onnx / tf / xla** 後端才移植成象棋 9×10。
- **正解**：用 px0 內建的 `leela2onnx` 把權重轉成 `.onnx`（`converter.cc` 是象棋感知的，90/9×10），再交給 **onnxruntime** 跑。完全繞過沒 port 的 C++ 後端。

### 階段 E：接上使用者的 MCTS + 除錯 + 驗證棋力
見第 3、4、6 節。

---

## 3. 最終架構（就是這個）

```
使用者盤面 Board (alphazero/xiangqi/board.py)
   │  board_to_px0_fen()：擺放與 px0 kStartposFen 完全一致，只補 "w|b - - 0 1"
   ▼
px0 綁定 GameState（帶最近 8 步歷史）
   │  as_input().expand() → 124×90 float 輸入平面（C++ 端展開，保住 90 位）
   │  moves() / policy_indices()：純棋規，著法 ↔ 2062 維 policy 索引對齊
   ▼
onnxruntime 前向（net_*.onnx，經 leela2onnx 轉換）
   │  輸出 /output/policy [2062]、/output/wdl [3]、/output/mlh [1]
   ▼
Px0Evaluator (alphazero/px0_eval.py)
   │  priors = 我方 legal 著法上 softmax；value = wdl.win - wdl.loss（走子方視角）
   ▼
使用者的 PUCT MCTS (alphazero/mcts.py: puct_search_batched / visit_distribution_batched)
   ▼
選步 → 之後接交大 z-index 線性棋力
```

**評估器介面**（與原 `nn_eval.NNEvaluator` 相同，可直接插進 MCTS）：
`evaluator(board, legal) -> (priors: dict[move->float], value: float)`、`evaluator.batch([...]) -> [...]`。

---

## 4. 映射細節（已實測驗證，`verify_px0_mapping.py`：11993 局面 0 失敗）

- **FEN**：`board.to_fen()` 的棋子擺放與 px0 `kStartposFen` 逐字一致（同方向、同字元 RNBAKC P 紅大寫黑小寫、10 列由上到下）。只需補尾欄 → `"<擺放> w - - 0 1"`（w=紅走、b=黑走）。
- **著法字串**：px0 `Move::ToString()` = from+to，每格 = `('a'+file)('0'+rank)`，如 `"b2b9"`。
  - **px0_file = 我方 x(0..8)、px0_rank = 9 - 我方 y(0..9)**，兩色通用（px0 黑走時內部 Mirror 只翻 rank 不翻 file）。與標準 UCCI 一致（紅炮起手在 b2/h2）。
- **policy**：`gs.moves()[i] ↔ gs.policy_indices()[i] ↔ onnx policy[idx]` 三者索引對齊。象棋 policy 是 **2062 維**（不是西洋棋的 1858）。
- **value**：px0 WDL 與使用者 MCTS 契約同為「**走子方視角 [-1,1]、越大越好**」，`value = W - L`，**免翻號**。

---

## 5. 踩過的坑（血淚知識，Ubuntu 部署也要知道）

1. **C++ 神經後端沒 port**（見階段 D）→ 不要試著編 blas/cuda，走 onnx。
2. **綁定 `evaluate` 是變參**（METH_FASTCALL）：要 `b.evaluate(inp)` 不是 `b.evaluate([inp])`（傳 list 會 reinterpret_cast 成垃圾指標 segfault）。**但我們最後根本不用綁定的 evaluate**（走 onnx）。
3. **綁定 `Input.mask(i)` 只有 64 位**（原本 `static_cast<uint64_t>`）→ 象棋 90 格的第 64-89 格被截斷。**解法**：在 `src/python/weights.h` 幫 `Input` 加了 `expand()`，C++ 端（`__uint128_t` 正常）展開成 124×90 的 **raw float32 bytes**，Python `np.frombuffer` 零轉換讀。（見 patch）
4. **網路要吃 8 步歷史平面**：lc0 輸入 = 最近 8 局面（每 15 plane：14 棋子 ours/theirs + 1 重複）×8 + 4 aux（120=we_are_black、121=rule50、122=movecount、123=全 1 邊界）= 124。只給當前局面（`GameState(fen)` 無歷史）→ 中局 value 每步 ±0.9 亂跳。**解法**：`Px0Evaluator._make_gamestate` 用 `board.move_stack` 回溯 8 步重建帶歷史的 GameState。
5. **21MB 網路（`d9472fa...`）是壞的**：WDL 頭給垃圾（startpos draw 機率 1.5%、對稱局面 value ±0.93——數學上不可能）。**33MB（`fcd86ede...`）以上正常**。決定性檢查：對稱局面 value 必須 ≈0。**用 33MB 以上**。
6. **batch_size 太大毀搜尋**：批次 MCTS 的虛擬損失（-1/訪問）在 batch=64 時把 visit 攤成「每個都 64」（等於沒搜尋）。**batch=4→h2e2 得 260/400（強力集中）、batch=8→152/120**。對弈/評測用 **batch_size=8**；batch=64 只適合純吞吐 benchmark。
7. **大網路（≥150MB）讓綁定 `backends.Weights(path)` segfault**（21/33MB 正常；lc0.exe/leela2onnx 載得動）。**解法**：編碼器與權重解耦——`Px0Evaluator` 用 `backends.Backend(backend="trivial")`（免權重，input_format 仍=1），推論全交給 onnx。綁定只負責「輸入編碼 + 著法索引」。
8. **評測要隨機開局**（`rand_open`）否則勝率是假的（見階段 A）。
9. **（Windows 特有，Ubuntu 不會遇到）**：MSVC 沒有原生 `__uint128_t`（用 `std::_Unsigned128`）→ weights.h 要 `static_cast`；cp314 vs python313.dll tag、DLL 靜態連結、meson native file 強制 python 3.13、CUDA 13.3 太新讓 network_cuda.cc 編不過 + cutlass 2.11 不相容……**這些在 Ubuntu/gcc 全部不存在**（gcc 原生 `__uint128_t`）。

---

## 6. 目前結果（棋力）

對手：自家 Rust 引擎 `oppd.exe`（negamax alpha-beta + 置換表 TT + MVV-LVA，交大 z-index 那條線的引擎）。
px0 側：**33MB 網路 + 400 sims + batch=8 + 隨機開局**。

| 對手 | 結果 |
|---|---|
| Rust depth-2 | **8 勝 0 負（100%）** |
| Rust depth-4 | **6 勝 0 負（100%）** |
| Rust depth-6 | 壓制中（見 `eval_d6b.log`，乾淨環境下開局連勝） |

對比：使用者自己從零訓練的網路連 depth-2 都 0%。→ **px0 權重 + 自製 MCTS 完勝那條路**。

速度（4070 Ti Super）：
- **33MB**：~0.5 秒/步（400 sims，DirectML）—— 快、夠強、適合互動對弈與 z-index。
- **150MB**：~5 秒/步 —— 更強天花板但慢 10×。**Ubuntu + NVIDIA CUDA onnxruntime 會比 Windows DirectML 快**，150MB 在你那邊可能就夠用。

---

## 7. 檔案清單

### 在 chinese-chess repo（本 repo，已 commit）
- `alphazero/px0_eval.py` — **核心評估器** `Px0Evaluator(onnx_path, providers)`（介面同 NNEvaluator）。
- `alphazero/verify_px0_mapping.py` — FEN + 著法映射驗證（11993 局面 0 失敗）。
- `alphazero/eval_px0_vs_oppd.py` — 對 Rust oppd 隨機開局勝率評測。
- `alphazero/mcts.py`（沿用）— PUCT MCTS，`puct_search_batched` / `visit_distribution_batched`。
- `alphazero/xiangqi/board.py`、`encode.py`（沿用）— 象棋盤面/規則。
- `engine/src/bin/oppd.rs`、`engine/src/search.rs`（TT）— Rust 對手守護程序 + 加速。
- `docs/px0-xiangqi-python.patch` — **px0 的三個修改**（見下）。
- `build_*.bat` — Windows 建置腳本（Ubuntu 用不到，僅參考建置參數）。

### px0 的修改（在 `docs/px0-xiangqi-python.patch`，Ubuntu 要套用）
基底 commit：`official-pikafish/px0` @ `d1b7bf2`。三個檔：
- `src/python/weights.h`：`Input::expand()`（展開成 raw float32 bytes）+ `mask()` 的 `static_cast`（Windows 用，gcc 無妨）+ `Move::ToString()` 無參修正。
- `scripts/pybind/retval.py`：新增 `BytesRetVal`（`Py_BuildValue("y#", ...)`）。
- `scripts/gen_py_bindings.py`：註冊 `input.AddMethod('expand').AddRetVal(BytesRetVal())`。

### 不進 git（可重生，太大）
- `px0/nets/*.pb.gz`（權重，從 pxzero-networks release 下載）、`px0/nets/*.onnx`（leela2onnx 轉出）、`checkpoints*`、`*.log`、`px0/builddir/`。

---

## 8. Ubuntu 部署步驟（你要做的）

### 前置
```bash
# 1) Python 環境
python3 -m venv .venv && source .venv/bin/activate
pip install numpy onnxruntime-gpu   # 有 NVIDIA GPU；否則 onnxruntime(CPU)

# 2) 取得權重（pxzero-networks release，用 33MB 或更大；別用 21MB=壞的）
#    用 GitHub API 拿 browser_download_url，例：33MB = fcd86ede...
#    存成 net.pb.gz
```

### 產生 .onnx（需要 px0 的 leela2onnx，一次性）
```bash
git clone https://github.com/official-pikafish/px0 && cd px0
git checkout d1b7bf2
git apply /path/to/docs/px0-xiangqi-python.patch   # 套用我們的三個修改
# Linux 建置（比 Windows 簡單，gcc 原生支援 __uint128_t）：
meson setup build -Dpython_bindings=true -Dlc0=true -Dblas=true   # 至少一個後端讓 lc0.exe 能編
ninja -C build lc0
./build/lc0 leela2onnx --input=net.pb.gz --output=net.onnx
```

### 兩條路讓「輸入編碼 + 著法索引」在 Ubuntu 可用

- **路 A（簡單）：重編 px0 綁定**（上面 `ninja -C build` 加 `backends` target），得到 Linux 的 `backends.*.so`。`Px0Evaluator` 照用（`px0_eval.py` 的 `_PX0_BUILDDIR` 指到 build 目錄）。
- **路 B（最乾淨，推薦給 prod）：純 Python 重寫輸入編碼 + 著法索引**，整套零 C++ 相依，只要 `board.py + mcts.py + px0_eval_pure.py + onnxruntime + net.onnx`。
  - 需重寫兩件事（規格見第 4 節 + px0 `src/neural/encoder.cc` 的 `EncodePositionForNN` 和 `MoveToNNIndex`）：
    1. 124-plane 輸入編碼（14 棋子 ours/theirs ×8 歷史 + 重複 plane + 4 aux；歷史有 flip 交替）。
    2. 著法 → 2062 維 policy 索引（`MoveToNNIndex`）。
  - **這份 Windows session 還沒做 B**（目前用綁定）。如果要 B，可以叫這個 Windows session 幫忙把 encoder.cc 的 `MoveToNNIndex` 讀出來、產出純 Python 版本 + 用綁定當「golden reference」逐局面比對驗證。

### 跑起來
```python
from px0_eval import Px0Evaluator
from mcts import puct_search_batched
from xiangqi.board import Board
nn = Px0Evaluator("net.onnx")          # 自動選 GPU(CUDA/DML)→CPU
b = Board.start()
mv = puct_search_batched(b, nn, sims=400, batch_size=8)   # batch_size=8 很重要
```

---

## 9. 待辦 / 下一步

1. **接交大 z-index 線性棋力**：用 sims / 溫度 / visit 分佈當棋力旋鈕（`best_move_mcts_strength`）。這是最終目標。
2. **選網路大小**：33MB 快又夠強（壓 depth-6）；要更強天花板可上 150MB / 400MB（Ubuntu CUDA 夠快的話）。
3. **（推薦）路 B 純 Python 化**：讓部署零 C++ 相依。
4. 可選：把 batch/sims/溫度做成設定，接到現有 server/frontend。

---

## 10. 給 Ubuntu session 的重點提醒（TL;DR）

- **架構是 MCTS**（`puct_search_batched`），評估器 `Px0Evaluator` 只是把 px0 的 onnx 當 policy+value 來源。別把它退化成 alpha-beta/NNUE。
- **一定用 batch_size=8**（不是 64，會毀搜尋）。
- **別用 21MB 網路**（壞的），33MB 以上。驗證健康：對稱局面 value 要 ≈0。
- **評測一定隨機開局**（`rand_open`），否則勝率是假的。
- **輸入要帶 8 步歷史**（`_make_gamestate` 已處理；若走純 Python 路 B 要自己實作歷史）。
- Linux 沒有 Windows 那些 MSVC/CUDA-13/DLL 坑，建置會順很多。
- 映射（FEN / 著法 / value）已用 `verify_px0_mapping.py` 驗過 11993 局面 0 失敗，可信；Ubuntu 上重建後**務必再跑一次驗證**。
