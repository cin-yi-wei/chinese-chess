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
# 自訂模式 sims 隨 z 縮放：弱端 sims 少（快又弱）、強端 sims 多（真的強、分佈細）。
CUSTOM_SIMS_MIN = int(os.environ.get("CHESS_CUSTOM_SIMS_MIN", "40"))   # z=-2（最弱）
CUSTOM_SIMS_MAX = int(os.environ.get("CHESS_CUSTOM_SIMS_MAX", "160"))  # z=+2（最強）
# 門檻 R_th 也隨 z 縮放：強端 0.10 保品質；弱端 →0 放行爛步，下限才夠弱。
THRESHOLD_MAX = 0.10
CUSTOM_MIN, CUSTOM_MAX = 1, 100


def difficulty_to_z(d: int) -> float:
    """自訂 1~100 線性映射到 strength index z ∈ [-2, 2]（論文實測此段 z↔Elo 近線性）。"""
    d = max(CUSTOM_MIN, min(CUSTOM_MAX, int(d)))
    return -2.0 + (d - 1.0) / 99.0 * 4.0


def _z01(z: float) -> float:
    """z∈[-2,2] → 0~1。"""
    return max(0.0, min(1.0, (z + 2.0) / 4.0))


def sims_for_z(z: float) -> int:
    return int(round(CUSTOM_SIMS_MIN + (CUSTOM_SIMS_MAX - CUSTOM_SIMS_MIN) * _z01(z)))


def rth_for_z(z: float) -> float:
    return THRESHOLD_MAX * _z01(z)


SIMS_HARD_MIN, SIMS_HARD_MAX = 8, 400  # 自訂 sims 拉霸的允許範圍


def resolve_difficulty(difficulty, sims_override=None):
    """回傳 (sims, z)：z=None 表示預設模式（取最高訪問）；z 有值表示自訂線性棋力。
    自訂模式：z 由 difficulty(1~100) 決定；sims 若前端有給(獨立拉霸)就用它，否則依 z 縮放。"""
    if isinstance(difficulty, bool):  # 防呆：bool 是 int 子類
        return DEFAULT_SIMS, None
    if isinstance(difficulty, (int, float)):
        z = difficulty_to_z(int(difficulty))
        if isinstance(sims_override, (int, float)) and not isinstance(sims_override, bool):
            sims = max(SIMS_HARD_MIN, min(SIMS_HARD_MAX, int(sims_override)))
        else:
            sims = sims_for_z(z)
        return sims, z
    if isinstance(difficulty, str) and difficulty in PRESET_SIMS:
        return PRESET_SIMS[difficulty], None
    return DEFAULT_SIMS, None


def z_select_move(dist: dict, z: float, legal: list):
    """線性棋力選步（NN 版）。

    純論文 π∝N^z 在強策略網路下弱不下來：因為爛步根本不會被搜到(訪問=0)、
    不在候選內，z 再負也只在『好步』裡挑。故改成『搜尋分佈』與『全合法均勻分佈』
    的混合：weakness w = 1-z01(z)（z=+2→0 全靠搜尋=最強；z=-2→1 全均勻=真的弱、
    會送子）。強端仍用 rth 過濾保品質。"""
    if not legal:
        legal = [m for m, n in (dist or {}).items()]
    if not legal:
        return None
    w = 1.0 - _z01(z)  # 0(最強) .. 1(最弱)

    # 搜尋分佈 p_search（僅在有訪問的步上）
    p_search = {}
    if dist:
        n_max = max(dist.values(), default=0)
        if n_max > 0:
            floor = n_max * rth_for_z(z)
            pool = {m: n for m, n in dist.items() if n >= floor and n > 0} \
                or {m: n for m, n in dist.items() if n > 0}
            if z >= 50.0:
                bm = max(pool, key=pool.get)
                p_search = {bm: 1.0}
            else:
                wts = {m: n ** z for m, n in pool.items()}
                tot = sum(wts.values())
                if tot > 0:
                    p_search = {m: v / tot for m, v in wts.items()}

    u = 1.0 / len(legal)  # 均勻分佈
    probs = [(1.0 - w) * p_search.get(m, 0.0) + w * u for m in legal]
    total = sum(probs)
    if not (total > 0.0):
        return legal[0]
    pick = random.random() * total
    for m, pr in zip(legal, probs):
        pick -= pr
        if pick <= 0.0:
            return m
    return legal[-1]


_evaluator = Px0Evaluator(ONNX)


def _pick_move(board: Board, sims: int, z):
    """跑 MCTS 選一步。z=None → 取最高訪問（預設難度）；z 有值 → 線性棋力抽樣（自訂）。"""
    if z is None:
        return puct_search_batched(board, _evaluator, sims, BATCH, 1.5)
    dist = visit_distribution_batched(board, _evaluator, sims, BATCH, 1.5)
    return z_select_move(dist, z, list(board.legal_moves()))


def state_msg(board: Board, ai_move=None, game_over_override=None) -> dict:
    legal = board.legal_moves()
    game_over = game_over_override
    if game_over is None and not legal:
        game_over = "black" if board.red_to_move else "red"
    return {
        "type": "state",
        "fen": board.to_fen(),
        "redToMove": board.red_to_move,
        "inCheck": board.checked(),
        "legal": [] if game_over else [[*sq_to_coord(move_src(m)), *sq_to_coord(move_dst(m))] for m in legal],
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
            sims, z = resolve_difficulty(cmd.get("difficulty"), cmd.get("sims"))
            await ws.send_json(state_msg(board))
        elif t == "restore":
            # 斷線重連：用前端保存的整局著法(每 ply [fx,fy,tx,ty])重放，重建盤面。
            board = Board.start()
            sims, z = resolve_difficulty(cmd.get("difficulty"), cmd.get("sims"))
            for ply in cmd.get("moves") or []:
                try:
                    mv = make_move_code(coord_to_sq(ply[0], ply[1]), coord_to_sq(ply[2], ply[3]))
                except (TypeError, IndexError):
                    break
                if mv in board.legal_moves():
                    board.make_move(mv)
                else:
                    break  # 資料不一致就停在重建到的位置
            await ws.send_json(state_msg(board))
        elif t == "resign":
            # 認輸：紅（人）投降，黑勝。盤面不動，只回覆終局。
            await ws.send_json(state_msg(board, game_over_override="black"))
        elif t == "undo":
            # 悔棋：收回「你上一手 + AI 回手」一整組（各一 ply），回到你的回合繼續下。
            for _ in range(2):
                if board.move_stack:
                    board.undo_make_move()
            # 撤到還沒輪到紅走時，補撤到紅方回合（保險）
            while board.move_stack and not board.red_to_move:
                board.undo_make_move()
            await ws.send_json(state_msg(board))
        elif t == "move":
            # 前端每步都帶當前難度/sims → 中途調拉霸『下一步立即生效』，不必重開局
            if "difficulty" in cmd:
                sims, z = resolve_difficulty(cmd.get("difficulty"), cmd.get("sims"))
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
