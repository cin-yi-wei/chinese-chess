"""多 worker 平行自我對弈：每個 worker 行程各自跑整局，且各自用「批次葉評估」。

- 把 CPU 端的樹走訪分到多核(單行程只用 ~1 核)；每個 worker 內部仍是每步一次 GPU 批次前向。
- 不改規則/編碼/PUCT/網路邏輯：worker 只是呼叫 selfplay.play_game。
- 官方權重 latest.pt 維持純 state_dict；worker 每輪從一份權重檔載入當前網路。

Windows/CUDA 用 spawn 啟動；worker 以 --multiprocessing-fork 形式存在（收工要一起殺）。
"""

from __future__ import annotations

import torch

import config
from net import XiangqiNet
from nn_eval import NNEvaluator
from selfplay import play_game, play_game_vs_opponent

_net = None
_ev = None
_opp = None
_loaded_version = None


def _init_worker(channels: int, blocks: int) -> None:
    """每個 worker 啟動時呼叫一次：建立網路 + 批次評估器（課程模式再各自開一個 oppd）。"""
    global _net, _ev, _opp
    torch.set_num_threads(1)  # 各 worker 單執行緒，避免互搶 CPU
    device = "cuda" if torch.cuda.is_available() else "cpu"
    _net = XiangqiNet(channels, blocks).to(device).eval()
    _ev = NNEvaluator(_net, device)
    if getattr(config, "OPPONENT_DEPTH", 0) > 0:
        from abopp import AlphaBetaOpponent
        _opp = AlphaBetaOpponent()


def _play_one(task):
    """task 帶局序號、當前權重版本與所有自對弈參數。回傳一局樣本。"""
    global _loaded_version
    (idx, weights_path, version, sims, temp_moves, max_moves, c_puct,
     batch_size, dir_alpha, dir_frac) = task
    if _loaded_version != version:
        device = next(_net.parameters()).device
        _net.load_state_dict(torch.load(weights_path, map_location=device))
        _net.eval()
        _loaded_version = version
    if _opp is not None:
        # 課程模式：AZ vs 老師，依局序號輪流執紅/黑
        return play_game_vs_opponent(_ev, _opp, config.OPPONENT_DEPTH, idx % 2 == 0,
                                     sims, temp_moves, max_moves, c_puct,
                                     batch_size, dir_alpha, dir_frac)
    return play_game(_ev, sims, temp_moves, max_moves, c_puct,
                     batch_size, dir_alpha, dir_frac)


class SelfPlayPool:
    """持久化 worker pool（跨 iteration 重用，省去反覆初始化 CUDA）。"""

    def __init__(self, num_workers: int, channels: int, blocks: int) -> None:
        import multiprocessing as mp

        ctx = mp.get_context("spawn")
        self.pool = ctx.Pool(processes=num_workers,
                             initializer=_init_worker, initargs=(channels, blocks))
        self.num_workers = num_workers

    def generate(self, weights_path: str, version: int, n_games: int):
        """派發 n_games 局（帶局序號供課程模式輪流執紅/黑），回傳攤平後的訓練樣本 list。"""
        base = (weights_path, version, config.SIMS, config.TEMP_MOVES, config.MAX_MOVES,
                config.C_PUCT, config.SELFPLAY_BATCH, config.DIRICHLET_ALPHA,
                config.DIRICHLET_FRAC)
        tasks = [(i, *base) for i in range(n_games)]
        results = self.pool.map(_play_one, tasks)
        return [s for game in results for s in game]

    def close(self) -> None:
        self.pool.close()
        self.pool.join()
