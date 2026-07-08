//! 蒙地卡羅樹搜尋（MCTS），對照 reference/cpp-console/mcts.cpp 的概念重寫。
//!
//! 標準乾淨版：Selection(UCB1) → Expansion → Simulation(隨機 rollout) → Backprop，
//! 以 Board::clone() 下探避免手動 undo 的錯誤來源，亂數用內建 xorshift。
//!
//! 另實作「線性棋力系統」選步（參考交大吳毅成團隊 2019 論文
//! Strength Adjustment and Assessment for MCTS-Based Programs）：
//! 跑完 MCTS 後，對 root 各著法的模擬次數 N_i，用 strength index z 做
//! softmax 抽樣 π_i ∝ N_i^z，並以門檻比 R_th 濾掉 N_i < N_1·R_th 的爛步。
//! z 越大越強（z→∞ 等於選 N 最大）、z=0 隨機、z<0 變弱；z 與 Elo 近乎線性。

use crate::board::{Board, Move};

/// 探索常數 √2。
const UCB_C: f64 = std::f64::consts::SQRT_2;
/// 隨機對局的深度上限（步）。
const ROLLOUT_DEPTH: u32 = 40;
/// 預設模擬次數。
pub const DEFAULT_ITERATIONS: u32 = 4000;
/// 棋力調整的門檻比：只考慮 N_i ≥ N_1·R_th 的著法，保證強度下限。
pub const THRESHOLD_RATIO: f64 = 0.1;

/// xorshift64 亂數（引擎不引入 rand crate，保持可編 WASM）。
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
    /// [0,1) 均勻浮點。
    fn unit(&mut self) -> f64 {
        (self.next_u64() >> 11) as f64 / (1u64 << 53) as f64
    }
}

/// 以盤面內容導出非零種子，讓不同局面的 rollout 走向不同。
fn seed_from(board: &Board) -> u64 {
    let mut s: u64 = 0x9e3779b97f4a7c15;
    for (i, &pc) in board.squares.iter().enumerate() {
        if pc != 0 {
            s = s.wrapping_mul(1099511628211).wrapping_add((i as u64 + 1) * pc as u64);
        }
    }
    s | 1
}

struct Node {
    mv: Move,
    parent: Option<usize>,
    children: Vec<usize>,
    untried: Vec<Move>,
    red_to_move: bool,
    visits: f64,
    wins: f64,
    terminal: bool,
}

/// 跑完整棵 MCTS，回傳 root 各子著法的 (著法, 模擬次數)。
fn run_mcts(root_board: &Board, iterations: u32) -> Vec<(Move, f64)> {
    let root_moves = root_board.clone().legal_moves();
    if root_moves.is_empty() {
        return Vec::new();
    }

    let mut nodes: Vec<Node> = Vec::new();
    nodes.push(Node {
        mv: 0,
        parent: None,
        children: Vec::new(),
        untried: root_moves,
        red_to_move: root_board.red_to_move,
        visits: 0.0,
        wins: 0.0,
        terminal: false,
    });

    let mut rng = Rng(seed_from(root_board));

    for _ in 0..iterations {
        let mut board = root_board.clone();
        let mut cur = 0usize;

        // 1) Selection
        loop {
            if nodes[cur].terminal || !nodes[cur].untried.is_empty() || nodes[cur].children.is_empty()
            {
                break;
            }
            let parent_visits = nodes[cur].visits;
            let mut best_ci = nodes[cur].children[0];
            let mut best_ucb = f64::MIN;
            for &ci in &nodes[cur].children {
                let ch = &nodes[ci];
                let ucb = ch.wins / ch.visits + UCB_C * (parent_visits.ln() / ch.visits).sqrt();
                if ucb > best_ucb {
                    best_ucb = ucb;
                    best_ci = ci;
                }
            }
            board.make_move(nodes[best_ci].mv);
            cur = best_ci;
        }

        // 2) Expansion
        if !nodes[cur].terminal && !nodes[cur].untried.is_empty() {
            let idx = rng.below(nodes[cur].untried.len());
            let mv = nodes[cur].untried.swap_remove(idx);
            board.make_move(mv);
            let child_moves = board.legal_moves();
            let terminal = child_moves.is_empty();
            let child = Node {
                mv,
                parent: Some(cur),
                children: Vec::new(),
                untried: child_moves,
                red_to_move: board.red_to_move,
                visits: 0.0,
                wins: 0.0,
                terminal,
            };
            nodes.push(child);
            let ci = nodes.len() - 1;
            nodes[cur].children.push(ci);
            cur = ci;
        }

        // 3) Simulation
        let result_red = rollout(&mut board, &mut rng);

        // 4) Backpropagation
        let mut node_opt = Some(cur);
        while let Some(ni) = node_opt {
            let n = &mut nodes[ni];
            n.visits += 1.0;
            let mover_is_red = !n.red_to_move;
            n.wins += if result_red == 0 {
                0.5
            } else if (result_red > 0) == mover_is_red {
                1.0
            } else {
                0.0
            };
            node_opt = n.parent;
        }
    }

    nodes[0]
        .children
        .iter()
        .map(|&ci| (nodes[ci].mv, nodes[ci].visits))
        .collect()
}

