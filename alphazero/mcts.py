"""PUCT MCTS（AlphaZero 式），用神經網路的 (policy, value) 引導，取代隨機 rollout。

評估器介面（可插拔）：
    evaluator(board, legal_moves) -> (priors: dict[move -> float], value: float)
  - priors：對合法著法的機率分佈（和約為 1）
  - value：目前走子方視角的局面評價，範圍 [-1, 1]（越大越好）

真正的網路評估器（torch）在 Phase 4 接上；本檔附一個純 Python 的材料評估器
`material_evaluator`，讓無 GPU 機也能驗證 PUCT 流程。
"""

from __future__ import annotations

import math

from xiangqi.board import Board, BLACK_TAG

# 子力價值（用於 stub 評估器）
_PIECE_VAL = {1: 2.0, 2: 2.0, 3: 4.0, 4: 9.0, 5: 4.5, 6: 1.0}  # 士象馬車炮兵；將不計


class Node:
    __slots__ = ("prior", "n", "w", "children")

    def __init__(self, prior: float) -> None:
        self.prior = prior
        self.n = 0
        self.w = 0.0
        self.children: dict[int, "Node"] = {}  # move -> Node

    def q(self) -> float:
        return self.w / self.n if self.n > 0 else 0.0


def material_evaluator(board: Board, legal: list[int]) -> tuple[dict[int, float], float]:
    """純 Python stub：均勻 prior + 材料差 value（走子方視角）。供 PUCT 流程驗證。"""
    red = black = 0.0
    for pc in board.squares:
        if pc == 0:
            continue
        v = _PIECE_VAL.get(pc & 7, 0.0)
        if pc < BLACK_TAG:
            red += v
        else:
            black += v
    diff = (red - black) if board.red_to_move else (black - red)
    value = math.tanh(diff / 10.0)
    p = 1.0 / len(legal) if legal else 0.0
    return {mv: p for mv in legal}, value


def _select(node: Node, c_puct: float) -> tuple[int, "Node"]:
    total = sum(ch.n for ch in node.children.values())
    sqrt_total = math.sqrt(total) + 1e-8
    best_mv, best_child, best_score = None, None, -1e18
    for mv, ch in node.children.items():
        q = -ch.q()  # 子節點價值是對手視角，父方取負
        u = c_puct * ch.prior * sqrt_total / (1 + ch.n)
        s = q + u
        if s > best_score:
            best_score, best_mv, best_child = s, mv, ch
    return best_mv, best_child


def _expand(node: Node, board: Board, evaluator) -> float:
    """展開葉節點；回傳該局面（走子方視角）的 value。終局回 -1（走子方已負）。"""
    legal = board.legal_moves()
    if not legal:
        return -1.0
    priors, value = evaluator(board, legal)
    for mv in legal:
        node.children[mv] = Node(priors.get(mv, 0.0))
    return value


def puct_search(board: Board, evaluator=material_evaluator, sims: int = 400,
                c_puct: float = 1.5) -> int | None:
    """跑 sims 次 PUCT 模擬，回傳訪問數最多的著法（robust child）。無合法著法回 None。"""
    root = Node(0.0)
    if _expand(root, board, evaluator) == -1.0 and not root.children:
        return None
    if not root.children:
        return None

    for _ in range(sims):
        b = board.clone()
        node = root
        path = [root]
        # Selection：沿 PUCT 下探到葉
        while node.children:
            mv, node = _select(node, c_puct)
            b.make_move(mv)
            path.append(node)
        # Expansion + Evaluation
        value = _expand(node, b, evaluator)
        # Backpropagation（逐層翻轉視角）
        for n in reversed(path):
            n.n += 1
            n.w += value
            value = -value

    return max(root.children.items(), key=lambda kv: kv[1].n)[0]


def visit_distribution(board: Board, evaluator=material_evaluator, sims: int = 400,
                       c_puct: float = 1.5) -> dict[int, int]:
    """回傳根節點各著法的訪問次數（供自我對弈產生訓練用的 policy 目標）。"""
    root = Node(0.0)
    _expand(root, board, evaluator)
    for _ in range(sims):
        b = board.clone()
        node = root
        path = [root]
        while node.children:
            mv, node = _select(node, c_puct)
            b.make_move(mv)
            path.append(node)
        value = _expand(node, b, evaluator)
        for n in reversed(path):
            n.n += 1
            n.w += value
            value = -value
    return {mv: ch.n for mv, ch in root.children.items()}
