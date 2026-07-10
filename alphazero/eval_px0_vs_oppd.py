"""量「px0 權重 + 你的 MCTS  vs  Rust alpha-beta 老師(depth D)」的勝率。

用法(alphazero/ 下,PYTHONPATH=.,需先 build oppd.exe):
    python eval_px0_vs_oppd.py <depth> [games=20] [sims=400] [rand_open=6] [batch=64]

px0 側用 puct_search_batched(sims>0)或純政策 argmax(sims<=0)、老師用 oppd;輪流執先;
封頂按子力判勝負。rand_open>0:每局先走該步數隨機著法(雙方)→ 每局不同棋,勝率才可靠。
"""

from __future__ import annotations

import sys
import random

import config
from xiangqi.board import Board, BLACK_TAG
from mcts import puct_search_batched
from abopp import AlphaBetaOpponent
from px0_eval import Px0Evaluator

ONNX = r"C:\Users\conra\project\chinese-chess\px0\nets\net_150mb.onnx"  # 可用最後一個參數 net= 覆寫

_PIECE_VAL = {1: 2.0, 2: 2.0, 3: 4.0, 4: 9.0, 5: 4.5, 6: 1.0}


def _margin(b) -> float:
    r = bk = 0.0
    for pc in b.squares:
        if pc == 0:
            continue
        v = _PIECE_VAL.get(pc & 7, 0.0)
        if pc < BLACK_TAG:
            r += v
        else:
            bk += v
    return r - bk


def _play(nn, oppd, depth, nn_red, sims, batch, rand_open=0):
    """回傳紅方視角結果(1 紅勝 / -1 黑勝 / 0 和)。"""
    b = Board.start()
    for _ in range(rand_open):
        legal = b.legal_moves()
        if not legal:
            return -1 if b.red_to_move else 1
        b.make_move(random.choice(legal))
    for _ in range(config.MAX_MOVES):
        legal = b.legal_moves()
        if not legal:
            return -1 if b.red_to_move else 1
        if b.red_to_move == nn_red:
            if sims <= 0:
                priors, _v = nn(b, legal)
                mv = max(priors, key=priors.get)
            else:
                mv = puct_search_batched(b, nn, sims, batch, config.C_PUCT)
        else:
            mv = oppd.best_move(b, depth)
        if mv is None:
            return -1 if b.red_to_move else 1
        b.make_move(mv)
    m = _margin(b)
    return 1 if m > 0.5 else (-1 if m < -0.5 else 0)


def main():
    depth = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    sims = int(sys.argv[3]) if len(sys.argv) > 3 else 400
    rand_open = int(sys.argv[4]) if len(sys.argv) > 4 else 6
    batch = int(sys.argv[5]) if len(sys.argv) > 5 else 8
    onnx = sys.argv[6] if len(sys.argv) > 6 else ONNX
    print(f"px0 MCTS vs oppd depth={depth}  games={n}  sims={sims}  "
          f"rand_open={rand_open}  batch={batch}  net={onnx.split(chr(92))[-1]}", flush=True)

    nn = Px0Evaluator(onnx)
    oppd = AlphaBetaOpponent()

    w = l = d = 0
    for i in range(n):
        nn_red = (i % 2 == 0)
        res = _play(nn, oppd, depth, nn_red, sims, batch, rand_open)
        nn_res = res if nn_red else -res
        w += nn_res > 0
        l += nn_res < 0
        d += nn_res == 0
        tag = "W" if nn_res > 0 else ("L" if nn_res < 0 else "D")
        print(f"game {i+1}/{n}: px0 {tag}  ({w}-{l}-{d})", flush=True)

    oppd.close()
    print(f"\npx0 MCTS(sims={sims}) vs oppd depth {depth}: "
          f"{w}W {l}L {d}D over {n} -> {(w+0.5*d)/n*100:.0f}%", flush=True)


if __name__ == "__main__":
    main()
