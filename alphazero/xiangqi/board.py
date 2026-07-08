"""中國象棋盤面與規則，移植自主線 Rust 引擎 engine/src/board.rs。

沿用象棋巫師系 256 格（16×16）表示法：實際棋盤在 rank 3..=12、file 3..=11。
棋子編碼：紅子 8+種類（8..14）、黑子 16+種類（16..22），0 為空格。
著法碼：低 8 位起點格、高 8 位終點格。
以「開局合法著法=44」為移植正確性的驗證錨點（見 tests/）。
"""

from __future__ import annotations

# 棋子種類
PIECE_KING = 0
PIECE_ADVISOR = 1
PIECE_BISHOP = 2
PIECE_KNIGHT = 3
PIECE_ROOK = 4
PIECE_CANNON = 5
PIECE_PAWN = 6

RED_TAG = 8
BLACK_TAG = 16

KING_DELTA = (-16, -1, 1, 16)
ADVISOR_DELTA = (-17, -15, 15, 17)
KNIGHT_DELTA = ((-33, -31), (-18, 14), (-14, 18), (31, 33))
KNIGHT_CHECK_DELTA = ((-33, -18), (-31, -14), (14, 31), (18, 33))

START_FEN = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR"

_CHAR_TO_PIECE = {
    "K": PIECE_KING, "A": PIECE_ADVISOR, "B": PIECE_BISHOP,
    "N": PIECE_KNIGHT, "R": PIECE_ROOK, "C": PIECE_CANNON, "P": PIECE_PAWN,
}
_PIECE_TO_CHAR = {v: k for k, v in _CHAR_TO_PIECE.items()}


def coord_to_sq(x: int, y: int) -> int:
    """前端座標 (x:0..8 檔, y:0..9 列) → 內部格。"""
    return ((y + 3) << 4) + (x + 3)


def sq_to_coord(sq: int) -> tuple[int, int]:
    return (sq & 0x0F) - 3, (sq >> 4) - 3


def move_src(mv: int) -> int:
    return mv & 0xFF


def move_dst(mv: int) -> int:
    return mv >> 8


def make_move_code(src: int, dst: int) -> int:
    return (src & 0xFF) | ((dst & 0xFF) << 8)


def _in_board(sq: int) -> bool:
    if sq < 0 or sq > 255:
        return False
    rank, file = sq >> 4, sq & 0x0F
    return 3 <= rank <= 12 and 3 <= file <= 11


def _in_fort(sq: int) -> bool:
    if sq < 0 or sq > 255:
        return False
    rank, file = sq >> 4, sq & 0x0F
    return (3 <= rank <= 5 or 10 <= rank <= 12) and 6 <= file <= 8


def _home_half(sq: int, sd: int) -> bool:
    return (sq & 0x80) != (sd << 7)


def _away_half(sq: int, sd: int) -> bool:
    return (sq & 0x80) == (sd << 7)


def _square_forward(sq: int, sd: int) -> int:
    return sq - 16 + (sd << 5)


