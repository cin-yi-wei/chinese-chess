//! Alpha-beta（negamax）搜尋 + 置換表(TT) + 走子排序(MVV-LVA/killer/history) + 靜態搜尋(quiescence)。
//!
//! negamax 框架：evaluate() 以走子方視角回傳分值，遞迴對子節點取負。
//! 加速手段：
//!   - 置換表 TT：以 zobrist 為鍵存 (depth,value,flag,best)，命中且深度足夠可直接回傳/剪枝。
//!   - 走子排序：TT 最佳著法 → MVV-LVA 捕獲 → killer moves → history 啟發式，最大化 beta 截斷。
//!   - 靜態搜尋 quiescence：depth 0 時只延伸「捕獲」直到平靜，消除吃子的水平線效應（horizon）。
//! 上述皆為「值保持」加速（quiescence 改變葉評估但更準確，TT/排序不改變結果）。
//! 正確性由測試 `tt_matches_plain_root_value` 保證：TT+排序版與純 negamax(同樣含 quiescence)根節點值一致。

use crate::board::{dst, src, Board, Move};

/// 將死分值（絕對值上限）。
pub const MATE_VALUE: i16 = 10000;
/// 高於此分值視為勝負已定。
pub const WIN_VALUE: i16 = MATE_VALUE - 200;

/// MVV-LVA 用的粗略子力值（僅供走子排序；index = 棋子種類 0..6：帥士象馬車炮兵）。
const ORD_VAL: [i32; 7] = [10000, 20, 20, 40, 90, 45, 10];

/// quiescence 最大延伸層數（防吃子鏈爆炸）。
const MAX_QDEPTH: u8 = 8;
/// killer/history 表的最大搜尋 ply。
const MAX_PLY: usize = 64;

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

/// 一次搜尋共用的可變狀態：置換表 + killer + history。
struct SearchState {
    tt: std::collections::HashMap<u64, TtEntry>,
    killers: [[Move; 2]; MAX_PLY],       // 每個 ply 兩個 killer（造成截斷的靜著）
    history: Vec<i32>,                    // [src*256 + dst] 靜著截斷累計，改善排序
}

impl SearchState {
    fn new() -> Self {
        SearchState {
            tt: std::collections::HashMap::new(),
            killers: [[0; 2]; MAX_PLY],
            history: vec![0; 256 * 256],
        }
    }

    fn record_cutoff(&mut self, board: &Board, mv: Move, ply: usize, depth: u8) {
        // 只有靜著（非捕獲）才進 killer/history；捕獲已由 MVV-LVA 處理。
        if board.squares[dst(mv) as usize] != 0 {
            return;
        }
        if ply < MAX_PLY {
            if self.killers[ply][0] != mv {
                self.killers[ply][1] = self.killers[ply][0];
                self.killers[ply][0] = mv;
            }
        }
        let idx = (src(mv) as usize) * 256 + dst(mv) as usize;
        self.history[idx] += (depth as i32) * (depth as i32);
    }
}

/// 走子排序：TT 最佳著法 → 捕獲(MVV-LVA) → killer → 其他靜著(history)。分數越高越前。
fn order_moves(board: &Board, moves: &mut Vec<Move>, tt_best: Move,
               killers: [Move; 2], history: &[i32]) {
    moves.sort_by_key(|&mv| {
        if mv == tt_best {
            return i32::MIN; // 最前
        }
        let victim = board.squares[dst(mv) as usize];
        if victim != 0 {
            let vt = (victim & 7) as usize;
            let at = (board.squares[src(mv) as usize] & 7) as usize;
            -(1_000_000 + ORD_VAL[vt] * 16 - ORD_VAL[at]) // 捕獲：高優先
        } else if mv == killers[0] {
            -900_000
        } else if mv == killers[1] {
            -800_000
        } else {
            let idx = (src(mv) as usize) * 256 + dst(mv) as usize;
            -history[idx] // history 越大越前
        }
    });
}

/// 只排捕獲用（quiescence）：MVV-LVA。
fn order_captures(board: &Board, moves: &mut Vec<Move>) {
    moves.sort_by_key(|&mv| {
        let victim = board.squares[dst(mv) as usize];
        let vt = (victim & 7) as usize;
        let at = (board.squares[src(mv) as usize] & 7) as usize;
        -(ORD_VAL[vt] * 16 - ORD_VAL[at])
    });
}

