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
  }

  create() {
    this.drawBoard();
    this.markerGfx = this.add.graphics().setDepth(5);
    this.connect();
    this.input.on('pointerdown', (p) => this.onClick(p));
    document.getElementById('new-game').onclick = () => this.newGame();
    const diff = document.getElementById('difficulty');
    const diffVal = document.getElementById('difficulty-val');
    if (diff && diffVal) diff.oninput = () => (diffVal.textContent = diff.value);
  }

  newGame() {
    const el = document.getElementById('difficulty');
    const difficulty = el ? parseInt(el.value, 10) : 50;
    this.busy = false;
    this.send({ type: 'new_game', difficulty });
  }

  // ---- WebSocket ----
  connect() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    this.ws = new WebSocket(`${proto}://${location.host}/ws`);
    this.ws.onopen = () => {
      this.setStatus('已連線');
      this.newGame();
    };
    this.ws.onclose = () => this.setStatus('連線中斷，重整頁面再試');
    this.ws.onmessage = (e) => this.onMessage(JSON.parse(e.data));
  }

  send(obj) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(obj));
  }

  onMessage(msg) {
    if (msg.type === 'illegal') {
      this.setStatus('不合規則的走法');
      return;
    }
    if (msg.type !== 'state') return;

    const apply = () => {
      this.parseFen(msg.fen);
      this.redToMove = msg.redToMove;
      this.gameOver = msg.gameOver;
      this.legal = msg.legal || [];
      this.selected = null;
      this.render();
      this.busy = false;
      this.updateStatus(msg);
    };

    if (msg.aiMove) {
      // 先播 AI 那步的動畫，再同步權威盤面
      this.animateMove(msg.aiMove[0], msg.aiMove[1], msg.aiMove[2], msg.aiMove[3], apply);
    } else {
      apply();
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
        this.setStatus('AI 思考中…');
        // 樂觀動畫：先把自己的子移過去（server 已驗證為合法目標）
        this.animateMove(from.x, from.y, x, y, null);
        this.send({ type: 'move', from: [from.x, from.y], to: [x, y] });
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
    this.drawMarkers();
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
