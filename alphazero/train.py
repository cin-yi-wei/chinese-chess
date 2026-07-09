"""AlphaZero 訓練主迴圈：自我對弈 → 訓練 → 更強網路 → 再自我對弈…

在使用者的 4070 Ti Super（Windows, CUDA）上跑：
    python train.py
產出 checkpoints/。訓練到「真的強」需反覆很多輪、數天~數週。

自我對弈使用批次葉評估 MCTS（見 mcts.visit_distribution_batched），每步一次 GPU 批次前向。
特性：
- 斷點續訓：啟動時自動從 checkpoints/latest.pt + train_state.pt + replay.pt 接續。
- latest.pt 維持「純權重」state_dict（供 prod 直接載入）；訓練狀態(opt/iter)另存 train_state.pt；
  經驗回放另存 replay.pt（以緊湊 tensor 儲存，續訓時一起載入，避免每次重開記憶清空）。
- 以 config.MAX_MINUTES 限制單次執行時間（跑完當前 iteration 後停）。
"""

from __future__ import annotations

import os
import time

import torch
import torch.nn.functional as F
from collections import deque

import config
from net import XiangqiNet
from nn_eval import NNEvaluator
from selfplay import play_game


def _paths():
    d = config.CKPT_DIR
    return (os.path.join(d, "latest.pt"),
            os.path.join(d, "train_state.pt"),
            os.path.join(d, "replay.pt"))


def _games_to_tensors(games):
    """把一輪 self-play 的樣本 list[(planes, pol, z)] 轉成緊湊 tensor 三元組（CPU）。"""
    planes = torch.tensor([s[0] for s in games], dtype=torch.float32)
    pol = torch.tensor([s[1] for s in games], dtype=torch.float32)
    z = torch.tensor([s[2] for s in games], dtype=torch.float32)
    return planes, pol, z


def _resume(net, opt, device, replay):
    """若有既有檢查點就載入（權重 + optimizer + iter + replay），回傳下一個 iteration 編號。"""
    latest, ts_path, replay_path = _paths()
    if not os.path.exists(latest):
        return 0
    net.load_state_dict(torch.load(latest, map_location=device))
    start_iter = 0
    if os.path.exists(ts_path):
        st = torch.load(ts_path, map_location=device, weights_only=False)
        opt.load_state_dict(st["opt"])
        start_iter = int(st["iter"]) + 1
    if os.path.exists(replay_path):
        loaded = torch.load(replay_path, map_location="cpu", weights_only=False)
        for batch in loaded:
            replay.append(batch)
        n = sum(b[2].shape[0] for b in replay)
        print(f"loaded replay: {len(replay)} iters, {n} samples", flush=True)
    print(f"resumed from {latest} -> starting at iter {start_iter}", flush=True)
    return start_iter


def train() -> None:
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"device = {device}", flush=True)
    net = XiangqiNet(config.CHANNELS, config.BLOCKS).to(device)
    opt = torch.optim.Adam(net.parameters(), lr=config.LR, weight_decay=config.WEIGHT_DECAY)
    os.makedirs(config.CKPT_DIR, exist_ok=True)
    latest_path, ts_path, replay_path = _paths()

    replay: deque = deque(maxlen=config.REPLAY_WINDOW)  # 每項 = (planes, pol, z) CPU tensors
    start_iter = _resume(net, opt, device, replay)
    print(f"self-play: SIMS={config.SIMS}, BATCH={config.SELFPLAY_BATCH}, "
          f"GAMES_PER_ITER={config.GAMES_PER_ITER}", flush=True)

    run_start = time.time()
    max_seconds = config.MAX_MINUTES * 60 if getattr(config, "MAX_MINUTES", 0) else None

    for it in range(start_iter, config.ITERATIONS):
        # 1) 自我對弈（用目前網路，批次葉評估）
        net.eval()
        evaluator = NNEvaluator(net, device)
        t0 = time.time()
        games = []
        for _ in range(config.GAMES_PER_ITER):
            games.extend(
                play_game(evaluator, config.SIMS, config.TEMP_MOVES,
                          config.MAX_MOVES, config.C_PUCT, config.SELFPLAY_BATCH)
            )
        sp_dt = time.time() - t0
        replay.append(_games_to_tensors(games))

        # 攤平整個 replay 成訓練張量（CPU；每批再搬上 device）
        X = torch.cat([b[0] for b in replay], 0)
        PI = torch.cat([b[1] for b in replay], 0)
        Z = torch.cat([b[2] for b in replay], 0)
        N = X.shape[0]
        print(f"[iter {it}] self-play {config.GAMES_PER_ITER} games -> {len(games)} samples "
              f"in {sp_dt:.0f}s ({config.GAMES_PER_ITER / sp_dt * 60:.1f} games/min); "
              f"replay total={N}", flush=True)

        # 2) 訓練
        net.train()
        loss_p = loss_v = None
        for _epoch in range(config.EPOCHS):
            perm = torch.randperm(N)
            for i in range(0, N, config.BATCH_SIZE):
                idx = perm[i:i + config.BATCH_SIZE]
                if idx.numel() == 0:
                    continue
                x = X[idx].to(device)
                pi = PI[idx].to(device)
                z = Z[idx].to(device)

                logits, value = net(x)
                logp = F.log_softmax(logits, dim=1)
                loss_p = -(pi * logp).sum(dim=1).mean()
                loss_v = F.mse_loss(value, z)
                loss = loss_p + loss_v

                opt.zero_grad()
                loss.backward()
                opt.step()

        # 3) 存檔：latest.pt 純 state_dict（供 prod）；訓練狀態 + replay 另存（供續訓）
        ckpt = os.path.join(config.CKPT_DIR, f"net_{it:04d}.pt")
        torch.save(net.state_dict(), ckpt)
        torch.save(net.state_dict(), latest_path)
        torch.save({"opt": opt.state_dict(), "iter": it}, ts_path)
        torch.save(list(replay), replay_path)
        lp = loss_p.item() if loss_p is not None else float("nan")
        lv = loss_v.item() if loss_v is not None else float("nan")
        elapsed = (time.time() - run_start) / 60
        print(f"[iter {it}] saved {ckpt}  loss_p={lp:.3f} loss_v={lv:.3f}  "
              f"elapsed={elapsed:.1f} min", flush=True)

        # 4) 到達本次執行時間上限就停（下次啟動會自動續訓）
        if max_seconds and (time.time() - run_start) >= max_seconds:
            print(f"reached MAX_MINUTES={config.MAX_MINUTES}; stopping after iter {it}. "
                  f"Re-run to resume.", flush=True)
            break


if __name__ == "__main__":
    train()