/// 從根局面搜尋指定深度，回傳最佳著法；無合法著法（被將死/困斃）回 None。
/// `depth` 即 AI 難度：越大越強、越慢。
pub fn best_move(board: &mut Board, depth: u8) -> Option<Move> {
    let mut st = SearchState::new();
    let mut best: Option<Move> = None;
    let mut best_val = i16::MIN;
    let mut alpha = -MATE_VALUE;
    let beta = MATE_VALUE;

    let mut moves = board.generate_moves();
    order_moves(board, &mut moves, 0, [0, 0], &st.history);
    for mv in moves {
        if !board.make_move(mv) {
            continue; // 送死著法，跳過
        }
        let vl = -alpha_beta(board, -beta, -alpha, depth.saturating_sub(1), 1, &mut st);
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

/// 靜態搜尋：只延伸捕獲直到「沒有吃子可下」，回傳穩定的葉評估（走子方視角）。
fn quiescence(board: &mut Board, alpha_in: i16, beta: i16, qdepth: u8) -> i16 {
    let stand = board.evaluate();
    if qdepth == 0 || stand >= beta {
        return if stand >= beta { beta } else { stand };
    }
    let mut alpha = alpha_in;
    if stand > alpha {
        alpha = stand;
    }
    // 只取捕獲著法
    let mut caps: Vec<Move> = board
        .generate_moves()
        .into_iter()
        .filter(|&mv| board.squares[dst(mv) as usize] != 0)
        .collect();
    order_captures(board, &mut caps);
    for mv in caps {
        if !board.make_move(mv) {
            continue;
        }
        let vl = -quiescence(board, -beta, -alpha, qdepth - 1);
        board.undo_make_move();
        if vl >= beta {
            return beta;
        }
        if vl > alpha {
            alpha = vl;
        }
    }
    alpha
}

/// Negamax alpha-beta 遞迴（含 TT / 排序 / quiescence）。回傳走子方視角最佳分值。
fn alpha_beta(board: &mut Board, alpha_in: i16, beta: i16, depth: u8, ply: usize,
              st: &mut SearchState) -> i16 {
    let key = board.zobrist;
    let mut tt_best: Move = 0;
    if let Some(e) = st.tt.get(&key).copied() {
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
        return quiescence(board, alpha_in, beta, MAX_QDEPTH);
    }

    let mut alpha = alpha_in;
    let mut any_legal = false;
    let mut best_val = -MATE_VALUE - 1;
    let mut best_mv: Move = 0;

    let killers = if ply < MAX_PLY { st.killers[ply] } else { [0, 0] };
    let mut moves = board.generate_moves();
    order_moves(board, &mut moves, tt_best, killers, &st.history);
    for mv in moves {
        if !board.make_move(mv) {
            continue;
        }
        any_legal = true;
        let vl = -alpha_beta(board, -beta, -alpha, depth - 1, ply + 1, st);
        board.undo_make_move();

        if vl > best_val {
            best_val = vl;
            best_mv = mv;
        }
        if vl >= beta {
            st.record_cutoff(board, mv, ply, depth);
            st.tt.insert(key, TtEntry { depth, value: vl, flag: F_LOWER, best: mv });
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
    st.tt.insert(key, TtEntry { depth, value: alpha, flag, best: best_mv });
    alpha
}

#[cfg(test)]
mod tests {
    use super::*;

    /// 純 negamax（無 TT、無排序，但同樣含 quiescence）當正確性參照。
    fn plain(board: &mut Board, alpha_in: i16, beta: i16, depth: u8) -> i16 {
        if depth == 0 {
            return quiescence(board, alpha_in, beta, MAX_QDEPTH);
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

    /// TT+排序版根節點值（供比對）。
    fn tt_root(board: &mut Board, depth: u8) -> i16 {
        let mut st = SearchState::new();
        alpha_beta(board, -MATE_VALUE, MATE_VALUE, depth, 0, &mut st)
    }

    #[test]
    fn tt_matches_plain_root_value() {
        // 從開局走幾條不同路線，比對「TT+排序+quiescence 版」與「純 negamax(同 quiescence)」根節點值一致。
        let mut b = Board::start();
        for depth in 1..=4u8 {
            let p = plain(&mut b, -MATE_VALUE, MATE_VALUE, depth);
            let t = tt_root(&mut b, depth);
            assert_eq!(p, t, "開局 depth={depth}：TT 值 {t} 應等於純 negamax {p}");
        }
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
