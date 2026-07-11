// 中國象棋前端：Phaser 畫棋盤 + WebSocket 與 Rust 後端對弈。
// 人執紅（下方），AI 執黑（上方）。座標 x:0..8 檔、y:0..9 列，左上為原點。
import Phaser from 'phaser';

const COLS = 9;
const ROWS = 10;
const CELL = 64;
const MARGIN = 46;
const W = MARGIN * 2 + CELL * (COLS - 1);
const H = MARGIN * 2 + CELL * (ROWS - 1);
const R = 27; // 棋子半徑

const RED_CHARS = { K: '帥', A: '仕', B: '相', N: '傌', R: '俥', C: '炮', P: '兵' };
const BLACK_CHARS = { k: '將', a: '士', b: '象', n: '馬', r: '車', c: '砲', p: '卒' };

const px = (x) => MARGIN + x * CELL;
const py = (y) => MARGIN + y * CELL;
const keyOf = (x, y) => `${x},${y}`;

class BoardScene extends Phaser.Scene {
  constructor() {
    super('board');
    this.grid = [];
    this.redToMove = true;
    this.gameOver = null;
    this.legal = [];
    this.selected = null;
    this.sprites = new Map(); // "x,y" -> 棋子容器
    this.busy = false; // 動畫/等待 AI 期間鎖住輸入
    this.history = []; // 每個權威盤面快照 {fen,redToMove,legal,gameOver,inCheck}
    this.viewPtr = -1; // 目前顯示的是 history 第幾筆（<最後一筆＝回顧模式）
    this.intent = 'new_game'; // 上一個送出的請求類型，決定回覆怎麼併入 history
    this.lastHuman = null; // 你最近一步 [fx,fy,tx,ty]
    this.lastAi = null; // AI 最近一步 [fx,fy,tx,ty]
    this.moves = []; // 整局每一 ply [fx,fy,tx,ty]（含人與 AI），用於斷線重連重建
    this._saved = null; // 重連時暫存 localStorage 讀到的存檔
    this.STORE = 'chess-az-game'; // localStorage key
  }

  // ---- 斷線重連存檔（手機切走 WS 會斷，回來重建整局） ----
  saveGame() {
    try {
      localStorage.setItem(this.STORE, JSON.stringify({
        moves: this.moves,
        hist: this.history,
        lh: this.lastHuman,
        la: this.lastAi,
        pay: this.difficultyPayload(),
      }));
    } catch (e) { /* localStorage 不可用就算了 */ }
  }

  loadGame() {
    try {
      const raw = localStorage.getItem(this.STORE);
      return raw ? JSON.parse(raw) : null;
    } catch (e) { return null; }
  }

  clearGame() {
    try { localStorage.removeItem(this.STORE); } catch (e) { /* ignore */ }
  }

  // 把存檔的難度設定還原到 UI 控制項（否則下一步會被 UI 現值覆蓋）
  applyPayloadToUI(pay) {
    if (!pay) return;
    const mode = document.getElementById('mode');
    const wrap = document.getElementById('custom-wrap');
    if (typeof pay.difficulty === 'number') {
      if (mode) mode.value = 'custom';
      if (wrap) wrap.style.display = 'inline-flex';
      const d = document.getElementById('difficulty');
      const dv = document.getElementById('difficulty-val');
      const sm = document.getElementById('sims');
      const smv = document.getElementById('sims-val');
      if (d) d.value = pay.difficulty;
      if (dv) dv.textContent = pay.difficulty;
      if (sm && pay.sims != null) sm.value = pay.sims;
      if (smv && pay.sims != null) smv.textContent = pay.sims;
    } else if (mode && typeof pay.difficulty === 'string') {
      mode.value = pay.difficulty;
      if (wrap) wrap.style.display = 'none';
    }
  }

