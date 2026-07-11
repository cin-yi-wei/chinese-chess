"""chess-az 對弈服務（px0 強權重版）：aiohttp WebSocket + 靜態前端（frontend/dist）。

評估器用 px0（PikaXiangqiZero，lc0 象棋 fork）權重經 ONNX（px0_eval.Px0Evaluator，
path B 純 Python 編碼 px0_encode，不需 C++ 綁定），跑在自家 PUCT MCTS（batch=8 為 px0 鐵律）。CPU 即可跑。

難度（前端 new_game 送 difficulty）：
    預設 "easy"/"medium"/"hard" → sims 8/16/48，取最高訪問。
    自訂整數 1~100 → 交大(NCTU 吳毅成) z-index 線性棋力系統：z∈[-2,2]、固定 sims 跑 MCTS、
      濾掉 N<N_max·0.1 後 π∝N^z 加權抽樣（同 engine::best_move_mcts_strength）。
      100=最強、50≈隨機最弱、1=偏好爛步。

環境變數：
    CHESS_ONNX         px0 leela2onnx 轉出的 .onnx（預設 ../px0/nets/net_fcd86ede.onnx）
    CHESS_BATCH        批次葉評估大小（預設 8，px0 鐵律，勿改大）
    CHESS_CUSTOM_SIMS  自訂模式的固定搜尋預算（預設 48，≈9s/步）
    CHESS_STATIC       前端靜態目錄（預設 ../frontend/dist）
    CHESS_PORT         監聽埠（預設 3941）
"""

from __future__ import annotations

import asyncio
import json
import os
import random

_REPO_ALPHAZERO = os.path.dirname(os.path.abspath(__file__))

from aiohttp import web

from px0_eval import Px0Evaluator
from mcts import puct_search_batched, visit_distribution_batched
from xiangqi.board import Board, coord_to_sq, sq_to_coord, move_src, move_dst, make_move_code

ONNX = os.environ.get(
    "CHESS_ONNX",
    os.path.normpath(os.path.join(_REPO_ALPHAZERO, "..", "px0", "nets", "net_fcd86ede.onnx")),
)
BATCH = int(os.environ.get("CHESS_BATCH", "8"))
STATIC = os.environ.get("CHESS_STATIC", "../frontend/dist")
PORT = int(os.environ.get("CHESS_PORT", "3941"))

# 預設難度 → sims（取訪問數最高步）
PRESET_SIMS = {"easy": 8, "medium": 16, "hard": 48}
DEFAULT_SIMS = PRESET_SIMS["medium"]

# 自訂＝交大（NCTU 吳毅成）線性棋力系統：固定 sims 跑 MCTS，再用 strength index z
# 對 root 訪問數 N_i 做 π_i ∝ N_i^z 加權抽樣（先濾掉 N_i < N_max·R_th 的爛步）。
# z 越大越強（→∞ 即選最大）、z=0 隨機、z<0 變弱；z↔Elo 近線性。與 chess-test 的
# engine::best_move_mcts_strength 同演算法（THRESHOLD_RATIO=0.1）。
CUSTOM_SIMS = int(os.environ.get("CHESS_CUSTOM_SIMS", "48"))  # 自訂模式的搜尋預算（≈9s/步）
THRESHOLD_RATIO = 0.1
CUSTOM_MIN, CUSTOM_MAX = 1, 100


def difficulty_to_z(d: int) -> float:
    """自訂 1~100 線性映射到 strength index z ∈ [-2, 2]（論文實測此段 z↔Elo 近線性）。"""
    d = max(CUSTOM_MIN, min(CUSTOM_MAX, int(d)))
    return -2.0 + (d - 1.0) / 99.0 * 4.0


def resolve_difficulty(difficulty):
    """回傳 (sims, z)：z=None 表示預設模式（取最高訪問）；z 有值表示自訂線性棋力。"""
    if isinstance(difficulty, bool):  # 防呆：bool 是 int 子類
        return DEFAULT_SIMS, None
    if isinstance(difficulty, (int, float)):
        return CUSTOM_SIMS, difficulty_to_z(int(difficulty))
    if isinstance(difficulty, str) and difficulty in PRESET_SIMS:
        return PRESET_SIMS[difficulty], None
    return DEFAULT_SIMS, None


