"""把 XiangqiNet 包成 PUCT 用的評估器：evaluator(board, legal) -> (priors, value)。

需 torch（GPU 端）。本機無 torch，僅定義。
"""

from __future__ import annotations

import torch
import torch.nn.functional as F

from xiangqi.encode import board_to_planes, move_to_index


class NNEvaluator:
    def __init__(self, net, device: str = "cpu") -> None:
        self.net = net
        self.device = device

    @torch.no_grad()
    def __call__(self, board, legal):
        planes = board_to_planes(board)
        x = torch.tensor(planes, dtype=torch.float32, device=self.device).unsqueeze(0)
        logits, value = self.net(x)
        logits = logits[0]
        # 只在合法著法上做 softmax，得到 prior
        idxs = [move_to_index(m) for m in legal]
        sel = logits[idxs]
        probs = F.softmax(sel, dim=0)
        priors = {m: float(probs[i]) for i, m in enumerate(legal)}
        return priors, float(value.item())

    @torch.no_grad()
    def batch(self, items):
        """批次評估。items = [(board, legal), ...]，一次前向算完，回傳 [(priors, value), ...]。

        神經網路算 1 個與算 N 個盤面耗時相近，批次可把每步的前向次數大幅攤平。
        """
        if not items:
            return []
        planes = [board_to_planes(b) for b, _ in items]
        x = torch.tensor(planes, dtype=torch.float32, device=self.device)
        logits, value = self.net(x)  # [B, 8100], [B]
        out = []
        for i, (_b, legal) in enumerate(items):
            idxs = [move_to_index(m) for m in legal]
            sel = logits[i][idxs]
            probs = F.softmax(sel, dim=0)
            priors = {m: float(probs[j]) for j, m in enumerate(legal)}
            out.append((priors, float(value[i].item())))
        return out