  create() {
    this.drawBoard();
    this.lastMoveGfx = this.add.graphics().setDepth(4); // 最近著法方框（在棋子下方）
    this.markerGfx = this.add.graphics().setDepth(5);
    this.connect();
    this.input.on('pointerdown', (p) => this.onClick(p));
    document.getElementById('new-game').onclick = () => this.newGame();
    const undoBtn = document.getElementById('undo');
    const resignBtn = document.getElementById('resign');
    const prevBtn = document.getElementById('prev');
    const nextBtn = document.getElementById('next');
    if (undoBtn) undoBtn.onclick = () => this.doUndo();
    if (resignBtn) resignBtn.onclick = () => this.doResign();
    if (prevBtn) prevBtn.onclick = () => this.viewStep(-1);
    if (nextBtn) nextBtn.onclick = () => this.viewStep(1);

    // 手機切回畫面時 WS 常已斷 → 自動重連並從存檔重建整局
    document.addEventListener('visibilitychange', () => {
      if (!document.hidden && (!this.ws || this.ws.readyState > 1)) this.connect();
    });
    window.addEventListener('online', () => {
      if (!this.ws || this.ws.readyState > 1) this.connect();
    });

    const diff = document.getElementById('difficulty');
    const diffVal = document.getElementById('difficulty-val');
    if (diff && diffVal) diff.oninput = () => (diffVal.textContent = diff.value);
    const sims = document.getElementById('sims');
    const simsVal = document.getElementById('sims-val');
    if (sims && simsVal) sims.oninput = () => (simsVal.textContent = sims.value);

    // 模式切換：選「自訂」才顯示 棋力 + 模擬數 兩支滑桿
    const mode = document.getElementById('mode');
    const wrap = document.getElementById('custom-wrap');
    if (mode && wrap) mode.onchange = () => (wrap.style.display = mode.value === 'custom' ? 'inline-flex' : 'none');
  }

  // 依目前選單組出難度 payload：自訂→{difficulty:1~100, sims}；預設→{difficulty:字串}
  difficultyPayload() {
    const mode = document.getElementById('mode');
    if (mode && mode.value === 'custom') {
      const slider = document.getElementById('difficulty');
      const sims = document.getElementById('sims');
      return {
        difficulty: slider ? parseInt(slider.value, 10) : 50,
        sims: sims ? parseInt(sims.value, 10) : 100,
      };
    }
    return { difficulty: mode ? mode.value : 'medium' };
  }

  newGame() {
    this.busy = false;
    this.intent = 'new_game';
    this.lastHuman = null;
    this.lastAi = null;
    this.moves = [];
    this.clearGame();
    this.send({ type: 'new_game', ...this.difficultyPayload() });
  }

  atLatest() {
    return this.viewPtr === this.history.length - 1;
  }

  doUndo() {
    // 回顧模式先跳回最新；未開局或無棋步可悔則忽略
    if (this.busy) return;
    if (!this.atLatest()) { this.viewPtr = this.history.length - 1; this.showSnapshot(); return; }
    if (this.history.length <= 1) return; // 只有起始盤，沒得悔
    const cur = this.history[this.viewPtr];
    if (cur && cur.gameOver && cur.gameOver !== 'black') return;
    this.intent = 'undo';
    this.busy = true;
    this.send({ type: 'undo' });
  }

  doResign() {
    if (this.busy || !this.atLatest()) return;
    const cur = this.history[this.viewPtr];
    if (cur && cur.gameOver) return;
    this.intent = 'resign';
    this.send({ type: 'resign' });
  }

  // 回顧棋譜：dir=-1 上一步、+1 下一步（唯讀，不改動伺服器盤面）
  viewStep(dir) {
    if (this.history.length === 0) return;
    const np = this.viewPtr + dir;
    if (np < 0 || np >= this.history.length) return;
    this.viewPtr = np;
    this.showSnapshot();
  }

  // 把 history[viewPtr] 的盤面畫出來（回顧模式：不可落子）
  showSnapshot() {
    const s = this.history[this.viewPtr];
    if (!s) return;
    this.parseFen(s.fen);
    this.redToMove = s.redToMove;
    this.gameOver = s.gameOver;
    this.legal = this.atLatest() ? s.legal || [] : [];
    this.selected = null;
    this.render();
    if (!this.atLatest()) {
      this.setStatus(`回顧中（第 ${this.viewPtr} / ${this.history.length - 1} 步）— 按「下一步」回到最新才能續弈`);
    } else {
      this.updateStatus(s);
    }
    this.updateNav();
  }

