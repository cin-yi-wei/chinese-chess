"""棋力評測：讓一個檢查點(NN+PUCT) 對戰基準(子力 stub 或另一檢查點)，回報勝率。

用法（在 alphazero/ 下，需 PYTHONPATH=.）：
    python eval.py <net.pt> material 20 200      # NN vs 子力基準，20 局，每步 200 sims
    python eval.py <netA.pt> <netB.pt> 20 200    # 兩個檢查點對戰
評測用 puct_search（無 Dirichlet 雜訊），雙方同 sims、輪流先手，公平比較。
"""

from __future__ import annotations

import sys
import torch

import config
from xiangqi.board import Board, BLACK_TAG
from net import XiangqiNet
from nn_eval import NNEvaluator
from mcts import puct_search, material_evaluator

_PIECE_VAL = {1: 2.0, 2: 2.0, 3: 4.0, 4: 9.0, 5: 4.5, 6: 1.0}  # 士象馬車炮兵


def _material_margin(b) -> float:
    """紅方視角子力差（用於封頂時的敏感判定）。"""
    red = black = 0.0
    for pc in b.squares:
        if pc == 0:
            continue
        v = _PIECE_VAL.get(pc & 7, 0.0)
        if pc < BLACK_TAG:
            red += v
        else:
            black += v
    return red - black


def make_evaluator(spec: str, device: str):
    if spec == "material":
        return material_evaluator
    net = XiangqiNet(config.CHANNELS, config.BLOCKS).to(device).eval()
    net.load_state_dict(torch.load(spec, map_location=device))
    return NNEvaluator(net, device)


def play_one(ev_red, ev_black, sims: int, c_puct: float, max_moves: int,
             adjudicate: bool = False) -> int:
    """回傳紅方視角結果：+1 紅勝 / -1 黑勝 / 0 和。

    adjudicate=True 時，達步數上限改按子力差判勝負（>0.5 分即算贏），敏感度較高。
    """
    b = Board.start()
    for _ in range(max_moves):
        if not b.legal_moves():
            return -1 if b.red_to_move else 1
        ev = ev_red if b.red_to_move else ev_black
        mv = puct_search(b, ev, sims, c_puct)
        if mv is None:
            return -1 if b.red_to_move else 1
        b.make_move(mv)
    if adjudicate:
        m = _material_margin(b)
        return 1 if m > 0.5 else (-1 if m < -0.5 else 0)
    return 0  # 達步數上限判和


def main():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    net_spec, opp_spec = sys.argv[1], sys.argv[2]
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 20
    sims = int(sys.argv[4]) if len(sys.argv) > 4 else 200
    adjudicate = len(sys.argv) > 5 and sys.argv[5] == "adj"
    mode = "子力判定" if adjudicate else "純勝負"
    print(f"device={device}  NN={net_spec}  opp={opp_spec}  games={n}  sims={sims}  ({mode})", flush=True)

    nn = make_evaluator(net_spec, device)
    opp = make_evaluator(opp_spec, device)

    w = l = d = 0
    for i in range(n):
        if i % 2 == 0:                       # NN 執紅
            res = play_one(nn, opp, sims, config.C_PUCT, config.MAX_MOVES, adjudicate)
        else:                                # NN 執黑
            res = -play_one(opp, nn, sims, config.C_PUCT, config.MAX_MOVES, adjudicate)
        w += res > 0
        l += res < 0
        d += res == 0
        tag = "W" if res > 0 else ("L" if res < 0 else "D")
        print(f"game {i+1}/{n}: NN {tag}  (running {w}-{l}-{d})", flush=True)

    score = (w + 0.5 * d) / n * 100
    print(f"\nNN vs {opp_spec}: {w}W {l}L {d}D over {n} games -> score {score:.0f}%", flush=True)


if __name__ == "__main__":
    main()
