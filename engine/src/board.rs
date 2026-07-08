//! 盤面表示與著法產生。
//!
//! 移植自 reference/cpp-console/position.cpp，沿用象棋巫師系經典的
//! 256 格（16×16）盤面：實際棋盤落在 rank 3..=12、file 3..=11，
//! 用單一位移量（KING_DELTA 等）描述走子方向，邊界靠 in_board() 擋掉。
//!
//! 里程碑 ② 範圍：盤面、著法產生（generate_moves，偽合法）、
//! make/undo（含自將過濾）、將軍偵測 checked、將死 is_mate。
//! Zobrist 重複判定留待里程碑 ③。

use crate::piece_value::PIECE_VALUE;

/// 走法：低 8 位為起點格、高 8 位為終點格。
pub type Move = u16;

// ---- 棋子種類（與紅黑標記相加得到棋子編碼）----
const PIECE_KING: u8 = 0; // 將／帥
const PIECE_ADVISOR: u8 = 1; // 士／仕
const PIECE_BISHOP: u8 = 2; // 象／相
const PIECE_KNIGHT: u8 = 3; // 馬
const PIECE_ROOK: u8 = 4; // 車
const PIECE_CANNON: u8 = 5; // 炮
const PIECE_PAWN: u8 = 6; // 卒／兵

// 紅子編碼 = 8 + 種類（8..=14）；黑子編碼 = 16 + 種類（16..=22）。
const RED_TAG: u8 = 8;
const BLACK_TAG: u8 = 16;

// 走子方向位移量（在 16 寬的虛擬盤上）。
const KING_DELTA: [i32; 4] = [-16, -1, 1, 16];
const ADVISOR_DELTA: [i32; 4] = [-17, -15, 15, 17];
const KNIGHT_DELTA: [[i32; 2]; 4] = [[-33, -31], [-18, 14], [-14, 18], [31, 33]];
const KNIGHT_CHECK_DELTA: [[i32; 2]; 4] = [[-33, -18], [-31, -14], [14, 31], [18, 33]];

/// 中國象棋開局盤面（黑方在上、紅方在下），不含走子方資訊。
pub const START_FEN: &str =
    "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR";

/// 取走法起點格。
#[inline]
pub fn src(mv: Move) -> u8 {
    (mv & 0xff) as u8
}

/// 取走法終點格。
#[inline]
pub fn dst(mv: Move) -> u8 {
    (mv >> 8) as u8
}

/// 由起訖格組出走法。
#[inline]
pub fn make_move_code(src: u8, dst: u8) -> Move {
    (src as u16) | ((dst as u16) << 8)
}

/// 格是否落在實際棋盤內（rank 3..=12、file 3..=11）。
///
/// 以函式取代 C++ 的 IN_BOARD_[256] 查表，語意等價且不易抄錯。
#[inline]
fn in_board(sq: i32) -> bool {
    if !(0..256).contains(&sq) {
        return false;
    }
    let rank = sq >> 4;
    let file = sq & 0x0f;
    (3..=12).contains(&rank) && (3..=11).contains(&file)
}

/// 格是否落在九宮內（紅黑各一，file 6..=8）。取代 C++ 的 IN_FORT_[256]。
#[inline]
fn in_fort(sq: i32) -> bool {
    if !(0..256).contains(&sq) {
        return false;
    }
    let rank = sq >> 4;
    let file = sq & 0x0f;
    let rank_ok = (3..=5).contains(&rank) || (10..=12).contains(&rank);
    rank_ok && (6..=8).contains(&file)
}

/// 象／相是否仍在本方半場（未過河）。sd：0=紅、1=黑。
#[inline]
fn home_half(sq: i32, sd: u8) -> bool {
    (sq & 0x80) != ((sd as i32) << 7)
}

/// 卒／兵是否已過河（在對方半場）。
#[inline]
fn away_half(sq: i32, sd: u8) -> bool {
    (sq & 0x80) == ((sd as i32) << 7)
}

/// 卒／兵向前一步的位置。紅往上（-16）、黑往下（+16）。
#[inline]
fn square_forward(sq: i32, sd: u8) -> i32 {
    sq - 16 + ((sd as i32) << 5)
}

/// 一個盤面狀態。
pub struct Board {
    /// 每格棋子編碼；0 為空格。索引 0..256。
    pub squares: [u8; 256],
    /// true = 該紅方走，false = 該黑方走。
    pub red_to_move: bool,
    /// 目前搜尋深度（步數）。
    pub distance: u16,
    /// 走法堆疊，供 undo。
    move_stack: Vec<Move>,
    /// 被吃子堆疊，與 move_stack 對齊；無吃子存 0。
    capture_stack: Vec<u8>,
}

