//! axum 後端服務入口。
//!
//! 目前為骨架：起一個 HTTP 伺服器，提供健康檢查 `/health`。
//! WebSocket 對弈協定（/ws）與棋局管理於後續里程碑 ⑥ 加入。

use axum::{routing::get, Router};

#[tokio::main]
async fn main() {
    tracing_subscriber::fmt::init();

    let app = Router::new().route("/health", get(health));

    let addr = "127.0.0.1:3000";
    let listener = tokio::net::TcpListener::bind(addr)
        .await
        .expect("無法綁定位址");
    tracing::info!("象棋後端啟動於 http://{addr}");

    axum::serve(listener, app).await.expect("伺服器結束");
}

/// 健康檢查端點，確認服務存活。
async fn health() -> &'static str {
    "ok"
}
