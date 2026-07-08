"""Phase 5：載入訓練好的權重，用 PUCT + 網路推論選著法。

對照 Windows 訓練端交接規格：
- 權重：XiangqiNet(channels=128, blocks=10) 的 state_dict（checkpoints/latest.pt）
- 輸入：15×10×9 平面（board_to_planes）
- 輸出：policy logits 8100（index=(fy*9+fx)*90+(ty*9+tx)）、value tanh∈[-1,1]
索引公式與 encode.py 的 move_to_index 完全一致（同一 repo），載入即相容。

需 torch。用法：
    python play.py --weights checkpoints/latest.pt --fen "<FEN>" --sims 400
"""

from __future__ import annotations

import argparse

import torch

from net import XiangqiNet
from nn_eval import NNEvaluator
from mcts import puct_search
from xiangqi.board import Board, START_FEN, sq_to_coord, move_src, move_dst


def load_net(path: str, device: str = "cpu", channels: int = 128, blocks: int = 10):
    net = XiangqiNet(channels, blocks)
    net.load_state_dict(torch.load(path, map_location=device))
    net.to(device).eval()
    return net


def best_move_from_fen(net, fen: str, sims: int = 400, device: str = "cpu"):
    b = Board()
    b.load_fen(fen)
    evaluator = NNEvaluator(net, device)
    return puct_search(b, evaluator, sims)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", required=True)
    ap.add_argument("--fen", default=START_FEN)
    ap.add_argument("--sims", type=int, default=400)
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    args = ap.parse_args()

    net = load_net(args.weights, args.device)
    mv = best_move_from_fen(net, args.fen, args.sims, args.device)
    if mv is None:
        print("no legal move (game over)")
    else:
        fx, fy = sq_to_coord(move_src(mv))
        tx, ty = sq_to_coord(move_dst(mv))
        print(f"best move: ({fx},{fy}) -> ({tx},{ty})  code={mv}")
