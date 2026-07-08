//! 象棋引擎核心函式庫。
//!
//! 移植自 reference/cpp-console 的 C++ 引擎，採用象棋巫師系經典
//! 256 格（16×16）盤面表示法。此函式庫零 I/O、零框架相依，方便
//! 單元測試，將來也能編成 WASM 或內嵌桌面 App。
//!
//! 里程碑進度：
//!   ② 盤面與著法產生、make/undo、將軍/將死  ✅
//!   ④ 評估函式 + alpha-beta 搜尋            ✅
//!   ⑥ axum WebSocket 服務（在 server crate） ✅
//!   ⑤ MCTS                                   ✅
//!   ③ Zobrist 重複盤面判定                  待辦

pub mod board;
pub mod mcts;
pub mod piece_value;
pub mod search;

pub use board::{Board, Move};
pub use mcts::best_move_mcts;
pub use search::{best_move, best_move_iterative};

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn board_starts_with_red_to_move() {
        let b = Board::start();
        assert!(b.red_to_move, "開局應由紅方先走");
    }

    #[test]
    fn start_position_has_32_pieces() {
        let b = Board::start();
        let count = b.squares.iter().filter(|&&p| p != 0).count();
        assert_eq!(count, 32, "開局盤面應有 32 顆棋子");
    }

    #[test]
    fn start_position_has_44_legal_moves() {
        // 中國象棋標準開局，紅方合法著法數為 44（公認值），
        // 用以驗證著法產生 + 自將過濾移植正確。
        let mut b = Board::start();
        let pseudo = b.generate_moves();
        let mut legal = 0;
        for mv in pseudo {
            if b.make_move(mv) {
                b.undo_make_move();
                legal += 1;
            }
        }
        assert_eq!(legal, 44, "開局合法著法數應為 44");
    }

    #[test]
    fn make_undo_restores_board() {
        // make 後 undo 應完全還原盤面與走子方。
        let mut b = Board::start();
        let before = b.squares;
        let moves = b.generate_moves();
        let mv = *moves.first().expect("開局應有著法");
        assert!(b.make_move(mv));
        b.undo_make_move();
        assert_eq!(b.squares, before, "undo 後盤面應完全還原");
        assert!(b.red_to_move, "undo 後應回到紅方");
    }

    #[test]
    fn start_position_is_balanced() {
        // 開局對稱，任一方視角的評估分應為 0。
        let b = Board::start();
        assert_eq!(b.evaluate(), 0, "開局評估應平衡（0 分）");
    }

    #[test]
    fn search_returns_legal_move_from_start() {
        // 搜尋應從開局回傳一個合法著法。
        let mut b = Board::start();
        let mv = best_move(&mut b, 3).expect("開局應搜得著法");
        let legal: Vec<_> = {
            let mut v = Vec::new();
            for m in b.generate_moves() {
                if b.make_move(m) {
                    b.undo_make_move();
                    v.push(m);
                }
            }
            v
        };
        assert!(legal.contains(&mv), "搜尋回傳的著法應為合法著法");
    }

    #[test]
    fn zobrist_restored_after_undo() {
        let mut b = Board::start();
        let z0 = b.zobrist;
        let mv = *b.legal_moves().first().unwrap();
        assert!(b.make_move(mv));
        assert_ne!(b.zobrist, z0, "走一步後雜湊應改變");
        b.undo_make_move();
        assert_eq!(b.zobrist, z0, "undo 後雜湊應還原");
    }

    #[test]
    fn detects_repetition_and_threefold() {
        let sq = Board::coord_to_sq;
        let mk = board::make_move_code;
        let mut b = Board::start();
        // 紅馬 (1,9)->(2,7)、黑馬 (1,0)->(2,2)、各自走回，四步構成一個還原循環
        let cycle = [
            mk(sq(1, 9), sq(2, 7)),
            mk(sq(1, 0), sq(2, 2)),
            mk(sq(2, 7), sq(1, 9)),
            mk(sq(2, 2), sq(1, 0)),
        ];
        for &m in &cycle {
            assert!(b.make_move(m), "循環著法應合法");
        }
        assert!(b.is_repetition(), "跑完一圈後應偵測到重複盤面");
        // 再跑兩圈 → 三次重複
        for _ in 0..2 {
            for &m in &cycle {
                assert!(b.make_move(m));
            }
        }
        assert!(b.is_threefold(), "跑完三圈應達三次重複");
    }

    #[test]
    fn mcts_returns_legal_move_from_start() {
        // MCTS 應從開局回傳一個合法著法（少量迭代即可驗證流程）。
        let b = Board::start();
        let mv = best_move_mcts(&b, 200).expect("MCTS 應搜得著法");
        let mut bb = Board::start();
        let legal = bb.legal_moves();
        assert!(legal.contains(&mv), "MCTS 回傳的著法應為合法著法");
    }
}
