# C++ 原版象棋 — 交接文件（cpp-port）

給接手的新 session。這是「C 語言（C++/Qt）原版引擎」獨立線，與主線的 Rust 版**完全分離**。

## 目標
把 reference 的 Qt C++ 象棋引擎整理成獨立專案，接上一份網頁介面，最後上線到 **chess-testc.conray.top**。
**重點：MCTS 不准修** —— 使用者要自己 debug 蒙地卡羅的錯，任何人都不要改 `mcts.cpp` / `treenode.cpp` 的演算法邏輯。

## 目前狀態（已完成 step 1–2）
位置：`/home/conray/project/chinese-chess-dev/cpp-port/`

- **去 Qt 化完成**：原碼用 g++ -std=c++17 可編（QVector→std::vector、QStack→std::vector、QSet→std::set、移除 qDebug）。無需 Qt。
- **編得過、跑得動**：`cmake -B build -S . && cmake --build build` 產出 `build/cpp_engine`。
- **stdin/stdout JSON 介面**（新的 `main.cpp`），協定與主線 Rust server 相同，方便共用前端：
  - 輸入 `{"cmd":"new"}` → 回開局 state
  - 輸入 `{"cmd":"move","from":[x,y],"to":[x,y]}` → 套用人類(紅)著法 → AI(黑)用 **MCTS** 回手 → 回 state（含 `aiMove`）
  - state 形狀：`{"fen","redToMove","inCheck","legal":[[fx,fy,tx,ty]...],"aiMove":[..]?,"gameOver":"red"|"black"|null}`
  - 座標 x:0..8 檔、y:0..9 列；內部格 = (y+3)*16+(x+3)
- **smoke test 通過**：`printf '{"cmd":"new"}\n{"cmd":"move","from":[0,6],"to":[0,5]}\n' | ./build/cpp_engine` 會印兩行合法 JSON，AI 會用 MCTS 回手，EXIT=0。
  - ⚠️ MCTS 因保留原 bug，選步可能很怪/很慢，**這是預期的**（給使用者 debug 用）。

## 待辦（step 3，尚未做）
把 C++ 引擎接上網頁並上線 chess-testc，且**不得動主線 Rust 專案（engine/ server/ frontend/）與 chess-test**：
1. 寫一個**獨立**的薄橋接服務（別用主線 Rust server）。建議 Node.js（本機有 node v22）：`ws` 收前端 WebSocket、`child_process` 開 `cpp_engine` 子行程走 stdio JSON 轉發；同時 serve 一份複製的前端。或用獨立的小 Rust/其他，只要不碰主線。
2. 複製一份前端（可從 `frontend/` 複製到 `cpp-port/web/`）——前端協定已相容，理論上幾乎不用改。
3. 開一個新本機 port（例如 3940，別用 3939）。
4. cloudflared：既有獨立 tunnel `chinese-chess`(id 2247f8a8) 的 config 在 `~/.cloudflared/chinese-chess.yml`，**新增**一條 ingress `chess-testc.conray.top → http://127.0.0.1:<新port>`，並 `cloudflared tunnel route dns 2247f8a8-... chess-testc.conray.top`。或另開一條 tunnel。主線 chess-test 的設定不要動。

## 待驗證 / 注意
- 新 session 最好先 `diff` `cpp-port/{mcts,treenode}.{cpp,h}` 與 `reference/cpp-console/` 對應檔，確認**只有容器型別差異、演算法邏輯 0 改動**（使用者的核心要求）。
- MCTS 的 `computation_budget=10000`（mcts.cpp）在網頁上可能太慢，但**不要改它**（那是使用者要調的）；橋接層可加 timeout 保護而非改引擎。

## 主線現況（別碰，僅供參考）
Rust 版已上線 https://chess-test.conray.top（server :3939 + cloudflared tunnel，背景行程）。詳見專案記憶 deployment / project-status。
