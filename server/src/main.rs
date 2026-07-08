//! axum 後端服務：對弈用 WebSocket + 靜態前端。
//!
//! 對弈模型（里程碑 ⑥）：人執紅（下方）、AI 執黑（上方），一條 WS 連線一局。
//! 協定（JSON 文字幀）：
//!   client→server:
//!     {"type":"new_game"}
//!     {"type":"move","from":[x,y],"to":[x,y]}   // x:0..8 檔、y:0..9 列
//!   server→client:
//!     {"type":"state", fen, redToMove, inCheck, legal:[[fx,fy,tx,ty]...],
//!                      aiMove:[fx,fy,tx,ty]|null, gameOver:"red"|"black"|null}
//!     {"type":"illegal"}

use axum::{
    extract::ws::{Message, WebSocket, WebSocketUpgrade},
    response::IntoResponse,
    routing::get,
    Router,
};
use engine::{best_move, Board, Move};
use serde::{Deserialize, Serialize};
use tower_http::services::{ServeDir, ServeFile};

/// AI 搜尋深度（難度）。之後可由 new_game 參數帶入。
const AI_DEPTH: u8 = 4;

#[tokio::main]
async fn main() {
    tracing_subscriber::fmt::init();

    // 靜態前端：優先服務 frontend/dist（打包後），fallback index.html。
    let frontend = ServeDir::new("frontend/dist")
        .not_found_service(ServeFile::new("frontend/dist/index.html"));

    let app = Router::new()
        .route("/health", get(|| async { "ok" }))
        .route("/ws", get(ws_handler))
        .fallback_service(frontend);

    let addr = "127.0.0.1:3000";
    let listener = tokio::net::TcpListener::bind(addr)
        .await
        .expect("無法綁定位址");
    tracing::info!("象棋後端啟動於 http://{addr}");
    axum::serve(listener, app).await.expect("伺服器結束");
}

async fn ws_handler(ws: WebSocketUpgrade) -> impl IntoResponse {
    ws.on_upgrade(handle_socket)
}

// ---- 協定型別 ----

#[derive(Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
enum ClientMsg {
    NewGame,
    Move { from: [u8; 2], to: [u8; 2] },
}

#[derive(Serialize)]
#[serde(tag = "type", rename_all = "snake_case")]
enum ServerMsg {
    State {
        fen: String,
        #[serde(rename = "redToMove")]
        red_to_move: bool,
        #[serde(rename = "inCheck")]
        in_check: bool,
        legal: Vec<[u8; 4]>,
        #[serde(rename = "aiMove")]
        ai_move: Option<[u8; 4]>,
        #[serde(rename = "gameOver")]
        game_over: Option<String>,
    },
    Illegal,
}

/// 每條連線各自持有一局盤面。
async fn handle_socket(mut socket: WebSocket) {
    let mut board = Board::start();

    while let Some(Ok(msg)) = socket.recv().await {
        let Message::Text(text) = msg else {
            continue;
        };
        let Ok(cmd) = serde_json::from_str::<ClientMsg>(&text) else {
            continue;
        };

        let reply = match cmd {
            ClientMsg::NewGame => {
                board = Board::start();
                state_msg(&mut board, None)
            }
            ClientMsg::Move { from, to } => {
                match apply_human_then_ai(&mut board, from, to) {
                    Some(ai) => state_msg(&mut board, ai),
                    None => ServerMsg::Illegal,
                }
            }
        };

        let json = serde_json::to_string(&reply).unwrap();
        if socket.send(Message::Text(json)).await.is_err() {
            break;
        }
    }
}

/// 套用人類著法；若合法且遊戲續行則讓 AI 回一手。
/// 回傳 Some(ai_move option)；著法非法回傳 None。
fn apply_human_then_ai(board: &mut Board, from: [u8; 2], to: [u8; 2]) -> Option<Option<[u8; 4]>> {
    let mv = engine::Board::coord_to_sq(from[0], from[1]) as Move
        | ((engine::Board::coord_to_sq(to[0], to[1]) as Move) << 8);

    // 僅接受合法著法
    if !board.legal_moves().contains(&mv) {
        return None;
    }
    board.make_move(mv);

    // 人走完就結束（AI 被將死）→ 無 AI 著法
    if board.legal_moves().is_empty() {
        return Some(None);
    }

    // AI 回手
    let ai_mv = best_move(board, AI_DEPTH)?;
    board.make_move(ai_mv);
    Some(Some(move_to_coords(ai_mv)))
}

/// 組 state 訊息（含合法著法清單、將軍、勝負）。
fn state_msg(board: &mut Board, ai_move: Option<[u8; 4]>) -> ServerMsg {
    let legal_mvs = board.legal_moves();
    let legal: Vec<[u8; 4]> = legal_mvs.iter().map(|&m| move_to_coords(m)).collect();
    let in_check = board.checked();
    let game_over = if legal_mvs.is_empty() {
        // 目前走子方無著法 = 被將死，對方勝
        Some(if board.red_to_move { "black" } else { "red" }.to_string())
    } else {
        None
    };
    ServerMsg::State {
        fen: board.to_fen(),
        red_to_move: board.red_to_move,
        in_check,
        legal,
        ai_move,
        game_over,
    }
}

/// 著法碼轉 [fx,fy,tx,ty] 前端座標。
fn move_to_coords(mv: Move) -> [u8; 4] {
    let (fx, fy) = Board::sq_to_coord((mv & 0xff) as u8);
    let (tx, ty) = Board::sq_to_coord((mv >> 8) as u8);
    [fx, fy, tx, ty]
}
