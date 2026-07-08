"""AlphaZero 訓練主迴圈：自我對弈 → 訓練 → 更強網路 → 再自我對弈…

在使用者的 4070 Ti Super（Windows, CUDA）上跑：
    python train.py
產出 checkpoints/。訓練到「真的強」需反覆很多輪、數天~數週。
"""

from __future__ import annotations

import os
import random
from collections import deque

import torch
import torch.nn.functional as F

import config
from net import XiangqiNet
from nn_eval import NNEvaluator
from selfplay import play_game


def train() -> None:
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"device = {device}")
    net = XiangqiNet(config.CHANNELS, config.BLOCKS).to(device)
    opt = torch.optim.Adam(net.parameters(), lr=config.LR, weight_decay=config.WEIGHT_DECAY)
    os.makedirs(config.CKPT_DIR, exist_ok=True)

    replay: deque = deque(maxlen=config.REPLAY_WINDOW)

    for it in range(config.ITERATIONS):
        # 1) 自我對弈（用目前網路）
        net.eval()
        evaluator = NNEvaluator(net, device)
        games = []
        for _ in range(config.GAMES_PER_ITER):
            games.extend(
                play_game(evaluator, config.SIMS, config.TEMP_MOVES,
                          config.MAX_MOVES, config.C_PUCT)
            )
        replay.append(games)
        data = [s for batch in replay for s in batch]
        print(f"[iter {it}] self-play samples this round={len(games)} total={len(data)}")

        # 2) 訓練
        net.train()
        for _epoch in range(config.EPOCHS):
            random.shuffle(data)
            for i in range(0, len(data), config.BATCH_SIZE):
                batch = data[i:i + config.BATCH_SIZE]
                if not batch:
                    continue
                x = torch.tensor([b[0] for b in batch], dtype=torch.float32, device=device)
                pi = torch.tensor([b[1] for b in batch], dtype=torch.float32, device=device)
                z = torch.tensor([b[2] for b in batch], dtype=torch.float32, device=device)

                logits, value = net(x)
                # policy：軟目標交叉熵 = -Σ pi * log_softmax(logits)
                logp = F.log_softmax(logits, dim=1)
                loss_p = -(pi * logp).sum(dim=1).mean()
                loss_v = F.mse_loss(value, z)
                loss = loss_p + loss_v

                opt.zero_grad()
                loss.backward()
                opt.step()

        # 3) 存檔
        ckpt = os.path.join(config.CKPT_DIR, f"net_{it:04d}.pt")
        torch.save(net.state_dict(), ckpt)
        torch.save(net.state_dict(), os.path.join(config.CKPT_DIR, "latest.pt"))
        print(f"[iter {it}] saved {ckpt}  loss_p={loss_p.item():.3f} loss_v={loss_v.item():.3f}")


if __name__ == "__main__":
    train()
