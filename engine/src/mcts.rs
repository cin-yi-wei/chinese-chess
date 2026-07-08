//! 蒙地卡羅樹搜尋（MCTS），對照 reference/cpp-console/mcts.cpp 的概念重寫。
//!
//! 原 C++ 版把 make/undo 與樹走訪耦合在一起、且 default_policy 只用單步評估差，
//! 邏輯脆弱又有已知 bug。這裡改寫成標準乾淨版：
//!   1. Selection：沿 UCB1 最佳子節點下探
//!   2. Expansion：展開一個尚未嘗試的合法著法
//!   3. Simulation：隨機對局 rollout 到深度上限，再以評估函式定勝負
//!   4. Backpropagation：沿路更新 visits/wins
//! 用 Board::clone() 複製盤面下探，避免手動 undo 的錯誤來源（引擎零外部相依，
//! 亂數用內建 xorshift）。

use crate::board::{Board, Move};

/// 探索常數 √2。
const UCB_C: f64 = std::f64::consts::SQRT_2;
/// 隨機對局的深度上限（步）。
const ROLLOUT_DEPTH: u32 = 40;
/// 預設模擬次數。
pub const DEFAULT_ITERATIONS: u32 = 4000;

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
    mv: Move,              // 抵達此節點的著法（根為 0）
    parent: Option<usize>, // 父節點索引
    children: Vec<usize>,
    untried: Vec<Move>, // 尚未展開的合法著法
    red_to_move: bool,  // 此節點輪到誰走
    visits: f64,
    wins: f64,
    terminal: bool, // 無合法著法（被將死）
}

/// 用 MCTS 從目前盤面選最佳著法；無合法著法回傳 None。
pub fn best_move_mcts(root_board: &Board, iterations: u32) -> Option<Move> {
    let root_moves = root_board.clone().legal_moves();
    if root_moves.is_empty() {
        return None;
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

        // 1) Selection：untried 空且有子節點時，沿 UCB1 下探
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

        // 2) Expansion：展開一個未嘗試著法
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

        // 3) Simulation：從 board 隨機對局，回傳以紅方視角的勝負（+1紅勝/-1黑勝/0和）
        let result_red = rollout(&mut board, &mut rng);

        // 4) Backpropagation
        let mut node_opt = Some(cur);
        while let Some(ni) = node_opt {
            let n = &mut nodes[ni];
            n.visits += 1.0;
            // 抵達此節點的著法由「n.red_to_move 的對方」所走
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

    // 選訪問次數最多的根子節點（robust child）
    nodes[0]
        .children
        .iter()
        .map(|&ci| &nodes[ci])
        .max_by(|a, b| a.visits.partial_cmp(&b.visits).unwrap())
        .map(|n| n.mv)
}

/// 隨機對局到深度上限，回傳以紅方視角的勝負。
fn rollout(board: &mut Board, rng: &mut Rng) -> i32 {
    for _ in 0..ROLLOUT_DEPTH {
        let moves = board.legal_moves();
        if moves.is_empty() {
            // 輪到走的一方被將死 → 對方勝
            return if board.red_to_move { -1 } else { 1 };
        }
        let mv = moves[rng.below(moves.len())];
        board.make_move(mv);
    }
    // 到達深度上限：以評估函式定優劣（evaluate 為走子方視角，轉成紅方視角）
    let s = board.evaluate();
    let red_score = if board.red_to_move { s } else { -s };
    red_score.signum() as i32
}