def z_select_move(dist: dict, z: float):
    """線性棋力選步：dist={move:N_i} → 濾門檻 → π_i ∝ N_i^z 加權抽樣。"""
    if not dist:
        return None
    n_max = max(dist.values())
    if n_max <= 0:
        return next(iter(dist))
    floor = n_max * THRESHOLD_RATIO
    pool = [(m, n) for m, n in dist.items() if n >= floor and n > 0] or list(dist.items())
    if z >= 50.0:
        return max(pool, key=lambda mn: mn[1])[0]
    weights = [n ** z for _, n in pool]
    total = sum(weights)
    if not (total > 0.0):
        return max(pool, key=lambda mn: mn[1])[0]
    pick = random.random() * total
    for (m, _), w in zip(pool, weights):
        pick -= w
        if pick <= 0.0:
            return m
    return pool[-1][0]


_evaluator = Px0Evaluator(ONNX)


def _pick_move(board: Board, sims: int, z):
    """跑 MCTS 選一步。z=None → 取最高訪問（預設難度）；z 有值 → 線性棋力抽樣（自訂）。"""
    if z is None:
        return puct_search_batched(board, _evaluator, sims, BATCH, 1.5)
    dist = visit_distribution_batched(board, _evaluator, sims, BATCH, 1.5)
    return z_select_move(dist, z)


def state_msg(board: Board, ai_move=None) -> dict:
    legal = board.legal_moves()
    game_over = None
    if not legal:
        game_over = "black" if board.red_to_move else "red"
    return {
        "type": "state",
        "fen": board.to_fen(),
        "redToMove": board.red_to_move,
        "inCheck": board.checked(),
        "legal": [[*sq_to_coord(move_src(m)), *sq_to_coord(move_dst(m))] for m in legal],
        "aiMove": ai_move,
        "gameOver": game_over,
    }


async def ws_handler(request: web.Request) -> web.WebSocketResponse:
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    board = Board.start()
    sims, z = DEFAULT_SIMS, None  # 每條連線各自記住難度（z=None 取最高訪問；有值走線性棋力）
    async for msg in ws:
        if msg.type != web.WSMsgType.TEXT:
            continue
        try:
            cmd = json.loads(msg.data)
        except json.JSONDecodeError:
            continue
        t = cmd.get("type")
        if t == "new_game":
            board = Board.start()
            sims, z = resolve_difficulty(cmd.get("difficulty"))
            await ws.send_json(state_msg(board))
        elif t == "move":
            fr, to = cmd.get("from"), cmd.get("to")
            mv = make_move_code(coord_to_sq(fr[0], fr[1]), coord_to_sq(to[0], to[1]))
            if mv not in board.legal_moves():
                await ws.send_json({"type": "illegal"})
                continue
            board.make_move(mv)
            if not board.legal_moves():
                await ws.send_json(state_msg(board))
                continue
            # AI 推論放到執行緒，避免卡住事件迴圈。預設模式取最高訪問；自訂走線性棋力 z 抽樣。
            ai_mv = await asyncio.to_thread(_pick_move, board, sims, z)
            board.make_move(ai_mv)
            ax, ay = sq_to_coord(move_src(ai_mv))
            bx, by = sq_to_coord(move_dst(ai_mv))
            await ws.send_json(state_msg(board, [ax, ay, bx, by]))
    return ws


async def index(_request: web.Request) -> web.FileResponse:
    return web.FileResponse(os.path.join(STATIC, "index.html"))


def make_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/ws", ws_handler)
    app.router.add_get("/health", lambda _r: web.Response(text="ok"))
    app.router.add_get("/", index)
    app.router.add_static("/", STATIC, show_index=False)
    return app


def main() -> None:
    print(f"chess-az(px0) 啟動 127.0.0.1:{PORT}  onnx={ONNX} batch={BATCH} "
          f"presets={PRESET_SIMS} providers={_evaluator.session.get_providers()}")
    web.run_app(make_app(), host="127.0.0.1", port=PORT)


if __name__ == "__main__":
    main()
