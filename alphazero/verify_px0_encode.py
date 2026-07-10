"""驗證純 Python 編碼器 px0_encode 與 px0 綁定(golden reference)逐局面 bit-exact。

比對：
  1. encode(board) 的 124×10×9 平面  vs  綁定 GameState(帶8步歷史).as_input.expand()
  2. move_to_nn_index(mv)             vs  綁定 gs.moves()/policy_indices()
在多個隨機自對弈局面上比對。用法：從 alphazero/ 跑 python verify_px0_encode.py
"""

from __future__ import annotations

import random
import sys

import numpy as np

sys.path.insert(0, r"C:\Users\conra\project\chinese-chess\px0\builddir")
import backends  # noqa: E402

from xiangqi.board import Board  # noqa: E402
from px0_encode import board_to_px0_fen, my_move_to_px0
import px0_encode  # noqa: E402

_ENC = backends.Backend(backend="trivial")


def _golden_gamestate(board):
    """與 px0_eval._make_gamestate 相同：回溯最多8步建帶歷史 GameState。"""
    stack = board.move_stack
    k = min(8, len(stack))
    if k == 0:
        return backends.GameState(board_to_px0_fen(board))
    tmp = board.clone()
    for _ in range(k):
        tmp.undo_make_move()
    start_fen = board_to_px0_fen(tmp)
    hist = [my_move_to_px0(m) for m in stack[len(stack) - k:]]
    return backends.GameState(start_fen, hist)


def main():
    random.seed(20260711)
    n_plane_ok = n_plane_bad = 0
    n_idx_ok = n_idx_bad = 0
    bad_examples = []

    for game in range(120):
        b = Board.start()
        for ply in range(40):
            legal = b.legal_moves()
            if not legal:
                break
            gs = _golden_gamestate(b)

            # 1) 平面
            gold = np.frombuffer(gs.as_input(_ENC).expand(),
                                 dtype=np.float32).reshape(124, 10, 9)
            mine = px0_encode.encode(b)
            if np.array_equal(gold, mine):
                n_plane_ok += 1
            else:
                n_plane_bad += 1
                if len(bad_examples) < 3:
                    diff = np.argwhere(gold != mine)
                    planes = sorted(set(int(d[0]) for d in diff))
                    bad_examples.append(
                        f"game{game} ply{ply}: {len(diff)} 格不同, planes={planes[:12]}")

            # 2) 著法索引
            gmoves = gs.moves()
            gidx = list(gs.policy_indices())
            gmap = dict(zip(gmoves, gidx))
            for m in legal:
                s = my_move_to_px0(m)
                if px0_encode.move_to_nn_index(m, b.red_to_move) == gmap.get(s, -999):
                    n_idx_ok += 1
                else:
                    n_idx_bad += 1

            b.make_move(random.choice(legal))

    print(f"平面 bit-exact: {n_plane_ok} OK / {n_plane_bad} 不同")
    print(f"著法索引:       {n_idx_ok} OK / {n_idx_bad} 不同")
    for e in bad_examples:
        print("  ", e)
    if n_plane_bad == 0 and n_idx_bad == 0:
        print("[PASS] 純 Python 編碼器與綁定完全一致")


if __name__ == "__main__":
    main()