  updateNav() {
    const prev = document.getElementById('prev');
    const next = document.getElementById('next');
    const undo = document.getElementById('undo');
    const resign = document.getElementById('resign');
    if (prev) prev.disabled = this.viewPtr <= 0;
    if (next) next.disabled = this.atLatest();
    const cur = this.history[this.viewPtr];
    const over = !!(cur && cur.gameOver);
    if (undo) undo.disabled = this.busy || this.history.length <= 1;
    if (resign) resign.disabled = this.busy || over || !this.atLatest();
  }

  // ---- WebSocket ----
  connect() {
    // 已在連線/已連上就不重複開
    if (this.ws && (this.ws.readyState === WebSocket.CONNECTING || this.ws.readyState === WebSocket.OPEN)) return;
    if (this._reconnectTimer) { clearTimeout(this._reconnectTimer); this._reconnectTimer = null; }
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    this.ws = new WebSocket(`${proto}://${location.host}/ws`);
    this.ws.onopen = () => {
      this.setStatus('已連線');
      const saved = this.loadGame();
      if (saved && Array.isArray(saved.moves) && saved.moves.length > 0) {
        // 有未結束的存檔 → 重建整局，不要開新局
        this._saved = saved;
        this.intent = 'restore';
        this.applyPayloadToUI(saved.pay);
        this.send({ type: 'restore', moves: saved.moves, ...(saved.pay || {}) });
      } else {
        this.newGame();
      }
    };
    this.ws.onclose = () => {
      this.setStatus('連線中斷，自動重連中…');
      // 自動重連（伺服器重啟/網路波動時，不必手動重整）；重連後會自動 restore 整局
      if (!this._reconnectTimer) {
        this._reconnectTimer = setTimeout(() => { this._reconnectTimer = null; this.connect(); }, 2000);
      }
    };
    this.ws.onerror = () => { try { this.ws.close(); } catch (e) { /* ignore */ } };
    this.ws.onmessage = (e) => this.onMessage(JSON.parse(e.data));
  }

