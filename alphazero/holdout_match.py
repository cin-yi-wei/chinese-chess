"""泛化診斷:在「訓練沒看過的全新隨機局面」上,量網路首選 vs 老師正解的 match%。

對比訓練集 match%(imitate 印的)：
  - held-out 也高 → 真的通用化
  - held-out 低(但訓練 match 高) → 過擬合/背題

用法:python holdout_match.py <net.pt> <depth> [n=500]
"""

from __future__ import annotations

import sys
import random
import torch

import config
from xiangqi.board import Board
from net import XiangqiNet
from nn_eval import NNEvaluator
from abopp import AlphaBetaOpponent


def main():
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    net_path = sys.argv[1]
    depth = int(sys.argv[2])
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 500

    net = XiangqiNet(config.CHANNELS, config.BLOCKS).to(dev).eval()
    net.load_state_dict(torch.load(net_path, map_location=dev))
    ev = NNEvaluator(net, dev)
    opp = AlphaBetaOpponent()

    match = 0
    total = 0
    while total < n:
        b = Board.start()
        steps = random.randint(4, 30)  # 全新隨機局面(不同長度隨機走)
        dead = False
        for _ in range(steps):
            legal = b.legal_moves()
            if not legal:
                dead = True
                break
            b.make_move(random.choice(legal))
        if dead:
            continue
        legal = b.legal_moves()
        if not legal:
            continue
        ab = opp.best_move(b, depth)
        if ab is None:
            continue
        priors, _v = ev(b, legal)
        pred = max(priors, key=priors.get)
        match += int(pred == ab)
        total += 1

    opp.close()
    print(f"held-out match vs depth-{depth}: {match}/{total} = {match / total * 100:.1f}%",
          flush=True)


if __name__ == "__main__":
    main()
