//! Alpha-beta（negamax）搜尋，移植自 reference/cpp-console/search.cpp。
//!
//! 用 negamax 框架：evaluate() 已以走子方視角回傳分值，故遞迴時對子節點
//! 取負即可。原 C++ 版夾雜若干除錯用的過濾條件（SRC/DST<140、repStatus2），
//! 那些非標準搜尋邏輯此處略去，改寫成乾淨的 alpha-beta。
//! 加吃子優先排序加速 beta 截斷，讓較深的搜尋可行。

use crate::board::{Board, Move};

/// 將死分值（絕對值上限）。
pub const MATE_VALUE: i16 = 10000;
/// 高於此分值視為勝負已定。
pub const WIN_VALUE: i16 = MATE_VALUE - 200;

/// xorshift64 亂數（供分級難度的隨機失誤用）。
struct Rng(u64);
impl Rng {
    fn next_u64(&mut self) -> u64 {
        let mut x = self.0;
        x ^= x << 13;
        x ^= x >> 7;
        x ^= x << 17;
        self.0 = x;
        x
    }
    fn below(&mut self, n: usize) -> usize {
        (self.next_u64() % n as u64) as usize
    }
    fn unit(&mut self) -> f64 {
        (self.next_u64() >> 11) as f64 / (1u64 << 53) as f64
    }
}

fn seed_from(board: &Board) -> u64 {
    let mut s: u64 = 0x2545_f491_4f6c_dd1d;
    for (i, &pc) in board.squares.iter().enumerate() {
        if pc != 0 {
            s = s.wrapping_mul(1099511628211).wrapping_add((i as u64 + 1) * pc as u64);
        }
    }
    s | 1
}

/// 吃子優先排序：終點有子的著法排前面（helps alpha-beta 剪枝）。
fn ordered_moves(board: &Board) -> Vec<Move> {
    let mut mvs = board.generate_moves();
    mvs.sort_by_key(|&m| if board.squares[(m >> 8) as usize] != 0 { 0 } else { 1 });
    mvs
}

/// 從根局面搜尋指定深度，回傳最佳著法；若無合法著法（已被將死/困斃）回傳 None。
///
/// `depth` 即搜尋深度：越大越強、越慢。
pub fn best_move(board: &mut Board, depth: u8) -> Option<Move> {
    let mut best: Option<Move> = None;
    let mut alpha = -MATE_VALUE;
    let beta = MATE_VALUE;

    for mv in ordered_moves(board) {
        if !board.make_move(mv) {
            continue; // 送死著法，跳過
        }
        let vl = -alpha_beta(board, -beta, -alpha, depth.saturating_sub(1));
        board.undo_make_move();
        if best.is_none() || vl > alpha {
            alpha = vl;
            best = Some(mv);
        }
    }
    best
}

/// 分級難度（1~100）：以 alpha-beta 為底，高分深搜且不失誤、低分淺搜且常隨機失誤。
///
/// 比純 MCTS 可靠——高難度是真正會算的 alpha-beta，不會亂走；
/// 低難度靠淺搜 + 隨機失誤率平滑弱化。
pub fn best_move_leveled(board: &mut Board, level: u8) -> Option<Move> {
    let level = level.clamp(1, 100);
    let depth: u8 = match level {
        85..=100 => 5,
        65..=84 => 4,
        45..=64 => 3,
        25..=44 => 2,
        _ => 1,
    };
    // 失誤率：level 越低越常亂走（最高約 60%）。
    let blunder = (100 - level) as f64 / 100.0 * 0.6;

    let legal = board.legal_moves();
    if legal.is_empty() {
        return None;
    }
    let mut rng = Rng(seed_from(board));
    if rng.unit() < blunder {
        return Some(legal[rng.below(legal.len())]);
    }
    best_move(board, depth)
}

/// 迭代加深：從深度 1 逐層加深到 `max_depth`，取最後完成的最佳著法。
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

    for mv in ordered_moves(board) {
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
