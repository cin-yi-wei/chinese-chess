"""監督式模仿暖啟動 + DAgger：訓練網路模仿 Rust alpha-beta 的著法（policy）+ 局面結果（value）。

為什麼：從零 RL 在這台啟動不起來（網路全輸→value 目標全 -1→退化）。改用「直接模仿老師的
著法」把競爭力灌進網路，不需要贏任何一盤。

兩種資料模式（config.DAGGER）：
- False（純模仿）：以老師的軌跡（+eps 隨機）走子，每個局面記老師著法。worker 只用 oppd（純 CPU、快）。
- True（DAgger）：以「網路自己的手」走子（+eps 隨機），每個局面仍記「老師的正解」當標籤。
  → 訓練分佈 = 網路自己會遇到的局面（含它自己犯的錯）→ 修分佈偏移，才能贏過老師的水準。
  worker 需要 net（走子）+ oppd（標註），每輪從權重檔重載當前網路。

policy = cross-entropy 到老師著法；value = MSE 到結果；指標 match%（首選==老師）。
存 checkpoints_imit/（不動 checkpoints/）。
"""

from __future__ import annotations

import os
import time
import random
from collections import deque

import torch
import torch.nn.functional as F

import config
from xiangqi.board import Board
from xiangqi.encode import board_to_planes, move_to_index
from net import XiangqiNet
from selfplay import _material_result

CKPT = "checkpoints_imit"

# ---- worker 全域 ----
_opp = None
_net = None
_ev = None
_loaded_version = None


def _init_worker(channels, blocks, dagger):
    global _opp, _net, _ev
    torch.set_num_threads(1)
    from abopp import AlphaBetaOpponent
    _opp = AlphaBetaOpponent()
    if dagger:
        from nn_eval import NNEvaluator
        device = "cuda" if torch.cuda.is_available() else "cpu"
        _net = XiangqiNet(channels, blocks).to(device).eval()
        _ev = NNEvaluator(_net, device)


def _gen_one(task):
    """一局，回傳 [(planes, 老師著法index, 走子方)]（label 永遠是老師正解）。value=整局結果。

    純模仿：走子=老師(+eps)，每個局面都記。
    DAgger：軌跡=「網路 vs 老師」對局（網路執 idx%2 的顏色，對手用 oppd）；
            只在網路的回合記樣本，標籤=該局面老師的正解 → 涵蓋部署時實際會遇到的局面。
    """
    global _loaded_version
    idx, dagger, weights_path, version, depth, eps, max_moves = task
    if dagger and _loaded_version != version:
        dev = next(_net.parameters()).device
        _net.load_state_dict(torch.load(weights_path, map_location=dev))
        _net.eval()
        _loaded_version = version

    b = Board.start()
    # 隨機開局：訓練涵蓋多樣局面（對齊隨機開局評測，修通用化）
    for _ in range(random.randint(0, int(getattr(config, "IMITATE_RAND_OPEN", 0)))):
        legal0 = b.legal_moves()
        if not legal0:
            break
        b.make_move(random.choice(legal0))
    hist = []
    result = 0.0
    decisive = False
    az_is_red = (idx % 2 == 0)  # DAgger：網路的顏色（輪流）
    opp_depth = random.randint(1, depth)  # 混合對手：對手用隨機深度，逼網路學通用應對
    for _ in range(max_moves):
        legal = b.legal_moves()
        if not legal:
            result = -1.0 if b.red_to_move else 1.0
            decisive = True
            break
        if not dagger:
            ab = _opp.best_move(b, depth)
            if ab is None:
                result = -1.0 if b.red_to_move else 1.0
                decisive = True
                break
            hist.append((board_to_planes(b), move_to_index(ab), b.red_to_move))
            mv = random.choice(legal) if random.random() < eps else ab
        elif b.red_to_move == az_is_red:
            # 網路的回合：標籤=強老師(depth)正解；實際走網路的手(+eps 探索)
            ab = _opp.best_move(b, depth)
            if ab is None:
                result = -1.0 if b.red_to_move else 1.0
                decisive = True
                break
            hist.append((board_to_planes(b), move_to_index(ab), b.red_to_move))
            if random.random() < eps:
                mv = random.choice(legal)
            else:
                priors, _v = _ev(b, legal)
                mv = max(priors, key=priors.get)
        else:
            # 對手的回合：用隨機深度的老師走（混合對手，避免過擬合單一對手），不記樣本
            mv = _opp.best_move(b, opp_depth)
            if mv is None:
                result = -1.0 if b.red_to_move else 1.0
                decisive = True
                break
        b.make_move(mv)
    if not decisive:
        result = _material_result(b)
    return [(p, i, (result if red else -result)) for (p, i, red) in hist]


