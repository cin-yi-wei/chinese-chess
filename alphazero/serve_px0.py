"""px0 + 自製 MCTS 的網頁對弈 GUI（自足版，桌面殼 app_px0 也用這個）。

- 純 Python 標準庫 HTTP 伺服器（無 aiohttp / 無 torch / 無 npm）。
- 內嵌單檔象棋盤 HTML（點選走子）。人執紅（下方），AI 執黑，用 Px0Evaluator + puct_search_batched。
- 伺服器維持一局 Board 狀態（含 move_stack）→ 餵給網路的 8 步歷史才正確。
- UI：點完自己的子「立刻」移動並顯示「AI 思考中」，不必等 AI 算完（樂觀更新）。
- 難度：easy/medium/hard/max → sims 40/96/160/400（DirectML 下約 0.3/0.6/1.0/2.9 秒/步）。

用法（alphazero/ 下，需 onnxruntime + 已轉好的 .onnx）：
    PX0_ONNX=../px0/nets/net_33mb.onnx python serve_px0.py
    然後瀏覽器開 http://127.0.0.1:3941
環境變數：PX0_ONNX（.onnx）、CHESS_BATCH（預設8，鐵律）、CHESS_DIFFICULTY（預設medium）、CHESS_PORT（3941）
"""

from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from xiangqi.board import (Board, coord_to_sq, sq_to_coord,
                           move_src, move_dst, make_move_code)
from mcts import puct_search_batched
from px0_eval import Px0Evaluator

ONNX = os.environ.get("PX0_ONNX", r"../px0/nets/net_33mb.onnx")
BATCH = int(os.environ.get("CHESS_BATCH", "8"))
PORT = int(os.environ.get("CHESS_PORT", "3941"))

PRESET_SIMS = {"easy": 40, "medium": 96, "hard": 160, "max": 400}
DEFAULT_DIFF = os.environ.get("CHESS_DIFFICULTY", "medium")

_evaluator = Px0Evaluator(ONNX)
_board = Board.start()
_sims = PRESET_SIMS.get(DEFAULT_DIFF, 96)
_lock = threading.Lock()   # 單局、序列化存取


def _state(ai_move=None):
    legal = _board.legal_moves()
    over = None
    if not legal:
        over = "black" if _board.red_to_move else "red"
    return {
        "fen": _board.to_fen(),
        "redToMove": _board.red_to_move,
        "inCheck": _board.checked(),
        "legal": [[*sq_to_coord(move_src(m)), *sq_to_coord(move_dst(m))] for m in legal],
        "aiMove": ai_move,
        "gameOver": over,
    }


def _handle(cmd: dict) -> dict:
    global _board, _sims
    t = cmd.get("type")
    if t == "new_game":
        _board = Board.start()
        d = cmd.get("difficulty")
        if d in PRESET_SIMS:
            _sims = PRESET_SIMS[d]
        return _state()
    if t == "move":
        fr, to = cmd["from"], cmd["to"]
        mv = make_move_code(coord_to_sq(fr[0], fr[1]), coord_to_sq(to[0], to[1]))
        if mv not in _board.legal_moves():
            return {"illegal": True}
        _board.make_move(mv)                      # 人（紅）走
        if not _board.legal_moves():              # 人走完 AI 已無著（人勝）
            return _state()
        ai_mv = puct_search_batched(_board, _evaluator, _sims, BATCH)
        _board.make_move(ai_mv)                   # AI（黑）回手
        ax, ay = sq_to_coord(move_src(ai_mv))
        bx, by = sq_to_coord(move_dst(ai_mv))
        return _state([ax, ay, bx, by])
    return {"error": "unknown"}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"ok")
            return
        if self.path in ("/", "/index.html"):
            body = INDEX_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path != "/api":
            self.send_error(404)
            return
        n = int(self.headers.get("Content-Length", 0))
        cmd = json.loads(self.rfile.read(n) or b"{}")
        with _lock:
            resp = _handle(cmd)
        body = json.dumps(resp).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