  send(obj) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(obj));
  }

  onMessage(msg) {
    if (msg.type === 'illegal') {
      this.setStatus('不合規則的走法');
      this.busy = false;
      this.updateNav();
      return;
    }
    if (msg.type !== 'state') return;

    const snap = {
      fen: msg.fen,
      redToMove: msg.redToMove,
      legal: msg.legal || [],
      gameOver: msg.gameOver,
      inCheck: msg.inCheck,
    };
    const intent = this.intent;
    this.intent = 'move'; // 下一則預設當作走子回覆

    if (intent === 'new_game') {
      this.history = [snap];
      this.viewPtr = 0;
      this.lastHuman = null;
      this.lastAi = null;
      this.moves = [];
    } else if (intent === 'restore') {
      // 重連重建：優先用存檔的歷史(含回顧棋譜)；伺服器回的 snap 是權威現況
      const s = this._saved;
      if (s && Array.isArray(s.hist) && s.hist.length) {
        this.history = s.hist;
        this.moves = Array.isArray(s.moves) ? s.moves : [];
        this.lastHuman = s.lh || null;
        this.lastAi = s.la || null;
      } else {
        this.history = [snap];
        this.moves = [];
      }
      this.viewPtr = this.history.length - 1;
      this._saved = null;
    } else if (intent === 'undo') {
      if (this.history.length > 1) this.history.pop(); // 丟掉被悔掉的那一組
      this.history[this.history.length - 1] = snap;
      this.viewPtr = this.history.length - 1;
      this.moves = this.moves.slice(0, Math.max(0, this.moves.length - 2)); // 收回人+AI 兩 ply
      this.lastHuman = null; // 悔棋後上一步標記已失效
      this.lastAi = null;
    } else if (intent === 'resign') {
      this.history[this.history.length - 1] = snap; // 盤面不變，只是標記終局
      this.viewPtr = this.history.length - 1;
    } else {
      // 一般走子
      if (msg.aiMove) {
        this.lastAi = msg.aiMove.slice(); // 記住 AI 這一步
        this.moves.push(msg.aiMove.slice()); // 記入整局著法（重連用）
      }
      this.history.push(snap);
      this.viewPtr = this.history.length - 1;
    }

    const applyVisual = () => {
      this.parseFen(snap.fen);
      this.redToMove = snap.redToMove;
      this.gameOver = snap.gameOver;
      this.legal = snap.legal;
      this.selected = null;
      this.render();
      this.busy = false;
      this.updateStatus(snap);
      this.updateNav();
      this.saveGame(); // 每次盤面更新都存檔（斷線重連用）
    };

    if (msg.aiMove && intent === 'move') {
      // 先播 AI 那步的動畫，再同步權威盤面
      this.animateMove(msg.aiMove[0], msg.aiMove[1], msg.aiMove[2], msg.aiMove[3], applyVisual);
    } else {
      applyVisual();
    }
  }

  updateStatus(msg) {
    if (this.gameOver) {
      const label =
        this.gameOver === 'draw' ? '和局' : this.gameOver === 'red' ? '紅方勝' : '黑方勝';
      this.setStatus(this.gameOver === 'red' ? '🎉 紅方勝！' : this.gameOver === 'draw' ? '和局（三次重複）' : '黑方勝，再接再厲');
      this.showBanner(label);
    } else if (msg.inCheck) {
      this.setStatus((this.redToMove ? '紅方' : '黑方') + '被將軍！');
      this.flashCheck();
    } else {
      this.setStatus(this.redToMove ? '輪到你（紅方）' : 'AI 思考中…');
    }
  }

  parseFen(fen) {
    this.grid = Array.from({ length: ROWS }, () => Array(COLS).fill(null));
    const rows = fen.split('/');
    for (let y = 0; y < rows.length && y < ROWS; y++) {
      let x = 0;
      for (const ch of rows[y]) {
        if (ch >= '1' && ch <= '9') x += parseInt(ch, 10);
        else {
          if (x < COLS) this.grid[y][x] = ch;
          x++;
        }
      }
    }
  }

  // ---- 互動 ----
  onClick(pointer) {
    if (this.busy || this.gameOver || !this.redToMove) return;
    if (!this.atLatest()) return; // 回顧模式不可落子
    const x = Math.round((pointer.x - MARGIN) / CELL);
    const y = Math.round((pointer.y - MARGIN) / CELL);
    if (x < 0 || x >= COLS || y < 0 || y >= ROWS) return;

    const ch = this.grid[y][x];
    const isRed = ch && RED_CHARS[ch] !== undefined;

    if (this.selected) {
      const ok = this.legal.some(
        (m) => m[0] === this.selected.x && m[1] === this.selected.y && m[2] === x && m[3] === y,
      );
      if (ok) {
        const from = this.selected;
        this.selected = null;
        this.markerGfx.clear();
        this.busy = true;
        this.intent = 'move';
        this.lastHuman = [from.x, from.y, x, y]; // 記住你這一步
        this.lastAi = null;
        this.moves.push([from.x, from.y, x, y]); // 記入整局著法（重連用）
        this.saveGame();
        this.setStatus('AI 思考中…');
        this.updateNav();
        this.drawLastMove(); // 立刻標出你這一步，不必等 AI 回手
        // 樂觀動畫：先把自己的子移過去（server 已驗證為合法目標）
        this.animateMove(from.x, from.y, x, y, null);
        // 每步都帶當前難度/sims → 中途調拉霸下一步立即生效
        this.send({ type: 'move', from: [from.x, from.y], to: [x, y], ...this.difficultyPayload() });
        return;
      }
    }
    this.selected = isRed ? { x, y } : null;
    this.drawMarkers();
  }

  // ---- 繪製 ----
  drawBoard() {
    const g = this.add.graphics();
    // 木紋漸層底
    g.fillStyle(0xead2a4, 1).fillRoundedRect(0, 0, W, H, 10);
    g.fillStyle(0x000000, 0.04);
    for (let i = 0; i < H; i += 6) g.fillRect(0, i, W, 2);

    g.lineStyle(1.6, 0x6b4a2b, 1);
    for (let y = 0; y < ROWS; y++) g.lineBetween(px(0), py(y), px(COLS - 1), py(y));
    for (let x = 0; x < COLS; x++) {
      if (x === 0 || x === COLS - 1) g.lineBetween(px(x), py(0), px(x), py(ROWS - 1));
      else {
        g.lineBetween(px(x), py(0), px(x), py(4));
        g.lineBetween(px(x), py(5), px(x), py(ROWS - 1));
      }
    }
    // 九宮斜線
    g.lineBetween(px(3), py(0), px(5), py(2));
    g.lineBetween(px(5), py(0), px(3), py(2));
    g.lineBetween(px(3), py(7), px(5), py(9));
    g.lineBetween(px(5), py(7), px(3), py(9));

    // 兵/炮 位置的傳統十字標記
    const marks = [
      [1, 2], [7, 2], [1, 7], [7, 7],
      [0, 3], [2, 3], [4, 3], [6, 3], [8, 3],
      [0, 6], [2, 6], [4, 6], [6, 6], [8, 6],
    ];
    g.lineStyle(1.4, 0x6b4a2b, 0.9);
    for (const [mx, my] of marks) this.drawStar(g, mx, my);

    // 楚河漢界
    this.add
      .text(W / 2, py(4.5), '楚 河          漢 界', {
        fontSize: '24px',
        color: '#6b4a2b',
        fontStyle: 'bold',
      })
      .setOrigin(0.5);
  }

  drawStar(g, x, y) {
    const s = 5, gap = 4;
    const cx = px(x), cy = py(y);
    const seg = (dx, dy) => {
      g.beginPath();
      g.moveTo(cx + dx * gap, cy + dy * gap + dy * s);
      g.lineTo(cx + dx * gap, cy + dy * gap);
      g.lineTo(cx + dx * gap + dx * s, cy + dy * gap);
      g.strokePath();
    };
    for (const dx of [-1, 1]) for (const dy of [-1, 1]) {
      if (x === 0 && dx === -1) continue; // 邊界不畫外側
      if (x === COLS - 1 && dx === 1) continue;
      seg(dx, dy);
    }
  }

  makePiece(x, y, ch) {
    const isRed = RED_CHARS[ch] !== undefined;
    const label = isRed ? RED_CHARS[ch] : BLACK_CHARS[ch];
    const shadow = this.add.circle(2, 3, R, 0x000000, 0.25);
    const base = this.add.circle(0, 0, R, 0xf3e2c0).setStrokeStyle(2.5, isRed ? 0xb03a2e : 0x2b2b2b);
    const inner = this.add.circle(0, 0, R - 5, 0xfaf0d8).setStrokeStyle(1, isRed ? 0xd98a80 : 0x777777);
    const txt = this.add
      .text(0, 0, label, {
        fontSize: '30px',
        color: isRed ? '#b03a2e' : '#1a1a1a',
        fontStyle: 'bold',
      })
      .setOrigin(0.5);
    const c = this.add.container(px(x), py(y), [shadow, base, inner, txt]).setDepth(10);
    c.setSize(R * 2, R * 2);
    return c;
  }

  render() {
    for (const c of this.sprites.values()) c.destroy();
    this.sprites.clear();
    for (let y = 0; y < ROWS; y++) {
      for (let x = 0; x < COLS; x++) {
        const ch = this.grid[y][x];
        if (ch) this.sprites.set(keyOf(x, y), this.makePiece(x, y, ch));
      }
    }
    this.drawLastMove();
    this.drawMarkers();
  }

  // 標出最近著法：起點小點、終點四角括號。你＝綠、AI＝藍。低調不擋棋子。
  drawLastMove() {
    const g = this.lastMoveGfx;
    if (!g) return;
    g.clear();
    if (!this.atLatest()) return; // 回顧模式不畫（避免與歷史盤面混淆）

    // 起點：中心一個半透明小圓點
    const dot = (x, y, color) => {
      g.fillStyle(color, 0.35);
      g.fillCircle(px(x), py(y), 7);
    };
    // 終點：四個角落的 L 形括號（包住格子，不畫整圈框）
    const corners = (x, y, color) => {
      const s = R + 5; // 括號離中心的半徑
      const len = 9; // L 每邊長度
      const cx = px(x), cy = py(y);
      g.lineStyle(3, color, 0.95);
      const L = (ox, oy, dx, dy) => {
        g.beginPath();
        g.moveTo(cx + ox, cy + oy + dy * len);
        g.lineTo(cx + ox, cy + oy);
        g.lineTo(cx + ox + dx * len, cy + oy);
        g.strokePath();
      };
      L(-s, -s, 1, 1);   // 左上
      L(s, -s, -1, 1);   // 右上
      L(-s, s, 1, -1);   // 左下
      L(s, s, -1, -1);   // 右下
    };

    if (this.lastHuman) {
      const [a, b, c, d] = this.lastHuman;
      dot(a, b, 0x2fbf4f);
      corners(c, d, 0x2fbf4f);
    }
    if (this.lastAi) {
      const [a, b, c, d] = this.lastAi;
      dot(a, b, 0x4d84c0);
      corners(c, d, 0x4d84c0);
    }
  }

  drawMarkers() {
    const m = this.markerGfx;
    m.clear();
    if (this.selected) {
      const { x, y } = this.selected;
      m.lineStyle(3, 0x2fbf4f, 1).strokeCircle(px(x), py(y), R + 4);
      m.fillStyle(0x2fbf4f, 0.5);
      for (const mv of this.legal) {
        if (mv[0] === x && mv[1] === y) m.fillCircle(px(mv[2]), py(mv[3]), 8);
      }
    }
  }

  // 動畫：把 (fx,fy) 的子移到 (tx,ty)，吃子則淡出；完成後 cb
  animateMove(fx, fy, tx, ty, cb) {
    const moving = this.sprites.get(keyOf(fx, fy));
    if (!moving) {
      if (cb) cb();
      return;
    }
    this.sprites.delete(keyOf(fx, fy));
    const captured = this.sprites.get(keyOf(tx, ty));
    if (captured) {
      this.sprites.delete(keyOf(tx, ty));
      this.tweens.add({
        targets: captured,
        scale: 0,
        alpha: 0,
        duration: 220,
        onComplete: () => captured.destroy(),
      });
    }
    this.sprites.set(keyOf(tx, ty), moving);
    moving.setDepth(20);
    this.tweens.add({
      targets: moving,
      x: px(tx),
      y: py(ty),
      duration: 260,
      ease: 'Cubic.easeInOut',
      onComplete: () => {
        moving.setDepth(10);
        if (cb) cb();
      },
    });
  }

  flashCheck() {
    // 找出被將軍方的將/帥閃紅光
    const target = this.redToMove ? 'K' : 'k';
    for (let y = 0; y < ROWS; y++)
      for (let x = 0; x < COLS; x++) {
        if (this.grid[y][x] === target) {
          const ring = this.add.circle(px(x), py(y), R + 6).setStrokeStyle(4, 0xff3b30).setDepth(15);
          this.tweens.add({
            targets: ring,
            alpha: 0,
            scale: 1.4,
            duration: 600,
            repeat: 1,
            onComplete: () => ring.destroy(),
          });
        }
      }
  }

  showBanner(text) {
    const bg = this.add.rectangle(W / 2, H / 2, W * 0.6, 90, 0x000000, 0.72).setDepth(30);
    const t = this.add
      .text(W / 2, H / 2, text, { fontSize: '40px', color: '#ffd479', fontStyle: 'bold' })
      .setOrigin(0.5)
      .setDepth(31);
    bg.setScale(0);
    t.setScale(0);
    this.tweens.add({ targets: [bg, t], scale: 1, duration: 350, ease: 'Back.easeOut' });
  }

  setStatus(s) {
    const el = document.getElementById('status');
    if (el) el.textContent = s;
  }
}

new Phaser.Game({
  type: Phaser.AUTO,
  parent: 'game',
  backgroundColor: '#1e1a17',
  scene: BoardScene,
  // RWD：以固定邏輯尺寸為基準，等比縮放塞進容器（手機直/橫都不跑版）。
  scale: {
    mode: Phaser.Scale.FIT,
    autoCenter: Phaser.Scale.CENTER_BOTH,
    width: W,
    height: H,
  },
});