impl Board {
    /// 建立空盤（紅方先行）。
    pub fn new() -> Self {
        Board {
            squares: [0u8; 256],
            red_to_move: true,
            distance: 0,
            move_stack: Vec::new(),
            capture_stack: Vec::new(),
        }
    }

    /// 建立中國象棋標準開局盤面。
    pub fn start() -> Self {
        let mut b = Board::new();
        b.load_fen(START_FEN);
        b
    }

    /// 走子方索引：紅=0、黑=1。
    #[inline]
    fn side(&self) -> u8 {
        if self.red_to_move {
            0
        } else {
            1
        }
    }

    /// 本方紅黑標記（紅=8、黑=16）。
    #[inline]
    fn self_tag(&self) -> u8 {
        RED_TAG + (self.side() << 3)
    }

    /// 對方紅黑標記。
    #[inline]
    fn opp_tag(&self) -> u8 {
        BLACK_TAG - (self.side() << 3)
    }

    /// 安全讀格：越界回傳 0（視為空格），供將軍偵測用。
    #[inline]
    fn at(&self, sq: i32) -> u8 {
        if (0..256).contains(&sq) {
            self.squares[sq as usize]
        } else {
            0
        }
    }

    /// 從 FEN 佈局字串擺子（不解析走子方欄位）。
    pub fn load_fen(&mut self, fen: &str) {
        self.squares = [0u8; 256];
        self.red_to_move = true;
        self.distance = 0;
        self.move_stack.clear();
        self.capture_stack.clear();

        const RANK_TOP: i32 = 3;
        const RANK_BOTTOM: i32 = 12;
        const FILE_LEFT: i32 = 3;
        const FILE_RIGHT: i32 = 11;

        let mut y = RANK_TOP;
        let mut x = FILE_LEFT;
        for c in fen.chars() {
            if c == ' ' {
                break;
            } else if c == '/' {
                x = FILE_LEFT;
                y += 1;
                if y > RANK_BOTTOM {
                    break;
                }
            } else if ('1'..='9').contains(&c) {
                x += c as i32 - '0' as i32;
            } else if let Some(pt) = char_to_piece(c.to_ascii_uppercase()) {
                if x <= FILE_RIGHT {
                    let tag = if c.is_ascii_uppercase() { RED_TAG } else { BLACK_TAG };
                    let sq = (x + (y << 4)) as usize;
                    self.squares[sq] = tag + pt;
                    x += 1;
                }
            }
        }
    }

    /// 切換走子方。
    #[inline]
    fn change_side(&mut self) {
        self.red_to_move = !self.red_to_move;
    }

    /// 移動棋子（不切邊、不做合法性檢查），並記錄以供 undo。
    fn move_piece(&mut self, mv: Move) {
        let s = src(mv) as usize;
        let d = dst(mv) as usize;
        let captured = self.squares[d];
        self.capture_stack.push(captured);
        self.squares[d] = self.squares[s];
        self.squares[s] = 0;
        self.move_stack.push(mv);
    }

    /// 撤銷 move_piece。
    fn undo_move_piece(&mut self) {
        let mv = self.move_stack.pop().expect("move_stack 為空");
        let s = src(mv) as usize;
        let d = dst(mv) as usize;
        self.squares[s] = self.squares[d];
        self.squares[d] = self.capture_stack.pop().expect("capture_stack 為空");
    }

    /// 嘗試走一步。若走完後本方被將軍（送死）則撤銷並回傳 false。
    pub fn make_move(&mut self, mv: Move) -> bool {
        self.move_piece(mv);
        if self.checked() {
            self.undo_move_piece();
            return false;
        }
        self.change_side();
        self.distance += 1;
        true
    }

    /// 撤銷 make_move。
    pub fn undo_make_move(&mut self) {
        self.distance -= 1;
        self.change_side();
        self.undo_move_piece();
    }

    /// 本方（目前走子方）的將是否正被將軍。
    pub fn checked(&self) -> bool {
        let self_tag = self.self_tag();
        let opp_tag = self.opp_tag();
        let sd = self.side();

        for sq in 0..256i32 {
            if self.squares[sq as usize] != self_tag + PIECE_KING {
                continue;
            }
            // 對方兵／卒正面攻將
            if self.at(square_forward(sq, sd)) == opp_tag + PIECE_PAWN {
                return true;
            }
            // 對方過河兵左右平推攻將
            for delta in [-1i32, 1] {
                if self.at(sq + delta) == opp_tag + PIECE_PAWN {
                    return true;
                }
            }
            // 對方馬攻將（檢查對應馬腿無子）
            for i in 0..4 {
                if self.at(sq + ADVISOR_DELTA[i]) != 0 {
                    continue; // 馬腿有子，此方向的馬別不了
                }
                for j in 0..2 {
                    if self.at(sq + KNIGHT_CHECK_DELTA[i][j]) == opp_tag + PIECE_KNIGHT {
                        return true;
                    }
                }
            }
            // 對方車／將帥對臉，與炮隔子攻將
            for i in 0..4 {
                let delta = KING_DELTA[i];
                let mut d = sq + delta;
                // 第一段：遇到的第一個子
                while in_board(d) {
                    let pc = self.squares[d as usize];
                    if pc > 0 {
                        if pc == opp_tag + PIECE_ROOK || pc == opp_tag + PIECE_KING {
                            return true;
                        }
                        break;
                    }
                    d += delta;
                }
                d += delta;
                // 第二段：翻過一子後遇到的子（炮）
                while in_board(d) {
                    let pc = self.squares[d as usize];
                    if pc > 0 {
                        if pc == opp_tag + PIECE_CANNON {
                            return true;
                        }
                        break;
                    }
                    d += delta;
                }
            }
            return false;
        }
        false
    }

