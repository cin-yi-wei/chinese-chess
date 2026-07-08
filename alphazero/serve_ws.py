"""Phase 5：AlphaZero 常駐對弈服務（aiohttp WebSocket + 靜態前端）。

載入 latest.pt 一次，之後每條 WS 連線一局；協定與主線前端相同
（new_game / move → state / illegal）。人執紅、AI 執黑用 PUCT+網路回手。
CPU 即可跑（推論不需 GPU）。

環境變數：
    CHESS_WEIGHTS  權重路徑（預設 checkpoints/latest.pt）
    CHESS_SIMS     每步 PUCT 模擬數（預設 200）
    CHESS_STATIC   前端靜態目錄（預設 ../frontend/dist）
    CHESS_PORT     監聽埠（預設 3941）
"""

from __future__ import annotations

import asyncio
import json
import os

import torch
from aiohttp import web

from net import XiangqiNet
from nn_eval import NNEvaluator
from mcts import puct_search_batched
from xiangqi.board import Board, coord_to_sq, sq_to_coord, move_src, move_dst, make_move_code

WEIGHTS = os.environ.get("CHESS_WEIGHTS", "checkpoints/latest.pt")
SIMS = int(os.environ.get("CHESS_SIMS", "200"))
BATCH = int(os.environ.get("CHESS_BATCH", "32"))
STATIC = os.environ.get("CHESS_STATIC", "../frontend/dist")
PORT = int(os.environ.get("CHESS_PORT", "3941"))

torch.set_num_threads(os.cpu_count() or 4)  # CPU 推論用滿核心
_device = "cuda" if torch.cuda.is_available() else "cpu"
_net = XiangqiNet(128, 10)
_net.load_state_dict(torch.load(WEIGHTS, map_location=_device))
_net.to(_device).eval()
_evaluator = NNEvaluator(_net, _device)


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
            # AI 推論放到執行緒，避免卡住事件迴圈
            ai_mv = await asyncio.to_thread(puct_search_batched, board, _evaluator, SIMS, BATCH)
            board.make_move(ai_mv)
            ax, ay = sq_to_coord(move_src(ai_mv))
            bx, by = sq_to_coord(move_dst(ai_mv))
            await ws.send_json(state_msg(board, [ax, ay, bx, by]))
    return ws


async def index(_request: web.Request) -> web.FileResponse:
    return web.FileResponse(os.path.join(STATIC, "index.html"))


def make_app() -> web.Application:
    """建立 aiohttp app（供 serve_ws 主程式與桌面版 desktop/ 共用）。"""
    app = web.Application()
    app.router.add_get("/ws", ws_handler)
    app.router.add_get("/health", lambda _r: web.Response(text="ok"))
    app.router.add_get("/", index)
    app.router.add_static("/", STATIC, show_index=False)
    return app


def main() -> None:
    print(f"AlphaZero 對弈服務啟動 127.0.0.1:{PORT}  weights={WEIGHTS} sims={SIMS} device={_device}")
    web.run_app(make_app(), host="127.0.0.1", port=PORT)


if __name__ == "__main__":
    main()
