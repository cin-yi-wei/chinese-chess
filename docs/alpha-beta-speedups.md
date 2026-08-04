# Alpha-Beta 搜尋加速技術筆記（engine/src/search.rs）

> 記錄 chess 引擎 alpha-beta（negamax）用到的每個加速手段：做什麼、為什麼有效、怎麼驗證。
> 分兩類：**值保持**（不改變搜尋結果，只加快）與 **啟發式裁剪**（會改變結果，靠對打驗證不變弱）。
> 對應程式：`engine/src/search.rs`；對手守護 `engine/src/bin/oppd.rs`。

## 基底：Negamax Alpha-Beta
- 極大極小搜尋 + alpha-beta 剪枝。`evaluate()` 以走子方視角回分，遞迴對子節點取負（negamax）。
- alpha/beta 是「目前已知的下界/上界」；某手證明比 beta 好就直接剪枝（對手不會讓你走到）→ beta 截斷。
- 剪枝效率**極度依賴走子順序**：好步先搜，才會早早 beta 截斷。下面多數技術都在「讓好步先搜」或「少搜沒用的分支」。

---

## 值保持加速（結果不變，只加快）

### 1. 置換表 Transposition Table (TT)
- 同一個盤面可由不同著法順序到達（轉位）。用 **Zobrist hash** 當鍵，存 `(depth, value, flag, best)`。
- 命中且存的深度 ≥ 需求深度：依 flag（精確/下界/上界）可直接回傳或收窄窗口，省掉整棵子樹。
- 還提供「上次算出的最佳著法」給走子排序當第一順位。

### 2. 走子排序 Move Ordering
好步先搜 = 更早 beta 截斷。順位：
- **TT best move**：上次搜這局面的最佳步，最優先。
- **MVV-LVA**（Most Valuable Victim − Least Valuable Attacker）：吃子步中，吃大子、用小子吃的排前面（通常是好交換）。
- **Killer moves**：記每一層（ply）最近造成 beta 截斷的 2 個「靜著（非吃子）」，下次同層優先試——兄弟節點常有同樣的殺著。
- **History heuristic**：對「造成截斷的靜著」用 `history[from][to] += depth²` 累計，排序時分數高的先試——全域統計哪些走法常有用。

### 3. 靜態搜尋 Quiescence Search
- 問題：固定深度到葉子直接評估，會有**水平線效應**——正在連環吃子的中途停下數子，估值大錯。
- 解：depth 0 時不直接評估，而是**只繼續延伸「吃子」著法**直到盤面「平靜」（沒吃子可下）再評估。
- 有 stand-pat：先看不吃子的靜態分，已經 ≥ beta 就回；否則只試吃子步。上限 `MAX_QDEPTH=8` 防吃子鏈爆炸。
- 嚴格說改變了葉評估（更準），但對「同一套規則」是一致的，仍當值保持看待（測試參照同步含 quiescence）。

### 4. PVS 主變例搜尋 (Principal Variation Search)
- 假設走子排序夠好 → 第一手（主變例 PV）大概就是最佳。
- 第一手用**全窗**搜；其餘手先用**零窗**（`(alpha, alpha+1)`）快速探測「有沒有可能比 PV 好」。
- 探測若證明沒更好（大多數情況）→ 超便宜就否決掉；只有零窗探測意外落在窗內，才用全窗**重搜**那一手。
- 值保持：最終選擇與純 alpha-beta 相同，只是多數手用便宜的零窗擋掉。

---

## 啟發式裁剪（會改變結果，換更深/更快；靠對打驗證）

### 5. LMR 後期著法減深 (Late Move Reductions)
- 假設：排序夠好時，排在**後面**的著法多半是爛步，不值得搜滿深度。
- 對「靠後（idx≥3）、非吃子、非將軍中、depth≥3」的著法，先**減 1~2 層**淺搜。
- 若淺搜意外**高過 alpha**（可能是好步被低估）→ 補回**全深度重搜**，避免漏掉。
- 有風險（減深度可能誤判），故列為啟發式。

### （未做）Null-Move Pruning
- 概念：先「讓對手連走兩步」（自己跳過一手），若這樣還打不垮我方 beta，代表這局面很好、可大幅剪枝。
- 本引擎**尚未實作**：需要在 `board.rs` 加正確的 null-move（切換走子方 + 更新 Zobrist 側手雜湊 + 重複盤面處理），侵入性較高，之後要做再開。

---

## 開關與驗證
- `SearchState.heuristics` 旗標：production 開啟 PVS+LMR；單元測試關閉 → 走「精確核心」（TT+排序+quiescence，皆值保持）。
- 正確性測試 `tt_matches_plain_root_value`：比對「精確核心版」與「純 negamax（同樣含 quiescence）」的根節點搜尋值必須逐一相等 → 保證 TT/排序/PVS 沒把值算錯。
- 啟發式（LMR）的正確性不靠等值測試，靠**對打**確認不變弱。

## 實測效果
- depth-8 開局單步：**13.2 秒 → 1.49 秒（約 9×）**（加 PVS+LMR 前後）。
- 意義：同樣時間可多搜約 2~4 層（原 depth-8 的耗時 ≈ 現在 depth-11~12）。

## 演進 commit
- `727c68e`：quiescence + killer + history。
- `f44ffcc`：PVS + LMR（heuristics 旗標閘控）。
- 之前已有：TT + MVV-LVA + 迭代加深。
