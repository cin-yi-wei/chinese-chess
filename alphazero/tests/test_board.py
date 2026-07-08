"""象棋規則 sanity 測試（與主線 Rust 引擎同錨點）。"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from xiangqi import Board, START_FEN, coord_to_sq, make_move_code  # noqa: E402


def test_start_has_32_pieces():
    b = Board.start()
    assert sum(1 for p in b.squares if p != 0) == 32


def test_start_red_to_move():
    assert Board.start().red_to_move is True


def test_start_has_44_legal_moves():
    # 中國象棋標準開局合法著法數為 44（公認值、移植正確性錨點）
    b = Board.start()
    assert len(b.legal_moves()) == 44


def test_make_undo_restores():
    b = Board.start()
    before = b.squares[:]
    mv = b.legal_moves()[0]
    assert b.make_move(mv)
    b.undo_make_move()
    assert b.squares == before
    assert b.red_to_move is True


def test_fen_roundtrip():
    b = Board.start()
    assert b.to_fen() == START_FEN


def test_repetition_cycle_legal():
    # 紅馬 (1,9)->(2,7)、黑馬 (1,0)->(2,2) 及走回，皆合法
    sq = coord_to_sq
    b = Board.start()
    cycle = [
        make_move_code(sq(1, 9), sq(2, 7)),
        make_move_code(sq(1, 0), sq(2, 2)),
        make_move_code(sq(2, 7), sq(1, 9)),
        make_move_code(sq(2, 2), sq(1, 0)),
    ]
    for mv in cycle:
        assert b.make_move(mv)
    assert b.to_fen() == START_FEN
