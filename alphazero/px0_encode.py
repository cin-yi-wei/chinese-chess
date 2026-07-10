"""純 Python 版 px0 輸入編碼 + 著法索引（零 C++ 相依，供打包/部署用）。

複製 px0 `src/neural/encoder.cc` 的 `EncodePositionForNN`（124 plane）與 `MoveToNNIndex`
（2062 維 policy）。用綁定 `Input.expand()` / `policy_indices()` 當 golden reference 驗證
（見 verify_px0_encode.py，逐局面 bit-exact 比對）。

規格（已從原始碼 + 實測推得）：
  - 124 plane = 15/局面 ×8 歷史 + 4 aux。每 15：7 ours + 7 theirs + 1 重複。
  - px0 棋子順序：rook, advisor, cannon, pawn, knight, bishop, king（與我方 type 順序不同，見 _MY2PX0）。
  - 走子方永遠擺到底端：net_rank = (9 - y) 若紅走、否則 y；net_file = x。ours = 當前走子方。
  - 全部 8 個歷史格都用「當前走子方視角」（C++ 的 flip 交替 + Mirror 等價於此）。
  - 歷史：current + 往前 undo，最多 8 格；不足補零（對應 FEN_ONLY 在 startpos 處 break）。
  - 重複 plane（base+14）：該局面在歷史窗內重複出現則整面設 1。
  - aux：120=we_are_black(黑走整面1)、121=rule50(我們 FEN 固定 0→整面0)、122=0、123=全1(邊界)。
"""

from __future__ import annotations

import json
import os
import sys

import numpy as np

from xiangqi.board import BLACK_TAG, sq_to_coord, move_src, move_dst

# 我方 piece type(KING0 ADVISOR1 BISHOP2 KNIGHT3 ROOK4 CANNON5 PAWN6)
#   → px0 plane 偏移(rook0 advisor1 cannon2 pawn3 knight4 bishop5 king6)
_MY2PX0 = {4: 0, 1: 1, 5: 2, 6: 3, 3: 4, 2: 5, 0: 6}

def _movestrs_path() -> str:
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "px0_movestrs.json")
    if not os.path.exists(p) and hasattr(sys, "_MEIPASS"):  # PyInstaller 凍結後
        p = os.path.join(sys._MEIPASS, "alphazero", "px0_movestrs.json")
    return p


_MOVESTRS = json.load(open(_movestrs_path(), encoding="utf-8"))
_MOVE_INDEX = {s: i for i, s in enumerate(_MOVESTRS)}

HISTORY = 8
KPPB = 15          # planes per board
AUX = KPPB * HISTORY  # 120


def _sq_to_px0(sq: int) -> str:
    x, y = sq_to_coord(sq)
    return chr(ord("a") + x) + chr(ord("0") + (9 - y))


def my_move_to_px0(mv: int) -> str:
    return _sq_to_px0(move_src(mv)) + _sq_to_px0(move_dst(mv))


def _flip_ranks(s: str) -> str:
    """翻轉著法字串兩端的 rank（r → 9-r）：絕對座標 ↔ 內部(走子方在底)視角。"""
    return s[0] + str(9 - int(s[1])) + s[2] + str(9 - int(s[3]))


def board_to_px0_fen(board) -> str:
    """我方 Board → px0 可解析的完整 FEN（供綁定 GameState 用；純推論不需要）。"""
    stm = "w" if board.red_to_move else "b"
    return f"{board.to_fen()} {stm} - - 0 1"


def move_to_nn_index(mv: int, red_to_move: bool) -> int:
    """我方 move code → px0 2062 維 policy 索引。

    MoveToNNIndex 用「內部(走子方在底)視角」；my_move_to_px0 給絕對座標。
    紅走時兩者相同；黑走時要先翻 rank。
    """
    s = my_move_to_px0(mv)
    if not red_to_move:
        s = _flip_ranks(s)
    return _MOVE_INDEX[s]


def _piece_planes(board, red_pov: bool, out, base: int) -> None:
    sq = board.squares
    for s in range(256):
        pc = sq[s]
        if pc == 0:
            continue
        is_red = pc < BLACK_TAG            # 8..14 紅 / 16..22 黑
        off = _MY2PX0[pc & 7]
        ours = (is_red == red_pov)
        plane = base + (off if ours else off + 7)
        x, y = sq_to_coord(s)
        nrank = (9 - y) if red_pov else y  # 走子方擺底端
        out[plane, nrank, x] = 1.0


def _pos_key(board):
    return (bytes(board.squares), board.red_to_move)


def encode(board) -> np.ndarray:
    """我方 Board（含 move_stack）→ [124,10,9] float32 輸入平面。"""
    out = np.zeros((124, 10, 9), dtype=np.float32)
    red_pov = board.red_to_move

    # 歷史：current + 往前 undo，最多 HISTORY 格
    tmp = board.clone()
    positions = [tmp.clone()]
    while len(positions) < HISTORY and tmp.move_stack:
        tmp.undo_make_move()
        positions.append(tmp.clone())

    # 重複偵測：某格局面若在更早(索引更大)出現過 → 設重複面
    keys = [_pos_key(p) for p in positions]
    for i, p in enumerate(positions):
        base = i * KPPB
        _piece_planes(p, red_pov, out, base)
        if keys[i] in keys[i + 1:]:
            out[base + 14, :, :] = 1.0

    # aux
    if not red_pov:
        out[AUX, :, :] = 1.0        # we_are_black
    # AUX+1 = rule50：最近未吃子連續步數，上限 = 歷史窗 k（與 _make_gamestate 從 k 步前
    # FEN(rule50=0)重放一致）。用 capture_stack 尾端計數。
    k = min(HISTORY, len(board.move_stack))
    r50 = 0
    for c in reversed(board.capture_stack[len(board.capture_stack) - k:] if k else []):
        if c == 0:
            r50 += 1
        else:
            break
    out[AUX + 1, :, :] = float(r50)
    # AUX+2 = 0（movecount，恆 0）
    out[AUX + 3, :, :] = 1.0        # 全 1 邊界
    return out
