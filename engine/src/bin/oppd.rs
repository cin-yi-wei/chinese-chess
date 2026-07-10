//! oppd — 「對手守護程序」：給 AlphaZero 訓練當固定強度的 alpha-beta 老師。
//!
//! 常駐讀 stdin、寫 stdout,每行一個請求,協定:
//!     <depth> <stm> <fen>
//!   depth: 搜尋層數(alpha-beta 難度)
//!   stm  : 走子方,"r"/"1"=紅、"b"/"0"=黑
//!   fen  : 佈局 FEN(與 engine START_FEN 同格式,不含走子方欄)
//! 回應一行:
//!     <fx> <fy> <tx> <ty>   最佳著法的起訖座標(x:0..8, y:0..9,y=0 為黑方底線)
//!     none                  無合法著法(已被將死/困斃)
//!
//! 只用 engine 函式庫,不改動引擎邏輯;純粹把既有 best_move 包成一個 I/O 介面。

use std::io::{self, BufRead, Write};

use engine::board::{dst, src, Board};
use engine::search::best_move;

fn main() {
    let stdin = io::stdin();
    let stdout = io::stdout();
    let mut out = stdout.lock();

    for line in stdin.lock().lines() {
        let line = match line {
            Ok(l) => l,
            Err(_) => break,
        };
        let line = line.trim();
        if line.is_empty() {
            continue;
        }
        if line == "quit" {
            break;
        }

        let mut it = line.splitn(3, ' ');
        let depth: u8 = it.next().and_then(|s| s.parse().ok()).unwrap_or(3);
        let stm = it.next().unwrap_or("r");
        let fen = it.next().unwrap_or("");

        let mut b = Board::new();
        b.load_fen(fen);
        b.red_to_move = stm == "r" || stm == "1";
        b.distance = 0;

        let resp = match best_move(&mut b, depth) {
            Some(mv) => {
                let (fx, fy) = Board::sq_to_coord(src(mv));
                let (tx, ty) = Board::sq_to_coord(dst(mv));
                format!("{} {} {} {}", fx, fy, tx, ty)
            }
            None => "none".to_string(),
        };
        if writeln!(out, "{}", resp).is_err() {
            break;
        }
        if out.flush().is_err() {
            break;
        }
    }
}
