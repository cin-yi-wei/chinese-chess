"""量「網路檢查點 vs Rust alpha-beta 老師(depth D)」的勝率,當課程升層判準。

用法(alphazero/ 下,PYTHONPATH=.,需先 build oppd):
    python eval_vs_oppd.py <net.pt> <depth> [games=20] [sims=200] [rand_open=6]
網路用 puct_search(sims>0)或純政策(sims<=0)、老師用 oppd;輪流執先;封頂按子力判勝負。
rand_open>0:每局先走該步數的隨機開局(雙方),讓每局都是不同棋 → 勝率才可靠
(oppd 確定性、網路近確定,不隨機化的話 N 局其實只有 ~2 種棋局重複)。
"""

from __future__ import annotations

import sys
import random
import torch

import config
from xiangqi.board import Board, BLACK_TAG
from net import XiangqiNet
from nn_eval import NNEvaluator
from mcts import puct_search
from abopp import AlphaBetaOpponent

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


def _play(nn, oppd, depth, nn_red, sims, rand_open=0):
    """回傳紅方視角結果。sims<=0 時網路用『純政策 argmax』(不搜尋)以診斷 value/MCTS 影響。
    rand_open>0:開局先走該步數隨機著法(雙方)以產生不同棋局。"""
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
                priors, _v = nn(b, legal)          # 純政策：網路首選著法，不做 MCTS
                mv = max(priors, key=priors.get)
            else:
                mv = puct_search(b, nn, sims, config.C_PUCT)
        else:
            mv = oppd.best_move(b, depth)
        if mv is None:
            return -1 if b.red_to_move else 1
        b.make_move(mv)
    m = _margin(b)
    return 1 if m > 0.5 else (-1 if m < -0.5 else 0)


def main():
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    net_path = sys.argv[1]
    depth = int(sys.argv[2])
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 20
    sims = int(sys.argv[4]) if len(sys.argv) > 4 else 200
    rand_open = int(sys.argv[5]) if len(sys.argv) > 5 else 6
    print(f"device={dev}  NN={net_path}  oppd depth={depth}  games={n}  sims={sims}  "
          f"rand_open={rand_open}", flush=True)

    net = XiangqiNet(config.CHANNELS, config.BLOCKS).to(dev).eval()
    net.load_state_dict(torch.load(net_path, map_location=dev))
    nn = NNEvaluator(net, dev)
    oppd = AlphaBetaOpponent()

    w = l = d = 0
    for i in range(n):
        nn_red = (i % 2 == 0)
        res = _play(nn, oppd, depth, nn_red, sims, rand_open)
        nn_res = res if nn_red else -res
        w += nn_res > 0
        l += nn_res < 0
        d += nn_res == 0
        tag = "W" if nn_res > 0 else ("L" if nn_res < 0 else "D")
        print(f"game {i+1}/{n}: NN {tag}  ({w}-{l}-{d})", flush=True)

    oppd.close()
    print(f"\nNN vs oppd depth {depth}: {w}W {l}L {d}D over {n} -> {(w+0.5*d)/n*100:.0f}%", flush=True)


if __name__ == "__main__":
    main()
