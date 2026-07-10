"""Python 端呼叫 Rust alpha-beta 守護程序(oppd)取得對手著法。

- 常駐一個 oppd 子行程,每步用 FEN + 走子方問它「這局面 depth N 的最佳著法」。
- 交換格式:盤面用 FEN(Python/Rust 同格式)、著法用座標 (fx,fy,tx,ty)。
- 不需要 torch;純粹當「固定強度老師」供課程訓練。
"""

from __future__ import annotations

import os
import subprocess

from xiangqi.board import coord_to_sq, make_move_code

# oppd.exe 相對於 alphazero/ 的位置(repo 根的 target/release）
_OPPD = os.path.join(os.path.dirname(__file__), "..", "target", "release", "oppd.exe")


class AlphaBetaOpponent:
    """常駐 Rust alpha-beta 引擎,當自我對弈的固定老師。"""

    def __init__(self, exe: str | None = None) -> None:
        self.exe = exe or _OPPD
        if not os.path.exists(self.exe):
            raise FileNotFoundError(f"找不到 oppd 執行檔:{self.exe}(先 cargo build --release --bin oppd)")
        self.proc = subprocess.Popen(
            [self.exe],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            text=True, bufsize=1,
        )

    def best_move(self, board, depth: int):
        """回傳 Python 著法碼;無合法著法回 None。"""
        stm = "r" if board.red_to_move else "b"
        self.proc.stdin.write(f"{depth} {stm} {board.to_fen()}\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline().strip()
        if not line or line == "none":
            return None
        fx, fy, tx, ty = (int(v) for v in line.split())
        return make_move_code(coord_to_sq(fx, fy), coord_to_sq(tx, ty))

    def close(self) -> None:
        try:
            self.proc.stdin.write("quit\n")
            self.proc.stdin.flush()
        except Exception:
            pass
        try:
            self.proc.wait(timeout=3)
        except Exception:
            self.proc.kill()
