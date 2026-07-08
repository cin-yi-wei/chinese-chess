// 中國象棋前端：Phaser 畫棋盤 + WebSocket 與 Rust 後端對弈。
// 人執紅（下方），AI 執黑（上方）。座標 x:0..8 檔、y:0..9 列，左上為原點。
import Phaser from 'phaser';

const COLS = 9;
const ROWS = 10;
const CELL = 64;
const MARGIN = 44;
const W = MARGIN * 2 + CELL * (COLS - 1);
const H = MARGIN * 2 + CELL * (ROWS - 1);
const R = 27; // 棋子半徑

// FEN 字元 → 顯示字 + 顏色。大寫紅、小寫黑。
const RED_CHARS = { K: '帥', A: '仕', B: '相', N: '馬', R: '車', C: '炮', P: '兵' };
const BLACK_CHARS = { k: '將', a: '士', b: '象', n: '馬', r: '車', c: '砲', p: '卒' };

const px = (x) => MARGIN + x * CELL;
const py = (y) => MARGIN + y * CELL;

class BoardScene extends Phaser.Scene {
  constructor() {
    super('board');
    this.grid = []; // grid[y][x] = FEN 字元 或 null
    this.redToMove = true;
    this.gameOver = null;
    this.legal = []; // [[fx,fy,tx,ty]...] 由後端提供
    this.selected = null; // {x,y}
    this.lastMove = null; // [fx,fy,tx,ty]
  }

  create() {
    this.drawBoard();
    this.markerGfx = this.add.graphics();
    this.pieceLayer = this.add.container();
    this.connect();

    this.input.on('pointerdown', (p) => this.onClick(p));
    document.getElementById('new-game').onclick = () => this.send({ type: 'new_game' });
  }

  // ---- WebSocket ----
  connect() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    this.ws = new WebSocket(`${proto}://${location.host}/ws`);
    this.ws.onopen = () => {
      this.setStatus('已連線');
      this.send({ type: 'new_game' });
    };
    this.ws.onclose = () => this.setStatus('連線中斷');
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
    this.parseFen(msg.fen);
    this.redToMove = msg.redToMove;
    this.gameOver = msg.gameOver;
    this.legal = msg.legal || [];
    this.selected = null;
    if (msg.aiMove) this.lastMove = msg.aiMove;
    this.render();

    if (this.gameOver) {
      this.setStatus(this.gameOver === 'red' ? '紅方勝！' : '黑方勝！');
    } else if (msg.inCheck) {
      this.setStatus((this.redToMove ? '紅方' : '黑方') + '被將軍！');
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
        if (ch >= '1' && ch <= '9') {
          x += parseInt(ch, 10);
        } else {
          if (x < COLS) this.grid[y][x] = ch;
          x++;
        }
      }
    }
  }

  // ---- 互動 ----
  onClick(pointer) {
    if (this.gameOver || !this.redToMove) return;
    const x = Math.round((pointer.x - MARGIN) / CELL);
    const y = Math.round((pointer.y - MARGIN) / CELL);
    if (x < 0 || x >= COLS || y < 0 || y >= ROWS) return;

    const ch = this.grid[y][x];
    const isRed = ch && RED_CHARS[ch] !== undefined;

    // 已選子 → 若點的是合法目標就走
    if (this.selected) {
      const ok = this.legal.some(
        (m) => m[0] === this.selected.x && m[1] === this.selected.y && m[2] === x && m[3] === y,
      );
      if (ok) {
        this.lastMove = [this.selected.x, this.selected.y, x, y];
        this.send({ type: 'move', from: [this.selected.x, this.selected.y], to: [x, y] });
        this.selected = null;
        this.setStatus('AI 思考中…');
        this.render();
        return;
      }
    }
    // 選自己的子
    if (isRed) {
      this.selected = { x, y };
    } else {
      this.selected = null;
    }
    this.render();
  }

  // ---- 繪製 ----
  drawBoard() {
    const g = this.add.graphics();
    g.fillStyle(0xe9c893, 1).fillRoundedRect(0, 0, W, H, 8); // 木紋底
    g.lineStyle(1.6, 0x5a3d24, 1);

    // 橫線
    for (let y = 0; y < ROWS; y++) {
      g.lineBetween(px(0), py(y), px(COLS - 1), py(y));
    }
    // 直線（中間河界斷開）
    for (let x = 0; x < COLS; x++) {
      if (x === 0 || x === COLS - 1) {
        g.lineBetween(px(x), py(0), px(x), py(ROWS - 1));
      } else {
        g.lineBetween(px(x), py(0), px(x), py(4));
        g.lineBetween(px(x), py(5), px(x), py(ROWS - 1));
      }
    }
    // 九宮斜線
    g.lineBetween(px(3), py(0), px(5), py(2));
    g.lineBetween(px(5), py(0), px(3), py(2));
    g.lineBetween(px(3), py(7), px(5), py(9));
    g.lineBetween(px(5), py(7), px(3), py(9));

    // 楚河漢界
    this.add
      .text(W / 2, py(4.5), '楚 河          漢 界', {
        fontSize: '22px',
        color: '#5a3d24',
        fontStyle: 'bold',
      })
      .setOrigin(0.5);
  }

  render() {
    // 標記層：選取、合法點、上一手
    const m = this.markerGfx;
    m.clear();
    if (this.lastMove) {
      const [fx, fy, tx, ty] = this.lastMove;
      m.lineStyle(2, 0x2f7fff, 0.9);
      m.strokeCircle(px(fx), py(fy), R + 2);
      m.strokeCircle(px(tx), py(ty), R + 2);
    }
    if (this.selected) {
      m.lineStyle(3, 0x2fbf4f, 1).strokeCircle(px(this.selected.x), py(this.selected.y), R + 3);
      m.fillStyle(0x2fbf4f, 0.55);
      for (const mv of this.legal) {
        if (mv[0] === this.selected.x && mv[1] === this.selected.y) {
          m.fillCircle(px(mv[2]), py(mv[3]), 8);
        }
      }
    }

    // 棋子層
    this.pieceLayer.removeAll(true);
    for (let y = 0; y < ROWS; y++) {
      for (let x = 0; x < COLS; x++) {
        const ch = this.grid[y][x];
        if (!ch) continue;
        const isRed = RED_CHARS[ch] !== undefined;
        const label = isRed ? RED_CHARS[ch] : BLACK_CHARS[ch];
        const disc = this.add.circle(px(x), py(y), R, 0xf7e7c8).setStrokeStyle(2.5, isRed ? 0xc0392b : 0x222222);
        const txt = this.add
          .text(px(x), py(y), label, {
            fontSize: '30px',
            color: isRed ? '#c0392b' : '#1a1a1a',
            fontStyle: 'bold',
          })
          .setOrigin(0.5);
        this.pieceLayer.add(disc);
        this.pieceLayer.add(txt);
      }
    }
  }

  setStatus(s) {
    const el = document.getElementById('status');
    if (el) el.textContent = s;
  }
}

new Phaser.Game({
  type: Phaser.AUTO,
  width: W,
  height: H,
  parent: 'game',
  backgroundColor: '#1e1a17',
  scene: BoardScene,
});
