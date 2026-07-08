"""AlphaZero 式 policy + value 雙頭殘差網路（PyTorch）。

輸入：15×10×9 平面（見 xiangqi/encode.py）。
輸出：policy logits（8100 = from×to）、value（tanh，[-1,1]，紅方視角勝率傾向）。

需 torch（在 4070 Ti Super/Windows 上跑）。本機（無 torch）不執行，僅定義。
"""

from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F

from xiangqi.encode import NUM_PLANES, BOARD_H, BOARD_W, POLICY_SIZE


class ResBlock(nn.Module):
    def __init__(self, ch: int) -> None:
        super().__init__()
        self.c1 = nn.Conv2d(ch, ch, 3, padding=1, bias=False)
        self.b1 = nn.BatchNorm2d(ch)
        self.c2 = nn.Conv2d(ch, ch, 3, padding=1, bias=False)
        self.b2 = nn.BatchNorm2d(ch)

    def forward(self, x):
        y = F.relu(self.b1(self.c1(x)))
        y = self.b2(self.c2(y))
        return F.relu(x + y)


class XiangqiNet(nn.Module):
    """channels 與 blocks 可調；PoC 用小網路，正式訓練再加大。"""

    def __init__(self, channels: int = 128, blocks: int = 10) -> None:
        super().__init__()
        self.stem = nn.Sequential(
            nn.Conv2d(NUM_PLANES, channels, 3, padding=1, bias=False),
            nn.BatchNorm2d(channels),
            nn.ReLU(inplace=True),
        )
        self.res = nn.Sequential(*[ResBlock(channels) for _ in range(blocks)])

        # policy head
        self.p_conv = nn.Sequential(
            nn.Conv2d(channels, 4, 1, bias=False),
            nn.BatchNorm2d(4),
            nn.ReLU(inplace=True),
        )
        self.p_fc = nn.Linear(4 * BOARD_H * BOARD_W, POLICY_SIZE)

        # value head
        self.v_conv = nn.Sequential(
            nn.Conv2d(channels, 2, 1, bias=False),
            nn.BatchNorm2d(2),
            nn.ReLU(inplace=True),
        )
        self.v_fc1 = nn.Linear(2 * BOARD_H * BOARD_W, 128)
        self.v_fc2 = nn.Linear(128, 1)

    def forward(self, x):
        x = self.stem(x)
        x = self.res(x)

        p = self.p_conv(x).flatten(1)
        p = self.p_fc(p)  # logits，外面再配合 legal mask 做 softmax

        v = self.v_conv(x).flatten(1)
        v = F.relu(self.v_fc1(v))
        v = torch.tanh(self.v_fc2(v)).squeeze(-1)
        return p, v
