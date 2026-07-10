//! Alpha-beta（negamax）搜尋 + 置換表(TT) + MVV-LVA 走子排序，移植/強化自 cpp-console。
//!
//! negamax 框架：evaluate() 以走子方視角回傳分值，遞迴對子節點取負。
//! 加速手段（不改變搜尋「結果值」，只加快）：
//!   - 置換表：以 zobrist 為鍵存 (depth,value,flag,best)，命中且深度足夠可直接回傳/剪枝。
//!   - 走子排序：先試 TT 最佳著法，再依 MVV-LVA（吃大子優先）排捕獲，增加 beta 截斷。
//! 正確性由測試 `tt_matches_plain_root_value` 保證（TT 版與純 negamax 的根節點值一致）。

use std::collections::HashMap;

use crate::board::{dst, src, Board, Move};

/// 將死分值（絕對值上限）。
pub const MATE_VALUE: i16 = 10000;
/// 高於此分值視為勝負已定。
pub const WIN_VALUE: i16 = MATE_VALUE - 200;

/// MVV-LVA 用的粗略子力值（僅供走子排序；index = 棋子種類 0..6：帥士象馬車炮兵）。
const ORD_VAL: [i32; 7] = [10000, 20, 20, 40, 90, 45, 10];

const F_EXACT: u8 = 0; // value 為精確值
const F_LOWER: u8 = 1; // value 為下界（發生 beta 截斷）
const F_UPPER: u8 = 2; // value 為上界（未超過 alpha）

#[derive(Clone, Copy)]
struct TtEntry {
    depth: u8,
    value: i16,
    flag: u8,
    best: Move,
}

/// 走子排序：TT 最佳著法最前，其次依 MVV-LVA 把吃大子的捕獲排前面。
fn order_moves(board: &Board, moves: &mut Vec<Move>, tt_best: Move) {
    moves.sort_by_key(|&mv| {
        if mv == tt_best {
            return i32::MIN; // 升冪排序 → 最前
        }
        let victim = board.squares[dst(mv) as usize];
        if victim != 0 {
            let vt = (victim & 7) as usize;
            let at = (board.squares[src(mv) as usize] & 7) as usize;
            -(100_000 + ORD_VAL[vt] * 16 - ORD_VAL[at]) // 捕獲：分數越高排越前（取負）
        } else {
            0 // 靜著
        }
    });
}

/// 從根局面搜尋指定深度，回傳最佳著法；無合法著法（被將死/困斃）回 None。
/// `depth` 即 AI 難度：越大越強、越慢。
pub fn best_move(board: &mut Board, depth: u8) -> Option<Move> {
    let mut tt: HashMap<u64, TtEntry> = HashMap::new();
    let mut best: Option<Move> = None;
    let mut best_val = i16::MIN;
    let mut alpha = -MATE_VALUE;
    let beta = MATE_VALUE;

    let mut moves = board.generate_moves();
    order_moves(board, &mut moves, 0);
    for mv in moves {
        if !board.make_move(mv) {
            continue; // 送死著法，跳過
        }
        let vl = -alpha_beta(board, -beta, -alpha, depth.saturating_sub(1), &mut tt);
        board.undo_make_move();
        if vl > best_val {
            best_val = vl;
            best = Some(mv);
        }
        if vl > alpha {
            alpha = vl;
        }
    }
    best
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

/// Negamax alpha-beta 遞迴（含 TT）。回傳以目前走子方視角的最佳分值。
fn alpha_beta(board: &mut Board, alpha_in: i16, beta: i16, depth: u8,
              tt: &mut HashMap<u64, TtEntry>) -> i16 {
    let key = board.zobrist;
    let mut tt_best: Move = 0;
    if let Some(e) = tt.get(&key).copied() {
        if e.depth >= depth {
            match e.flag {
                F_EXACT => return e.value,
                F_LOWER => {
                    if e.value >= beta {
                        return e.value;
                    }
                }
                F_UPPER => {
                    if e.value <= alpha_in {
                        return e.value;
                    }
                }
                _ => {}
            }
        }
        tt_best = e.best;
    }

    if depth == 0 {
        return board.evaluate();
    }

    let mut alpha = alpha_in;
    let mut any_legal = false;
    let mut best_val = -MATE_VALUE - 1;
    let mut best_mv: Move = 0;

    let mut moves = board.generate_moves();
    order_moves(board, &mut moves, tt_best);
    for mv in moves {
        if !board.make_move(mv) {
            continue;
        }
        any_legal = true;
        let vl = -alpha_beta(board, -beta, -alpha, depth - 1, tt);
        board.undo_make_move();

        if vl > best_val {
            best_val = vl;
            best_mv = mv;
        }
        if vl >= beta {
            tt.insert(key, TtEntry { depth, value: vl, flag: F_LOWER, best: mv });
            return beta; // beta 截斷（fail-hard）
        }
        if vl > alpha {
            alpha = vl;
        }
    }

    if !any_legal {
        // 無合法著法 = 被將死或困斃，判負；越早被將死分數越低（偏好速勝/緩敗）。
        return -MATE_VALUE + board.distance as i16;
    }

    let flag = if best_val <= alpha_in { F_UPPER } else { F_EXACT };
    tt.insert(key, TtEntry { depth, value: alpha, flag, best: best_mv });
    alpha
}

#[cfg(test)]
mod tests {
    use super::*;

    /// 純 negamax（無 TT、無排序）當正確性參照。
    fn plain(board: &mut Board, alpha_in: i16, beta: i16, depth: u8) -> i16 {
        if depth == 0 {
            return board.evaluate();
        }
        let mut alpha = alpha_in;
        let mut any = false;
        for mv in board.generate_moves() {
            if !board.make_move(mv) {
                continue;
            }
            any = true;
            let vl = -plain(board, -beta, -alpha, depth - 1);
            board.undo_make_move();
            if vl >= beta {
                return beta;
            }
            if vl > alpha {
                alpha = vl;
            }
        }
        if !any {
            return -MATE_VALUE + board.distance as i16;
        }
        alpha
    }

    /// TT 版根節點值（供比對）。
    fn tt_root(board: &mut Board, depth: u8) -> i16 {
        let mut tt: HashMap<u64, TtEntry> = HashMap::new();
        alpha_beta(board, -MATE_VALUE, MATE_VALUE, depth, &mut tt)
    }

    #[test]
    fn tt_matches_plain_root_value() {
        // 從開局走幾條不同路線，比對「TT 版」與「純 negamax」的根節點搜尋值是否一致。
        let mut b = Board::start();
        for depth in 1..=4u8 {
            let p = plain(&mut b, -MATE_VALUE, MATE_VALUE, depth);
            let t = tt_root(&mut b, depth);
            assert_eq!(p, t, "開局 depth={depth}：TT 值 {t} 應等於純 negamax {p}");
        }
        // 走幾步後再比對（不同局面）
        let seq = b.generate_moves();
        for &mv in seq.iter().take(4) {
            let mut bb = Board::start();
            if bb.make_move(mv) {
                for depth in 1..=4u8 {
                    let p = plain(&mut bb, -MATE_VALUE, MATE_VALUE, depth);
                    let t = tt_root(&mut bb, depth);
                    assert_eq!(p, t, "走一步後 depth={depth}：TT {t} 應等於 plain {p}");
                }
            }
        }
    }
}