INDEX_HTML = r"""<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>px0 象棋 · 你執紅</title>
<style>
  body{margin:0;background:#2b2b2b;color:#eee;font-family:system-ui,"Microsoft JhengHei",sans-serif;
       display:flex;flex-direction:column;align-items:center;gap:10px;padding:14px}
  h1{font-size:17px;margin:2px;font-weight:600}
  #status{font-size:14px;min-height:20px;color:#bbb}
  svg{background:#e9c88a;border-radius:6px;box-shadow:0 4px 18px rgba(0,0,0,.4);touch-action:manipulation}
  .pc{cursor:pointer}
  .row{display:flex;gap:10px;align-items:center}
  button,select{background:#3a6ea5;color:#fff;border:0;border-radius:6px;padding:7px 14px;font-size:14px;cursor:pointer}
  button:hover{background:#4d84c0}
  select{background:#444}
  .muted{color:#888;font-size:12px}
</style></head><body>
<h1>px0 象棋 · <span style="color:#e05a4a">你執紅（下方）</span> vs AI 黑</h1>
<div id="status">載入中…</div>
<svg id="board" width="450" height="500" viewBox="0 0 450 500"></svg>
<div class="row">
  難度 <select id="diff">
    <option value="easy">簡單(快)</option>
    <option value="medium" selected>普通</option>
    <option value="hard">困難</option>
    <option value="max">最強(較慢)</option>
  </select>
  <button onclick="newGame()">新局</button>
</div>
<div class="muted">點自己的子 → 點目標格。難度改變後按「新局」生效。</div>
<script>
const M=25, GX=50, GY=50;
const X=i=>GX+i*M, Y=j=>GY+j*M;
const CN={R:"俥",N:"傌",B:"相",A:"仕",K:"帥",C:"炮",P:"兵",
          r:"車",n:"馬",b:"象",a:"士",k:"將",c:"砲",p:"卒"};
let state=null, sel=null, aiMove=null, optim=null, thinking=false;

function parseFEN(fen){
  const g=[]; const rows=fen.split(" ")[0].split("/");
  for(let j=0;j<10;j++){ const row=rows[j]||""; const line=[];
    for(const ch of row){ if(ch>="1"&&ch<="9"){for(let k=0;k<+ch;k++)line.push(null);} else line.push(ch);}
    while(line.length<9)line.push(null); g.push(line);}
  return g;
}
function curGrid(){ return optim ? optim : parseFEN(state.fen); }
function draw(){
  const svg=document.getElementById("board"); let s="";
  for(let j=0;j<10;j++) s+=`<line x1="${X(0)}" y1="${Y(j)}" x2="${X(8)}" y2="${Y(j)}" stroke="#7a5a28"/>`;
  for(let i=0;i<9;i++){
    if(i===0||i===8){ s+=`<line x1="${X(i)}" y1="${Y(0)}" x2="${X(i)}" y2="${Y(9)}" stroke="#7a5a28"/>`;}
    else{ s+=`<line x1="${X(i)}" y1="${Y(0)}" x2="${X(i)}" y2="${Y(4)}" stroke="#7a5a28"/>`;
          s+=`<line x1="${X(i)}" y1="${Y(5)}" x2="${X(i)}" y2="${Y(9)}" stroke="#7a5a28"/>`;}
  }
  s+=`<line x1="${X(3)}" y1="${Y(0)}" x2="${X(5)}" y2="${Y(2)}" stroke="#7a5a28"/><line x1="${X(5)}" y1="${Y(0)}" x2="${X(3)}" y2="${Y(2)}" stroke="#7a5a28"/>`;
  s+=`<line x1="${X(3)}" y1="${Y(7)}" x2="${X(5)}" y2="${Y(9)}" stroke="#7a5a28"/><line x1="${X(5)}" y1="${Y(7)}" x2="${X(3)}" y2="${Y(9)}" stroke="#7a5a28"/>`;
  s+=`<text x="${X(2)}" y="${Y(4.6)}" fill="#7a5a28" font-size="16">楚河</text><text x="${X(5)}" y="${Y(4.6)}" fill="#7a5a28" font-size="16">漢界</text>`;
  if(aiMove && !optim){ const[fx,fy,tx,ty]=aiMove;
    s+=`<circle cx="${X(fx)}" cy="${Y(fy)}" r="14" fill="none" stroke="#4d84c0" stroke-width="2"/>`;
    s+=`<circle cx="${X(tx)}" cy="${Y(ty)}" r="14" fill="none" stroke="#4d84c0" stroke-width="2"/>`;}
  if(sel){ s+=`<circle cx="${X(sel[0])}" cy="${Y(sel[1])}" r="15" fill="none" stroke="#e0c000" stroke-width="3"/>`;
    for(const [fx,fy,tx,ty] of state.legal){ if(fx===sel[0]&&fy===sel[1])
      s+=`<circle cx="${X(tx)}" cy="${Y(ty)}" r="5" fill="#2a8f3a"/>`;}}
  const g=curGrid();
  for(let j=0;j<10;j++)for(let i=0;i<9;i++){ const p=g[j][i]; if(!p)continue;
    const red=p===p.toUpperCase(); const fill=red?"#c0392b":"#111";
    s+=`<g class="pc" data-x="${i}" data-y="${j}">
      <circle cx="${X(i)}" cy="${Y(j)}" r="13" fill="#f3e2b8" stroke="${fill}" stroke-width="1.5"/>
      <text x="${X(i)}" y="${Y(j)+6}" text-anchor="middle" font-size="17" fill="${fill}">${CN[p]}</text></g>`;
  }
  svg.innerHTML=s;
  svg.querySelectorAll(".pc").forEach(e=>e.onclick=()=>click(+e.dataset.x,+e.dataset.y));
  svg.onclick=(ev)=>{ if(ev.target===svg||ev.target.tagName==="line") boardClick(ev); };
}
function nearest(ev){ const r=document.getElementById("board").getBoundingClientRect();
  const px=(ev.clientX-r.left)*450/r.width, py=(ev.clientY-r.top)*500/r.height;
  const i=Math.round((px-GX)/M), j=Math.round((py-GY)/M);
  return (i>=0&&i<9&&j>=0&&j<10)?[i,j]:null; }
function boardClick(ev){ const c=nearest(ev); if(c)click(c[0],c[1]); }
function click(i,j){
  if(!state||state.gameOver||!state.redToMove||thinking)return;
  if(sel){ const ok=state.legal.some(m=>m[0]===sel[0]&&m[1]===sel[1]&&m[2]===i&&m[3]===j);
    if(ok){ const from=sel; sel=null; move(from,[i,j]); return;} }
  const g=parseFEN(state.fen); const p=g[j][i];
  if(p&&p===p.toUpperCase()){ sel=[i,j]; draw(); } else { sel=null; draw(); }
}
function setStatus(){ const s=document.getElementById("status");
  if(!state){s.textContent="";return;}
  if(thinking){ s.textContent="AI 思考中…"; return; }
  if(state.gameOver){ s.textContent = state.gameOver==="red"?"🎉 你贏了！":(state.gameOver==="black"?"AI 贏了":"和局"); return;}
  s.textContent = state.redToMove ? (state.inCheck?"你被將軍！輪你走":"輪你走（紅）") : "AI…";
}
async function api(cmd){ const r=await fetch("/api",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(cmd)}); return r.json(); }
async function newGame(){ sel=null; aiMove=null; optim=null; thinking=false;
  state=await api({type:"new_game", difficulty:document.getElementById("diff").value}); draw(); setStatus(); }
async function move(from,to){
  // 樂觀更新：先在畫面上立刻移動你的棋子，再送給伺服器算 AI。
  const g=parseFEN(state.fen);
  g[to[1]][to[0]]=g[from[1]][from[0]]; g[from[1]][from[0]]=null;
  optim=g; aiMove=null; thinking=true; sel=null; draw(); setStatus();
  const r=await api({type:"move",from,to});
  thinking=false;
  if(r.illegal){ optim=null; draw(); setStatus(); return; }
  optim=null; state=r; aiMove=r.aiMove; draw(); setStatus();
}
newGame();
</script>
</body></html>"""


def main():
    print(f"px0 象棋 GUI → http://127.0.0.1:{PORT}  net={ONNX} batch={BATCH} "
          f"難度={DEFAULT_DIFF}({_sims} sims) providers={_evaluator.session.get_providers()[:2]}")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