class Board:
    """一個象棋盤面狀態。"""

    __slots__ = ("squares", "red_to_move", "move_stack", "capture_stack")

    def __init__(self) -> None:
        self.squares = [0] * 256
        self.red_to_move = True
        self.move_stack: list[int] = []
        self.capture_stack: list[int] = []

    @classmethod
    def start(cls) -> "Board":
        b = cls()
        b.load_fen(START_FEN)
        return b

    def clone(self) -> "Board":
        b = Board.__new__(Board)
        b.squares = self.squares[:]
        b.red_to_move = self.red_to_move
        b.move_stack = self.move_stack[:]
        b.capture_stack = self.capture_stack[:]
        return b

    # ---- 內部小工具 ----
    def _side(self) -> int:
        return 0 if self.red_to_move else 1

    def _self_tag(self) -> int:
        return RED_TAG + (self._side() << 3)

    def _opp_tag(self) -> int:
        return BLACK_TAG - (self._side() << 3)

    def _at(self, sq: int) -> int:
        return self.squares[sq] if 0 <= sq <= 255 else 0

    # ---- FEN ----
    def load_fen(self, fen: str) -> None:
        self.squares = [0] * 256
        self.red_to_move = True
        self.move_stack.clear()
        self.capture_stack.clear()
        y, x = 3, 3
        for c in fen:
            if c == " ":
                break
            if c == "/":
                x = 3
                y += 1
                if y > 12:
                    break
            elif "1" <= c <= "9":
                x += int(c)
            else:
                pt = _CHAR_TO_PIECE.get(c.upper())
                if pt is not None and x <= 11:
                    tag = RED_TAG if c.isupper() else BLACK_TAG
                    self.squares[x + (y << 4)] = tag + pt
                    x += 1

    def to_fen(self) -> str:
        rows = []
        for y in range(10):
            row, empty = "", 0
            for x in range(9):
                pc = self.squares[coord_to_sq(x, y)]
                if pc == 0:
                    empty += 1
                    continue
                if empty:
                    row += str(empty)
                    empty = 0
                ch = _PIECE_TO_CHAR[pc & 7]
                row += ch if pc < BLACK_TAG else ch.lower()
            if empty:
                row += str(empty)
            rows.append(row)
        return "/".join(rows)

    # ---- 走子 ----
    def _change_side(self) -> None:
        self.red_to_move = not self.red_to_move

    def _move_piece(self, mv: int) -> None:
        s, d = move_src(mv), move_dst(mv)
        self.capture_stack.append(self.squares[d])
        self.squares[d] = self.squares[s]
        self.squares[s] = 0
        self.move_stack.append(mv)

    def _undo_move_piece(self) -> None:
        mv = self.move_stack.pop()
        s, d = move_src(mv), move_dst(mv)
        self.squares[s] = self.squares[d]
        self.squares[d] = self.capture_stack.pop()

    def make_move(self, mv: int) -> bool:
        """走一步；走完自將（送死）則撤銷回 False。"""
        self._move_piece(mv)
        if self.checked():
            self._undo_move_piece()
            return False
        self._change_side()
        return True

    def undo_make_move(self) -> None:
        self._change_side()
        self._undo_move_piece()

    # ---- 將軍 / 將死 ----
    def checked(self) -> bool:
        self_tag = self._self_tag()
        opp_tag = self._opp_tag()
        sd = self._side()
        for sq in range(256):
            if self.squares[sq] != self_tag + PIECE_KING:
                continue
            if self._at(_square_forward(sq, sd)) == opp_tag + PIECE_PAWN:
                return True
            for delta in (-1, 1):
                if self._at(sq + delta) == opp_tag + PIECE_PAWN:
                    return True
            for i in range(4):
                if self._at(sq + ADVISOR_DELTA[i]) != 0:
                    continue
                for j in range(2):
                    if self._at(sq + KNIGHT_CHECK_DELTA[i][j]) == opp_tag + PIECE_KNIGHT:
                        return True
            for i in range(4):
                delta = KING_DELTA[i]
                d = sq + delta
                while _in_board(d):
                    pc = self.squares[d]
                    if pc > 0:
                        if pc == opp_tag + PIECE_ROOK or pc == opp_tag + PIECE_KING:
                            return True
                        break
                    d += delta
                d += delta
                while _in_board(d):
                    pc = self.squares[d]
                    if pc > 0:
                        if pc == opp_tag + PIECE_CANNON:
                            return True
                        break
                    d += delta
            return False
        return False

    def is_mate(self) -> bool:
        for mv in self.generate_moves():
            if self.make_move(mv):
                self.undo_make_move()
                return False
        return True

    # ---- 著法產生 ----
    def generate_moves(self) -> list[int]:
        mvs: list[int] = []
        self_tag = self._self_tag()
        opp_tag = self._opp_tag()
        sd = self._side()
        sq = self.squares
        for src in range(256):
            pc = sq[src]
            if pc & self_tag == 0:
                continue
            pt = pc - self_tag
            if pt == PIECE_KING:
                for i in range(4):
                    dst = src + KING_DELTA[i]
                    if _in_fort(dst) and sq[dst] & self_tag == 0:
                        mvs.append(make_move_code(src, dst))
            elif pt == PIECE_ADVISOR:
                for i in range(4):
                    dst = src + ADVISOR_DELTA[i]
                    if _in_fort(dst) and sq[dst] & self_tag == 0:
                        mvs.append(make_move_code(src, dst))
            elif pt == PIECE_BISHOP:
                for i in range(4):
                    eye = src + ADVISOR_DELTA[i]
                    if not (_in_board(eye) and _home_half(eye, sd) and sq[eye] == 0):
                        continue
                    dst = eye + ADVISOR_DELTA[i]
                    if sq[dst] & self_tag == 0:
                        mvs.append(make_move_code(src, dst))
            elif pt == PIECE_KNIGHT:
                for i in range(4):
                    leg = src + KING_DELTA[i]
                    if self._at(leg) > 0:
                        continue
                    for j in range(2):
                        dst = src + KNIGHT_DELTA[i][j]
                        if _in_board(dst) and sq[dst] & self_tag == 0:
                            mvs.append(make_move_code(src, dst))
            elif pt == PIECE_ROOK:
                for i in range(4):
                    delta = KING_DELTA[i]
                    dst = src + delta
                    while _in_board(dst):
                        pcd = sq[dst]
                        if pcd == 0:
                            mvs.append(make_move_code(src, dst))
                        else:
                            if pcd & opp_tag != 0:
                                mvs.append(make_move_code(src, dst))
                            break
                        dst += delta
            elif pt == PIECE_CANNON:
                for i in range(4):
                    delta = KING_DELTA[i]
                    dst = src + delta
                    while _in_board(dst):
                        if sq[dst] == 0:
                            mvs.append(make_move_code(src, dst))
                        else:
                            break
                        dst += delta
                    dst += delta
                    while _in_board(dst):
                        pcd = sq[dst]
                        if pcd > 0:
                            if pcd & opp_tag != 0:
                                mvs.append(make_move_code(src, dst))
                            break
                        dst += delta
            elif pt == PIECE_PAWN:
                fwd = _square_forward(src, sd)
                if _in_board(fwd) and sq[fwd] & self_tag == 0:
                    mvs.append(make_move_code(src, fwd))
                if _away_half(src, sd):
                    for delta in (-1, 1):
                        dst = src + delta
                        if _in_board(dst) and sq[dst] & self_tag == 0:
                            mvs.append(make_move_code(src, dst))
        return mvs

    def legal_moves(self) -> list[int]:
        legal = []
        for mv in self.generate_moves():
            if self.make_move(mv):
                self.undo_make_move()
                legal.append(mv)
        return legal