/// 用 MCTS 選最佳著法（訪問數最多，robust child）；無合法著法回傳 None。
pub fn best_move_mcts(root_board: &Board, iterations: u32) -> Option<Move> {
    run_mcts(root_board, iterations)
        .into_iter()
        .max_by(|a, b| a.1.partial_cmp(&b.1).unwrap())
        .map(|(mv, _)| mv)
}

/// 「線性棋力系統」選步：以 strength index `z` 調整棋力。
///
/// 跑完 MCTS 後，對 root 各著法模擬次數 N_i：先濾掉 N_i < N_1·R_th 的爛步，
/// 再以 π_i ∝ N_i^z 做加權抽樣。z 越大越強（→∞ 即選最大），z=0 隨機，z<0 變弱。
/// 無合法著法回傳 None。
pub fn best_move_mcts_strength(root_board: &Board, iterations: u32, z: f64) -> Option<Move> {
    let children = run_mcts(root_board, iterations);
    if children.is_empty() {
        return None;
    }
    let n_max = children.iter().map(|&(_, n)| n).fold(0.0f64, f64::max);
    if n_max <= 0.0 {
        return children.first().map(|&(mv, _)| mv);
    }
    // 門檻過濾：只留 N_i ≥ N_1·R_th
    let floor = n_max * THRESHOLD_RATIO;
    let candidates: Vec<(Move, f64)> = children
        .iter()
        .filter(|&&(_, n)| n >= floor && n > 0.0)
        .copied()
        .collect();
    let pool = if candidates.is_empty() { children } else { candidates };

    // 權重 w_i = N_i^z（z 很大時等於挑最大，直接回傳避免溢位）
    if z >= 50.0 {
        return pool
            .into_iter()
            .max_by(|a, b| a.1.partial_cmp(&b.1).unwrap())
            .map(|(mv, _)| mv);
    }
    let weights: Vec<f64> = pool.iter().map(|&(_, n)| n.powf(z)).collect();
    let total: f64 = weights.iter().sum();
    if !(total > 0.0) {
        // 數值異常時退回訪問數最多
        return pool
            .into_iter()
            .max_by(|a, b| a.1.partial_cmp(&b.1).unwrap())
            .map(|(mv, _)| mv);
    }

    let mut rng = Rng(seed_from(root_board) ^ 0xabcd_1234_5678_9f01);
    let mut pick = rng.unit() * total;
    for (i, &w) in weights.iter().enumerate() {
        pick -= w;
        if pick <= 0.0 {
            return Some(pool[i].0);
        }
    }
    pool.last().map(|&(mv, _)| mv)
}

/// 模擬對局中選吃子步的機率（其餘走隨機合法步）。
const CAPTURE_BIAS: f64 = 0.8;

/// 對局模擬到深度上限，回傳以紅方視角的勝負。
///
/// 用「吃子導向」rollout 取代純隨機：象棋是吃子驅動的，模擬時大機率優先
/// 走吃子步，統計比亂走準得多，整體棋力明顯提升（方案 1）。
fn rollout(board: &mut Board, rng: &mut Rng) -> i32 {
    for _ in 0..ROLLOUT_DEPTH {
        let moves = board.legal_moves();
        if moves.is_empty() {
            return if board.red_to_move { -1 } else { 1 };
        }
        let mv = pick_rollout_move(board, &moves, rng);
        board.make_move(mv);
        // 提早結束：一方子力大幅領先就不必走到底
        let s = board.evaluate();
        let red_score = if board.red_to_move { s } else { -s };
        if red_score.abs() > 800 {
            return red_score.signum() as i32;
        }
    }
    let s = board.evaluate();
    let red_score = if board.red_to_move { s } else { -s };
    red_score.signum() as i32
}

/// 吃子導向選步：有吃子步時以 CAPTURE_BIAS 機率從吃子步中挑，否則隨機。
fn pick_rollout_move(board: &Board, moves: &[Move], rng: &mut Rng) -> Move {
    // 終點格有子 = 吃子步
    let captures: Vec<Move> = moves
        .iter()
        .copied()
        .filter(|&m| board.squares[(m >> 8) as usize] != 0)
        .collect();
    if !captures.is_empty() && rng.unit() < CAPTURE_BIAS {
        captures[rng.below(captures.len())]
    } else {
        moves[rng.below(moves.len())]
    }
}