def _save(obj, path):
    tmp = path + ".tmp"
    torch.save(obj, tmp)
    os.replace(tmp, path)


def main():
    import multiprocessing as mp

    device = "cuda" if torch.cuda.is_available() else "cpu"
    depth = int(getattr(config, "IMITATE_DEPTH", 3))
    eps = float(getattr(config, "IMITATE_EPS", 0.2))
    dagger = bool(getattr(config, "DAGGER", False))
    os.makedirs(CKPT, exist_ok=True)
    latest = os.path.join(CKPT, "latest.pt")
    ts_path = os.path.join(CKPT, "train_state.pt")
    worker_weights = os.path.join(CKPT, "_worker.pt")

    net = XiangqiNet(config.CHANNELS, config.BLOCKS).to(device)
    opt = torch.optim.Adam(net.parameters(), lr=config.LR, weight_decay=config.WEIGHT_DECAY)
    start_iter = 0
    if os.path.exists(latest):
        net.load_state_dict(torch.load(latest, map_location=device))
        if os.path.exists(ts_path):
            st = torch.load(ts_path, map_location=device, weights_only=False)
            opt.load_state_dict(st["opt"])
            start_iter = int(st["iter"]) + 1
        print(f"resumed imitation from iter {start_iter}", flush=True)
    print(f"imitation warm-start: teacher depth={depth}, eps={eps}, DAgger={dagger}, "
          f"workers={config.NUM_WORKERS}, device={device}", flush=True)

    ctx = mp.get_context("spawn")
    pool = ctx.Pool(config.NUM_WORKERS, initializer=_init_worker,
                    initargs=(config.CHANNELS, config.BLOCKS, dagger))

    replay: deque = deque(maxlen=config.REPLAY_WINDOW)
    run_start = time.time()
    max_seconds = config.MAX_MINUTES * 60 if getattr(config, "MAX_MINUTES", 0) else None

    try:
        for it in range(start_iter, config.ITERATIONS):
            t0 = time.time()
            if dagger:
                _save(net.state_dict(), worker_weights)  # 給 worker 走子用的當前網路
            tasks = [(i, dagger, worker_weights, it, depth, eps, config.MAX_MOVES)
                     for i in range(config.GAMES_PER_ITER)]
            results = pool.map(_gen_one, tasks)
            games = [s for g in results for s in g]
            sp_dt = time.time() - t0

            planes = torch.tensor([s[0] for s in games], dtype=torch.float32)
            pidx = torch.tensor([s[1] for s in games], dtype=torch.long)
            z = torch.tensor([s[2] for s in games], dtype=torch.float32)
            replay.append((planes, pidx, z))
            X = torch.cat([b[0] for b in replay], 0)
            P = torch.cat([b[1] for b in replay], 0)
            Z = torch.cat([b[2] for b in replay], 0)
            N = X.shape[0]
            print(f"[imit {it}] {config.GAMES_PER_ITER} games -> {len(games)} samples "
                  f"in {sp_dt:.0f}s; replay total={N}", flush=True)

            net.train()
            lp = lv = None
            for _epoch in range(config.EPOCHS):
                perm = torch.randperm(N)
                for i in range(0, N, config.BATCH_SIZE):
                    idx = perm[i:i + config.BATCH_SIZE]
                    x = X[idx].to(device)
                    tgt = P[idx].to(device)
                    zz = Z[idx].to(device)
                    logits, value = net(x)
                    lp = F.cross_entropy(logits, tgt)
                    lv = F.mse_loss(value, zz)
                    loss = lp + lv
                    opt.zero_grad()
                    loss.backward()
                    opt.step()

            _save(net.state_dict(), os.path.join(CKPT, f"net_{it:04d}.pt"))
            _save(net.state_dict(), latest)
            _save({"opt": opt.state_dict(), "iter": it}, ts_path)

            net.eval()
            with torch.no_grad():
                k = min(1024, N)
                pred = net(X[:k].to(device))[0].argmax(1).cpu()
                match = (pred == P[:k]).float().mean().item()
            elapsed = (time.time() - run_start) / 60
            print(f"[imit {it}] saved  loss_p={lp.item():.3f} loss_v={lv.item():.3f} "
                  f"match={match*100:.0f}%  elapsed={elapsed:.1f} min", flush=True)

            if max_seconds and (time.time() - run_start) >= max_seconds:
                print(f"reached MAX_MINUTES={config.MAX_MINUTES}; stopping after iter {it}.",
                      flush=True)
                break
    finally:
        pool.close()


if __name__ == "__main__":
    main()
