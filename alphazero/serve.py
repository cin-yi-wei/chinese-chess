"""Phase 5：AlphaZero 引擎的 stdin/stdout JSON 服務（協定與主線 web / cpp_engine 相同）。

一行一個 JSON 指令；一行一個 JSON 回覆（每次 flush）。人執紅、AI 執黑（用 PUCT+網路）。
可直接套用 cpp-port 那套 Node 橋接（ws + child_process）接上網頁。

輸入：
    {"cmd":"new"}
    {"cmd":"move","from":[x,y],"to":[x,y]}
回覆：
    {"fen","redToMove","inCheck","legal":[[fx,fy,tx,ty]...],"aiMove":[..]|null,"gameOver":"red"|"black"|"draw"|null}
    {"illegal":true}

需 torch + 權重。用法：
    CHESS_WEIGHTS=checkpoints/latest.pt CHESS_SIMS=400 python serve.py
"""

from __future__ import annotations

import json
import os
import sys

import torch

from net import XiangqiNet
from nn_eval import NNEvaluator
from mcts import puct_search
from xiangqi.board import Board, coord_to_sq, sq_to_coord, move_src, move_dst, make_move_code


def _emit(obj) -> None:
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def _state(board: Board, ai_move=None):
    legal = board.legal_moves()
    game_over = None
    if not legal:
        game_over = "black" if board.red_to_move else "red"  # 走子方無著 → 對方勝
    return {
        "fen": board.to_fen(),
        "redToMove": board.red_to_move,
        "inCheck": board.checked(),
        "legal": [[*sq_to_coord(move_src(m)), *sq_to_coord(move_dst(m))] for m in legal],
        "aiMove": ai_move,
        "gameOver": game_over,
    }


def main() -> None:
    weights = os.environ.get("CHESS_WEIGHTS", "checkpoints/latest.pt")
    sims = int(os.environ.get("CHESS_SIMS", "400"))
    device = "cuda" if torch.cuda.is_available() else "cpu"

    net = XiangqiNet(128, 10)
    net.load_state_dict(torch.load(weights, map_location=device))
    net.to(device).eval()
    evaluator = NNEvaluator(net, device)

    board = Board.start()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            cmd = json.loads(line)
        except json.JSONDecodeError:
            continue

        if cmd.get("cmd") == "new":
            board = Board.start()
            _emit(_state(board))
        elif cmd.get("cmd") == "move":
            fx, fy = cmd["from"]
            tx, ty = cmd["to"]
            mv = make_move_code(coord_to_sq(fx, fy), coord_to_sq(tx, ty))
            if mv not in board.legal_moves():
                _emit({"illegal": True})
                continue
            board.make_move(mv)
            if not board.legal_moves():  # 人走完 AI 已被將死
                _emit(_state(board))
                continue
            ai_mv = puct_search(board, evaluator, sims)
            board.make_move(ai_mv)
            ax, ay = sq_to_coord(move_src(ai_mv))
            bx, by = sq_to_coord(move_dst(ai_mv))
            _emit(_state(board, [ax, ay, bx, by]))


if __name__ == "__main__":
    main()
