//! Alpha-beta（negamax）搜尋，移植自 reference/cpp-console/search.cpp。
//!
//! 用 negamax 框架：evaluate() 已以走子方視角回傳分值，故遞迴時對子節點
//! 取負即可。原 C++ 版夾雜若干除錯用的過濾條件（SRC/DST<140、repStatus2），
//! 那些非標準搜尋邏輯此處略去，改寫成乾淨的 alpha-beta。
//! 重複盤面判定於里程碑 ③ 併入。

use crate::board::{Board, Move};

/// 將死分值（絕對值上限）。
pub const MATE_VALUE: i16 = 10000;
/// 高於此分值視為勝負已定。
pub const WIN_VALUE: i16 = MATE_VALUE - 200;

/// 從根局面搜尋指定深度，回傳最佳著法；若無合法著法（已被將死/困斃）回傳 None。
///
/// `depth` 即 AI 難度：越大越強、越慢。
pub fn best_move(board: &mut Board, depth: u8) -> Option<Move> {
    let mut best: Option<Move> = None;
    let mut alpha = -MATE_VALUE;
    let beta = MATE_VALUE;

    for mv in board.generate_moves() {
        if !board.make_move(mv) {
            continue; // 送死著法，跳過
        }
        let vl = -alpha_beta(board, -beta, -alpha, depth.saturating_sub(1));
        board.undo_make_move();
        if vl > alpha {
            alpha = vl;
            best = Some(mv);
        }
    }
    best
}

/// 迭代加深：從深度 1 逐層加深到 `max_depth`，取最後完成的最佳著法。
///
/// 提供比固定深度更穩定的著法排序基礎（目前尚未接置換表，僅逐層重算）。
pub fn best_move_iterative(board: &mut Board, max_depth: u8) -> Option<Move> {
    let mut best = None;
    for depth in 1..=max_depth {
        if let Some(mv) = best_move(board, depth) {
            best = Some(mv);
        }
    }
    best
}

/// Negamax alpha-beta 遞迴。回傳以目前走子方視角的最佳分值。
fn alpha_beta(board: &mut Board, alpha_in: i16, beta: i16, depth: u8) -> i16 {
    if depth == 0 {
        return board.evaluate();
    }
    let mut alpha = alpha_in;
    let mut any_legal = false;

    for mv in board.generate_moves() {
        if !board.make_move(mv) {
            continue;
        }
        any_legal = true;
        let vl = -alpha_beta(board, -beta, -alpha, depth - 1);
        board.undo_make_move();

        if vl >= beta {
            return beta; // beta 截斷
        }
        if vl > alpha {
            alpha = vl;
        }
    }

    if !any_legal {
        // 無合法著法 = 被將死或困斃，判負；越早被將死分數越低（偏好速勝/緩敗）。
        return -MATE_VALUE + board.distance as i16;
    }
    alpha
}
