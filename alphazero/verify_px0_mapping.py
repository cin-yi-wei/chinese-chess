"""驗證「我方 Board ↔ px0 GameState」的 FEN + 著法映射正確性。

只用 px0 的棋規(gs.moves(),編譯進 .pyd,不需 backend/CUDA)與我方 board.legal_moves()。
在多個隨機局面(含黑方走子、中局)比對兩邊合法著法集合是否完全一致。
用法：從 alphazero 目錄跑：  python verify_px0_mapping.py
"""

from __future__ import annotations

import random

from xiangqi.board import Board
from px0_encode import board_to_px0_fen, my_move_to_px0
import backends


def check_position(board) -> tuple[bool, str]:
    my_legal = board.legal_moves()
    my_set = {my_move_to_px0(mv) for mv in my_legal}
    gs = backends.GameState(board_to_px0_fen(board))
    px0_set = set(gs.moves())
    if my_set == px0_set:
        return True, ""
    only_mine = my_set - px0_set
    only_px0 = px0_set - my_set
    msg = (f"FEN={board_to_px0_fen(board)}\n"
           f"  我方 {len(my_set)} 著、px0 {len(px0_set)} 著\n"
           f"  只在我方: {sorted(only_mine)}\n"
           f"  只在 px0: {sorted(only_px0)}")
    return False, msg


def main() -> None:
    random.seed(1234)
    # 1) 起始盤面
    b = Board.start()
    ok, msg = check_position(b)
    print(f"[startpos] {'OK' if ok else 'FAIL'}  合法著法={len(b.legal_moves())}")
    if not ok:
        print(msg)

    # 2) 隨機自對弈走子,沿路每一步都比對(含黑方視角)
    n_checked, n_fail = 1, 0 if ok else 1
    for game in range(200):
        b = Board.start()
        for _ply in range(60):
            legal = b.legal_moves()
            if not legal:
                break
            ok, msg = check_position(b)
            n_checked += 1
            if not ok:
                n_fail += 1
                print(f"[game {game} ply {_ply}] FAIL")
                print(msg)
                if n_fail >= 5:
                    print("...太多失敗,中止")
                    print(f"\n總計:{n_checked} 局面,{n_fail} 失敗")
                    return
            b.make_move(random.choice(legal))

    print(f"\n總計:{n_checked} 局面,{n_fail} 失敗")
    if n_fail == 0:
        print("[PASS] 映射完全正確:每個局面兩邊合法著法集合逐一吻合(含黑方走子)")


if __name__ == "__main__":
    main()
