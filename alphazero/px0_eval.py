"""把 px0(PikaXiangqiZero)的強權重包成 PUCT 用的評估器。

介面與 nn_eval.NNEvaluator 相同：
    evaluator(board, legal) -> (priors: dict[move -> float], value: float)
    evaluator.batch([(board, legal), ...]) -> [(priors, value), ...]
  - priors：對「我方 legal 著法」的機率分佈（和為 1）
  - value：目前走子方視角的局面評價 [-1, 1]，越大越好（= WDL 的 win - loss，與 px0 同慣例）

為何走 ONNX：px0 repo 的 C++ 神經後端(blas/cuda/cudnn)全是沒 port 的西洋棋 8×8=64 碼，
對象棋 9×10=90 會崩/算錯。px0 真正的推論路徑是 ONNX（converter.cc 象棋感知）。
故用 `lc0.exe leela2onnx` 把權重轉成 .onnx，交給 onnxruntime 跑。

管線：
  1. 我方 Board → px0 FEN（board_to_px0_fen）→ px0 GameState
  2. GameState.as_input(trivial 後端).expand() → 124×90 float（C++ 端展開，保住 90 位；
     Python 的 mask() 會截成 64 位，故不能用）→ reshape [124,10,9]
  3. onnxruntime 前向 → policy[2062]、wdl[3]
  4. GameState.moves()[i] ↔ policy_indices()[i]，用我方 move→px0 字串查 policy index
     （映射已由 verify_px0_mapping.py 驗證：11993 局面 0 失敗）
  5. 只在我方 legal 著法上做 softmax → priors；value = w - l
"""

from __future__ import annotations

import os
import sys

import numpy as np

from xiangqi.board import sq_to_coord, move_src, move_dst

_PX0_BUILDDIR = os.environ.get(
    "PX0_BUILDDIR",
    r"C:\Users\conra\project\chinese-chess\px0\builddir",
)
if _PX0_BUILDDIR not in sys.path:
    sys.path.insert(0, _PX0_BUILDDIR)

import backends          # noqa: E402  (需先設好 sys.path)
import onnxruntime as ort  # noqa: E402


def _sq_to_px0(sq: int) -> str:
    x, y = sq_to_coord(sq)
    return chr(ord("a") + x) + chr(ord("0") + (9 - y))


def my_move_to_px0(mv: int) -> str:
    """我方 move code → px0 著法字串（4 字元），如 'b2b9'。"""
    return _sq_to_px0(move_src(mv)) + _sq_to_px0(move_dst(mv))


def board_to_px0_fen(board) -> str:
    stm = "w" if board.red_to_move else "b"
    return f"{board.to_fen()} {stm} - - 0 1"


class Px0Evaluator:
    """用 px0 權重（經 ONNX）輸出 (priors, value)，介面同 NNEvaluator。

    weights_path：px0 lc0 格式權重（.pb.gz），只用來讓綁定做輸入編碼/著法索引。
    onnx_path   ：leela2onnx 轉出的 .onnx（實際推論用）。
    providers   ：onnxruntime 執行提供者。預設 CPU；GPU 可用
                  ['DmlExecutionProvider']（pip install onnxruntime-directml）或
                  ['CUDAExecutionProvider']（需相容的 onnxruntime-gpu）。
    """

    def __init__(self, onnx_path: str,
                 providers: list[str] | None = None) -> None:
        # 編碼器與權重解耦：as_input 只需 input_format(所有 pxzero 網路都是 1)，
        # trivial 後端免權重即可提供。這也繞過大網路(≥150MB)讓綁定 Weights() segfault
        # 的問題——推論全交給 onnx，綁定只負責「輸入編碼 + 著法索引」(純棋規)。
        self._enc = backends.Backend(backend="trivial")
        if providers is None:
            # 自動：有 DirectML(GPU) 就用，否則 CPU。MCTS 建議 batch_size=64。
            avail = ort.get_available_providers()
            providers = (["DmlExecutionProvider"]
                         if "DmlExecutionProvider" in avail
                         else ["CPUExecutionProvider"])
        self.session = ort.InferenceSession(onnx_path, providers=providers)
        self._in_name = self.session.get_inputs()[0].name
        outs = {o.name: o.name for o in self.session.get_outputs()}
        self._pol_name = next(n for n in outs if n.endswith("policy"))
        self._wdl_name = next(n for n in outs if n.endswith("wdl"))

    # lc0 網路吃最近 HISTORY 步的局面當輸入平面；不給歷史會讓網路以為局面停滯/重複，
    # 中局 value/policy 全亂（實測無歷史時 value 每步在 ±0.9 亂跳）。
    HISTORY = 8

    def _make_gamestate(self, board):
        """用 board.move_stack 還原最近 HISTORY 步歷史，建帶歷史的 GameState。

        回溯 K 步取「K 步前的局面 FEN」當起點，再餵這 K 步著法字串。
        （比從開局重放整局快；K 步前的局面即 lc0 需要的歷史視窗起點。）
        """
        stack = board.move_stack
        k = min(self.HISTORY, len(stack))
        if k == 0:
            return backends.GameState(board_to_px0_fen(board))
        tmp = board.clone()
        for _ in range(k):
            tmp.undo_make_move()
        start_fen = board_to_px0_fen(tmp)
        hist = [my_move_to_px0(m) for m in stack[len(stack) - k:]]
        return backends.GameState(start_fen, hist)

    def batch(self, items):
        """items = [(board, legal), ...] → [(priors, value), ...]，一次批次前向。"""
        if not items:
            return []
        planes = np.empty((len(items), 124, 10, 9), dtype=np.float32)
        strmaps = []  # 每局面: {px0著法字串: policy index}
        for k, (board, _legal) in enumerate(items):
            gs = self._make_gamestate(board)
            planes[k] = np.frombuffer(gs.as_input(self._enc).expand(),
                                      dtype=np.float32).reshape(124, 10, 9)
            strmaps.append(dict(zip(gs.moves(), gs.policy_indices())))

        pol, wdl = self.session.run(
            [self._pol_name, self._wdl_name], {self._in_name: planes})

        result = []
        for k, (board, legal) in enumerate(items):
            strmap = strmaps[k]
            row = pol[k]
            idxs = [strmap.get(my_move_to_px0(mv), -1) for mv in legal]
            logits = np.array([row[i] if i >= 0 else -1e9 for i in idxs],
                              dtype=np.float32)
            m = logits.max()
            e = np.exp(logits - m)
            s = e.sum()
            probs = (e / s) if s > 0 else np.full(len(legal), 1.0 / len(legal))
            priors = {mv: float(probs[i]) for i, mv in enumerate(legal)}
            value = float(wdl[k][0] - wdl[k][2])  # win - loss，走子方視角
            result.append((priors, value))
        return result

    def __call__(self, board, legal):
        return self.batch([(board, legal)])[0]
