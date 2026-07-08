"""盤面 → 神經網路輸入張量、著法 ↔ policy 索引的編碼。

- 輸入平面：15 個 10×9 平面 = 紅 7 種 + 黑 7 種棋子各一 + 1 個走子方平面。
- 動作空間：from×to = 90×90 = 8100，policy index = from_idx*90 + to_idx，
  其中 idx = y*9 + x（x:0..8 檔、y:0..9 列）。用合法著法產生 mask。

此模組純 Python（不依賴 numpy），方便在無 GPU 機驗證；訓練端可直接
np.asarray(board_to_planes(...)) 轉張量。
"""

from __future__ import annotations

from .board import (
    Board,
    RED_TAG,
    BLACK_TAG,
    move_src,
    move_dst,
    sq_to_coord,
    make_move_code,
    coord_to_sq,
)

BOARD_H = 10
BOARD_W = 9
NUM_PIECE_PLANES = 14  # 紅 7 + 黑 7
NUM_PLANES = NUM_PIECE_PLANES + 1  # + 走子方
POLICY_SIZE = 90 * 90  # from × to


def _cell_idx(x: int, y: int) -> int:
    return y * BOARD_W + x


def board_to_planes(board: Board) -> list[list[list[float]]]:
    """回傳 shape [15][10][9] 的 0/1 平面（巢狀 list）。"""
    planes = [[[0.0] * BOARD_W for _ in range(BOARD_H)] for _ in range(NUM_PLANES)]
    for y in range(BOARD_H):
        for x in range(BOARD_W):
            pc = board.squares[coord_to_sq(x, y)]
            if pc == 0:
                continue
            pt = pc & 7  # 0..6
            plane = pt if pc < BLACK_TAG else 7 + pt  # 紅 0..6、黑 7..13
            planes[plane][y][x] = 1.0
    # 走子方平面：紅走全 1、黑走全 0
    if board.red_to_move:
        for y in range(BOARD_H):
            for x in range(BOARD_W):
                planes[NUM_PIECE_PLANES][y][x] = 1.0
    return planes


def move_to_index(mv: int) -> int:
    fx, fy = sq_to_coord(move_src(mv))
    tx, ty = sq_to_coord(move_dst(mv))
    return _cell_idx(fx, fy) * 90 + _cell_idx(tx, ty)


def index_to_move(idx: int) -> int:
    frm, to = divmod(idx, 90)
    fx, fy = frm % BOARD_W, frm // BOARD_W
    tx, ty = to % BOARD_W, to // BOARD_W
    return make_move_code(coord_to_sq(fx, fy), coord_to_sq(tx, ty))


def legal_policy_mask(board: Board) -> list[float]:
    """回傳長度 8100 的 0/1 mask，僅合法著法為 1。"""
    mask = [0.0] * POLICY_SIZE
    for mv in board.legal_moves():
        mask[move_to_index(mv)] = 1.0
    return mask
