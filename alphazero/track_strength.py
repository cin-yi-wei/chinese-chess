"""棋力追蹤：評測最新檢查點對「固定基準」的勝率，追加到 strength_log.csv。

用法（在 alphazero/ 下，PYTHONPATH=.）：
    python track_strength.py [games=6] [sims=100]
評測最新的 net_XXXX.pt（不可變檔，避免與訓練搶寫 latest.pt）：
  - vs net_0028.pt（開練前基準）→ 相對進步
  - vs material（子力基準）      → 絕對門檻
用子力判定（adj）較敏感。建議在訓練暫停時跑（GPU 才不會被搶）。
"""

from __future__ import annotations

import sys
import os
import re
import glob
import datetime

import torch

import config
from eval import make_evaluator, play_one

LOG = "training.log"
CSV = "strength_log.csv"
ANCHOR = "checkpoints/net_0028.pt"


def _cumulative_games(path: str):
    per = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8", errors="ignore") as f:
            for line in f:
                m = re.search(r"\[iter (\d+)\] self-play (\d+) games", line)
                if m:
                    per[int(m.group(1))] = int(m.group(2))
    return (sum(per.values()), max(per)) if per else (0, -1)


def _winrate(net_spec, opp_spec, n, sims, device):
    nn = make_evaluator(net_spec, device)
    opp = make_evaluator(opp_spec, device)
    w = l = d = 0
    for i in range(n):
        if i % 2 == 0:
            res = play_one(nn, opp, sims, config.C_PUCT, config.MAX_MOVES, True)
        else:
            res = -play_one(opp, nn, sims, config.C_PUCT, config.MAX_MOVES, True)
        w += res > 0
        l += res < 0
        d += res == 0
    return (w + 0.5 * d) / n * 100


def main():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    sims = int(sys.argv[2]) if len(sys.argv) > 2 else 100

    ckpts = sorted(glob.glob("checkpoints/net_*.pt"))
    latest = ckpts[-1] if ckpts else "checkpoints/latest.pt"
    games, it = _cumulative_games(LOG)

    vs28 = _winrate(latest, ANCHOR, n, sims, device)
    vsmat = _winrate(latest, "material", n, sims, device)

    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    if not os.path.exists(CSV):
        with open(CSV, "w", encoding="utf-8") as f:
            f.write("time,iter,cum_games,winrate_vs_net0028,winrate_vs_material,n_games\n")
    with open(CSV, "a", encoding="utf-8") as f:
        f.write(f"{ts},{it},{games},{vs28:.0f},{vsmat:.0f},{n}\n")
    print(f"logged: iter={it} cum_games={games} vs_net0028={vs28:.0f}% "
          f"vs_material={vsmat:.0f}% (using {os.path.basename(latest)})", flush=True)


if __name__ == "__main__":
    main()
