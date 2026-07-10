"""自我對弈：用目前網路 + PUCT 產生一局訓練樣本。

每個決策點記錄 (輸入平面, MCTS 訪問分佈當 policy 目標, 走子方)；
對局結束用勝負結果 z 當每個位置的 value 目標（該位置走子方視角）。
"""

from __future__ import annotations

import math
import random

from xiangqi.board import Board, BLACK_TAG
from xiangqi.encode import board_to_planes, move_to_index, POLICY_SIZE
from mcts import visit_distribution_batched

# 子力價值（僅用於冷啟動時對「達步數上限」的局判定勝負；不影響走子/合法性）
_PIECE_VAL = {1: 2.0, 2: 2.0, 3: 4.0, 4: 9.0, 5: 4.5, 6: 1.0}  # 士象馬車炮兵
_MAT_WIN = 3.0  # 子力差達此值（約一個馬/炮）即判該方勝，逼出決定性 value 訊號


def _material_result(b: Board) -> float:
    """紅方視角的價值目標 ∈ [-1,1]，給達步數上限、未分勝負的局用。

    子力明顯領先(>= _MAT_WIN)直接判勝(±1)，讓價值頭學到決定性訊號；
    接近平衡才用較銳利的梯度，避免全部擠在 0 附近（先前價值頭空轉主因）。
    """
    red = black = 0.0
    for pc in b.squares:
        if pc == 0:
            continue
        v = _PIECE_VAL.get(pc & 7, 0.0)
        if pc < BLACK_TAG:
            red += v
        else:
            black += v
    diff = red - black  # 紅方視角
    if diff >= _MAT_WIN:
        return 1.0
    if diff <= -_MAT_WIN:
        return -1.0
    return math.tanh(diff / 3.0)


def play_game(evaluator, sims: int, temp_moves: int = 30, max_moves: int = 200,
              c_puct: float = 1.5, batch_size: int = 32,
              dir_alpha: float = 0.0, dir_frac: float = 0.0):
    """回傳 [(planes, policy_target[8100], value_target)]。evaluator 需有 .batch()。

    dir_frac>0 時自我對弈於根節點加 Dirichlet 探索雜訊（AlphaZero 標準）。
    """
    b = Board.start()
    history = []  # (planes, dist, red_to_move)
    result = 0.0  # 紅方視角：+1 紅勝 / -1 黑勝 / 0 和
    decisive = False  # 是否真的分出勝負（將死/困斃）

    for ply in range(max_moves):
        if not b.legal_moves():
            # 走子方無合法著法 = 被將死/困斃，該方負
            result = -1.0 if b.red_to_move else 1.0
            decisive = True
            break
        dist = visit_distribution_batched(b, evaluator, sims, batch_size, c_puct,
                                          dir_alpha, dir_frac)
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

    if not decisive:
        # 達步數上限、未分勝負：用子力差當梯度化的 value 目標（冷啟動 bootstrap）
        result = _material_result(b)

    samples = []
    for planes, dist, red in history:
        pol = [0.0] * POLICY_SIZE
        tot = sum(dist.values()) or 1
        for m, v in dist.items():
            pol[move_to_index(m)] = v / tot
        z = result if red else -result  # 轉成該位置走子方視角
        samples.append((planes, pol, float(z)))
    return samples


def _pick_move(dist, ply, temp_moves):
    """前 temp_moves 步依訪問數比例取樣，之後取最高訪問。"""
    moves = list(dist)
    visits = [dist[m] for m in moves]
    if ply < temp_moves:
        total = sum(visits)
        r = random.random() * total
        acc = 0.0
        for m, v in zip(moves, visits):
            acc += v
            if acc >= r:
                return m
        return moves[-1]
    return max(dist, key=dist.get)


def play_game_vs_opponent(az_evaluator, opponent, depth: int, az_is_red: bool,
                          sims: int, temp_moves: int = 30, max_moves: int = 200,
                          c_puct: float = 1.5, batch_size: int = 32,
                          dir_alpha: float = 0.0, dir_frac: float = 0.0):
    """課程訓練：AZ(MCTS) 對 alpha-beta 老師。只記 AZ 側的樣本；value=整局結果。

    opponent 需有 .best_move(board, depth)。az_is_red 決定 AZ 執紅或黑（外部輪流）。
    """
    b = Board.start()
    history = []  # 只記 AZ 走子的局面 (planes, dist, red_to_move)
    result = 0.0
    decisive = False

    for ply in range(max_moves):
        if not b.legal_moves():
            result = -1.0 if b.red_to_move else 1.0
            decisive = True
            break
        if b.red_to_move == az_is_red:
            # AZ 走：跑 MCTS、記樣本
            dist = visit_distribution_batched(b, az_evaluator, sims, batch_size, c_puct,
                                              dir_alpha, dir_frac)
            if not dist:
                result = -1.0 if b.red_to_move else 1.0
                decisive = True
                break
            history.append((board_to_planes(b), dist, b.red_to_move))
            chosen = _pick_move(dist, ply, temp_moves)
        else:
            # 老師走：alpha-beta，不記樣本
            chosen = opponent.best_move(b, depth)
            if chosen is None:
                result = -1.0 if b.red_to_move else 1.0
                decisive = True
                break
        b.make_move(chosen)

    if not decisive:
        result = _material_result(b)

    samples = []
    for planes, dist, red in history:
        pol = [0.0] * POLICY_SIZE
        tot = sum(dist.values()) or 1
        for m, v in dist.items():
            pol[move_to_index(m)] = v / tot
        z = result if red else -result
        samples.append((planes, pol, float(z)))
    return samples
