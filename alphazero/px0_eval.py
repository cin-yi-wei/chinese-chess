"""把 px0(PikaXiangqiZero）的強權重包成 PUCT 用的評估器（純 Python，零 C++ 相依）。

介面與 nn_eval.NNEvaluator 相同：
    evaluator(board, legal) -> (priors: dict[move -> float], value: float)
    evaluator.batch([(board, legal), ...]) -> [(priors, value), ...]
  - priors：對「我方 legal 著法」的機率分佈（和為 1）
  - value：目前走子方視角的局面評價 [-1, 1]，越大越好（= WDL 的 win - loss）

只依賴 numpy + onnxruntime + px0_encode（純 Python 輸入編碼/著法索引，已對綁定 bit-exact 驗證，
見 verify_px0_encode.py）。**不需要 px0 C++ 綁定**——適合 PyInstaller 打包 / 跨平台部署。

權重：用 px0 的 `lc0 leela2onnx` 把 pxzero 網路（.pb.gz）轉成 .onnx（一次性，見 docs/HANDOFF.md）。
輸出節點：/output/policy [2062]、/output/wdl [3]、/output/mlh [1]。
"""

from __future__ import annotations

import numpy as np
import onnxruntime as ort

import px0_encode


class Px0Evaluator:
    """用 px0 權重（經 ONNX）輸出 (priors, value)，介面同 NNEvaluator。

    onnx_path ：leela2onnx 轉出的 .onnx。
    providers ：onnxruntime 執行提供者。預設自動：CUDA → DirectML → CPU。
    """

    def __init__(self, onnx_path: str, providers: list[str] | None = None) -> None:
        if providers is None:
            avail = ort.get_available_providers()
            for p in ("CUDAExecutionProvider", "DmlExecutionProvider", "CPUExecutionProvider"):
                if p in avail:
                    providers = [p]
                    break
        self.session = ort.InferenceSession(onnx_path, providers=providers)
        self._in = self.session.get_inputs()[0].name
        outs = [o.name for o in self.session.get_outputs()]
        self._pol = next(n for n in outs if n.endswith("policy"))
        self._wdl = next(n for n in outs if n.endswith("wdl"))

    def batch(self, items):
        """items = [(board, legal), ...] → [(priors, value), ...]，一次批次前向。"""
        if not items:
            return []
        planes = np.stack([px0_encode.encode(b) for b, _ in items])
        pol, wdl = self.session.run([self._pol, self._wdl], {self._in: planes})
        result = []
        for k, (board, legal) in enumerate(items):
            row = pol[k]
            red = board.red_to_move
            logits = np.array(
                [row[px0_encode.move_to_nn_index(m, red)] for m in legal],
                dtype=np.float32)
            e = np.exp(logits - logits.max())
            s = e.sum()
            probs = (e / s) if s > 0 else np.full(len(legal), 1.0 / len(legal))
            priors = {mv: float(probs[i]) for i, mv in enumerate(legal)}
            value = float(wdl[k][0] - wdl[k][2])   # win - loss，走子方視角
            result.append((priors, value))
        return result

    def __call__(self, board, legal):
        return self.batch([(board, legal)])[0]
