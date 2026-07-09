"""自我對弈：用目前網路 + PUCT 產生一局訓練樣本。

每個決策點記錄 (輸入平面, MCTS 訪問分佈當 policy 目標, 走子方)；
對局結束用勝負結果 z 當每個位置的 value 目標（該位置走子方視角）。
"""

from __future__ import annotations

import random

from xiangqi.board import Board
from xiangqi.encode import board_to_planes, move_to_index, POLICY_SIZE
from mcts import visit_distribution_batched


def play_game(evaluator, sims: int, temp_moves: int = 30, max_moves: int = 200,
              c_puct: float = 1.5, batch_size: int = 32):
    """回傳 [(planes, policy_target[8100], value_target)]。evaluator 需有 .batch()。"""
    b = Board.start()
    history = []  # (planes, dist, red_to_move)
    result = 0  # 紅方視角：+1 紅勝 / -1 黑勝 / 0 和

    for ply in range(max_moves):
        if not b.legal_moves():
            # 走子方無合法著法 = 被將死/困斃，該方負
            result = -1 if b.red_to_move else 1
            break
        dist = visit_distribution_batched(b, evaluator, sims, batch_size, c_puct)
        history.append((board_to_planes(b), dist, b.red_to_move))

        moves = list(dist)
        visits = [dist[m] for m in moves]
        if ply < temp_moves:
            # 依訪問數比例取樣
            total = sum(visits)
            r = random.random() * total
            acc = 0.0
            chosen = moves[-1]
            for m, v in zip(moves, visits):
                acc += v
                if acc >= r:
                    chosen = m
                    break
        else:
            chosen = max(dist, key=dist.get)
        b.make_move(chosen)

    samples = []
    for planes, dist, red in history:
        pol = [0.0] * POLICY_SIZE
        tot = sum(dist.values()) or 1
        for m, v in dist.items():
            pol[move_to_index(m)] = v / tot
        z = result if red else -result  # 轉成該位置走子方視角
        samples.append((planes, pol, float(z)))
    return samples