    /// 前端座標（x:0..=8 檔、y:0..=9 列，左上為原點）轉內部格編號。
    #[inline]
    pub fn coord_to_sq(x: u8, y: u8) -> u8 {
        ((y + 3) << 4) + (x + 3)
    }

    /// 內部格編號轉前端座標 (x, y)。
    #[inline]
    pub fn sq_to_coord(sq: u8) -> (u8, u8) {
        let x = (sq & 0x0f) - 3;
        let y = (sq >> 4) - 3;
        (x, y)
    }

    /// 輸出佈局 FEN（僅佈局欄位，與 START_FEN 同格式）。
    pub fn to_fen(&self) -> String {
        let mut fen = String::new();
        for y in 0..10u8 {
            if y > 0 {
                fen.push('/');
            }
            let mut empty = 0;
            for x in 0..9u8 {
                let pc = self.squares[Self::coord_to_sq(x, y) as usize];
                if pc == 0 {
                    empty += 1;
                    continue;
                }
                if empty > 0 {
                    fen.push_str(&empty.to_string());
                    empty = 0;
                }
                let ch = piece_to_char(pc & 7);
                // 紅子（<16）大寫、黑子小寫
                fen.push(if pc < BLACK_TAG {
                    ch
                } else {
                    ch.to_ascii_lowercase()
                });
            }
            if empty > 0 {
                fen.push_str(&empty.to_string());
            }
        }
        fen
    }

    /// 目前走子方的所有合法著法（已過濾送死）。供前端提示與驗證用。
    pub fn legal_moves(&mut self) -> Vec<Move> {
        let mut legal = Vec::new();
        for mv in self.generate_moves() {
            if self.make_move(mv) {
                self.undo_make_move();
                legal.push(mv);
            }
        }
        legal
    }

    /// 局面評估分值，以「目前走子方」視角回傳（正值對己方有利）。
    ///
    /// 對照 position.cpp 的 evaluate()：紅子查 PIECE_VALUE[type][sq]，
    /// 黑子查鏡射格 [type][254-sq]，取紅黑差後依走子方轉正負。
    /// 此處每次從頭累加（O(256)），暫不做增量維護。
    pub fn evaluate(&self) -> i16 {
        let mut red: i32 = 0;
        let mut black: i32 = 0;
        for sq in 0..256usize {
            let pc = self.squares[sq];
            if pc == 0 {
                continue;
            }
            let pt = (pc & 7) as usize; // 低 3 位即棋子種類 0..=6
            if pc < BLACK_TAG {
                red += PIECE_VALUE[pt][sq] as i32;
            } else {
                black += PIECE_VALUE[pt][254 - sq] as i32;
            }
        }
        let vl = red - black;
        (if self.red_to_move { vl } else { -vl }) as i16
    }

    /// 目前走子方是否已被將死（無任何合法著法）。
    pub fn is_mate(&mut self) -> bool {
        let moves = self.generate_moves();
        for mv in moves {
            if self.make_move(mv) {
                self.undo_make_move();
                return false;
            }
        }
        true
    }

    /// 產生目前走子方的所有偽合法著法（未過濾自將；由 make_move 過濾）。
    pub fn generate_moves(&self) -> Vec<Move> {
        let mut mvs = Vec::new();
        let self_tag = self.self_tag();
        let opp_tag = self.opp_tag();
        let sd = self.side();

        for sq_src in 0..256i32 {
            let pc_src = self.squares[sq_src as usize];
            if pc_src & self_tag == 0 {
                continue; // 空格或對方子
            }
            match pc_src - self_tag {
                PIECE_KING => {
                    for i in 0..4 {
                        let sq_dst = sq_src + KING_DELTA[i];
                        if !in_fort(sq_dst) {
                            continue;
                        }
                        if self.squares[sq_dst as usize] & self_tag == 0 {
                            mvs.push(make_move_code(sq_src as u8, sq_dst as u8));
                        }
                    }
                }
                PIECE_ADVISOR => {
                    for i in 0..4 {
                        let sq_dst = sq_src + ADVISOR_DELTA[i];
                        if !in_fort(sq_dst) {
                            continue;
                        }
                        if self.squares[sq_dst as usize] & self_tag == 0 {
                            mvs.push(make_move_code(sq_src as u8, sq_dst as u8));
                        }
                    }
                }
                PIECE_BISHOP => {
                    for i in 0..4 {
                        // 象眼位置
                        let eye = sq_src + ADVISOR_DELTA[i];
                        if !(in_board(eye) && home_half(eye, sd) && self.squares[eye as usize] == 0)
                        {
                            continue; // 象眼越界／過河／被塞
                        }
                        let sq_dst = eye + ADVISOR_DELTA[i];
                        if self.squares[sq_dst as usize] & self_tag == 0 {
                            mvs.push(make_move_code(sq_src as u8, sq_dst as u8));
                        }
                    }
                }
                PIECE_KNIGHT => {
                    for i in 0..4 {
                        let leg = sq_src + KING_DELTA[i];
                        if self.at(leg) > 0 {
                            continue; // 蹩馬腿
                        }
                        for j in 0..2 {
                            let sq_dst = sq_src + KNIGHT_DELTA[i][j];
                            if !in_board(sq_dst) {
                                continue;
                            }
                            if self.squares[sq_dst as usize] & self_tag == 0 {
                                mvs.push(make_move_code(sq_src as u8, sq_dst as u8));
                            }
                        }
                    }
                }
                PIECE_ROOK => {
                    for i in 0..4 {
                        let delta = KING_DELTA[i];
                        let mut sq_dst = sq_src + delta;
                        while in_board(sq_dst) {
                            let pc_dst = self.squares[sq_dst as usize];
                            if pc_dst == 0 {
                                mvs.push(make_move_code(sq_src as u8, sq_dst as u8));
                            } else {
                                if pc_dst & opp_tag != 0 {
                                    mvs.push(make_move_code(sq_src as u8, sq_dst as u8));
                                }
                                break;
                            }
                            sq_dst += delta;
                        }
                    }
                }
                PIECE_CANNON => {
                    for i in 0..4 {
                        let delta = KING_DELTA[i];
                        let mut sq_dst = sq_src + delta;
                        // 未翻山：可走空格
                        while in_board(sq_dst) {
                            let pc_dst = self.squares[sq_dst as usize];
                            if pc_dst == 0 {
                                mvs.push(make_move_code(sq_src as u8, sq_dst as u8));
                            } else {
                                break;
                            }
                            sq_dst += delta;
                        }
                        // 翻過一子後：只能吃對方子
                        sq_dst += delta;
                        while in_board(sq_dst) {
                            let pc_dst = self.squares[sq_dst as usize];
                            if pc_dst > 0 {
                                if pc_dst & opp_tag != 0 {
                                    mvs.push(make_move_code(sq_src as u8, sq_dst as u8));
                                }
                                break;
                            }
                            sq_dst += delta;
                        }
                    }
                }
                PIECE_PAWN => {
                    // 向前一步
                    let sq_fwd = square_forward(sq_src, sd);
                    if in_board(sq_fwd) && self.squares[sq_fwd as usize] & self_tag == 0 {
                        mvs.push(make_move_code(sq_src as u8, sq_fwd as u8));
                    }
                    // 過河後可左右平走
                    if away_half(sq_src, sd) {
                        for delta in [-1i32, 1] {
                            let sq_dst = sq_src + delta;
                            if in_board(sq_dst) && self.squares[sq_dst as usize] & self_tag == 0 {
                                mvs.push(make_move_code(sq_src as u8, sq_dst as u8));
                            }
                        }
                    }
                }
                _ => {}
            }
        }
        mvs
    }
}

impl Default for Board {
    fn default() -> Self {
        Self::new()
    }
}

/// 棋子種類轉 FEN 大寫字元。
fn piece_to_char(pt: u8) -> char {
    match pt {
        PIECE_KING => 'K',
        PIECE_ADVISOR => 'A',
        PIECE_BISHOP => 'B',
        PIECE_KNIGHT => 'N',
        PIECE_ROOK => 'R',
        PIECE_CANNON => 'C',
        PIECE_PAWN => 'P',
        _ => '?',
    }
}

/// FEN 字元轉棋子種類（大寫）。
fn char_to_piece(c: char) -> Option<u8> {
    match c {
        'K' => Some(PIECE_KING),
        'A' => Some(PIECE_ADVISOR),
        'B' => Some(PIECE_BISHOP),
        'N' => Some(PIECE_KNIGHT),
        'R' => Some(PIECE_ROOK),
        'C' => Some(PIECE_CANNON),
        'P' => Some(PIECE_PAWN),
        _ => None,
    }
}
